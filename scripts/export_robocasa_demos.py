#!/usr/bin/env python3
"""Export exact-task RoboCasa training episodes without changing their frames.

Example:
    python3 scripts/export_robocasa_demos.py --dataset-root /path/to/robocasa/v1.0

The dataset root must contain the official downloaded/extracted LeRobot archives
and their .download_complete.json provenance receipts. Source files are read only.
One complete episode and its left external camera are selected per gallery task.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


DATASET = "RoboCasa v1.0 training demonstrations"
DATASET_URL = "https://huggingface.co/datasets/nvidia/PhysicalAI-Robotics-Manipulation-Kitchen-Demos"
CAMERA = "observation.images.robot0_agentview_left"
EPISODE = 0


@dataclass(frozen=True)
class Candidate:
    path: Path
    receipt: dict

    @property
    def priority(self) -> tuple:
        source = self.receipt["source"]
        split = self.receipt["split"]
        rank = 0 if (source, split) == ("human", "target") else 1 if source == "human" else 2
        return rank, self.path.as_posix()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run(*args: str) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def probe(path: Path, *, count_frames: bool = False) -> dict:
    args = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if count_frames:
        args.append("-count_frames")
    args.extend([
        "-show_entries",
        "stream=codec_name,pix_fmt,width,height,nb_frames,nb_read_frames,avg_frame_rate,duration",
        "-of", "json", str(path),
    ])
    streams = json.loads(run(*args))["streams"]
    if len(streams) != 1:
        raise ValueError(f"Expected one video stream in {path}")
    return streams[0]


def faststart(path: Path) -> bool:
    """Inspect top-level MP4 atoms without mistaking payload text for atom names."""
    with path.open("rb") as handle:
        while header := handle.read(8):
            if len(header) != 8:
                return False
            size = int.from_bytes(header[:4], "big")
            kind = header[4:]
            header_size = 8
            if size == 1:
                size = int.from_bytes(handle.read(8), "big")
                header_size = 16
            if kind == b"moov":
                return True
            if kind == b"mdat" or size < header_size:
                return False
            handle.seek(size - header_size, 1)
    return False


def candidates(dataset_root: Path) -> dict[str, Candidate]:
    # Explicit layouts avoid scanning millions of frame/state/data files.
    patterns = (
        "*/*/*/*/lerobot/.download_complete.json",
        "*/*/*/*/mg/demo/*/lerobot/.download_complete.json",
        "*/*/*/*/demo/*/lerobot/.download_complete.json",
    )
    choices: dict[str, list[Candidate]] = {}
    for pattern in patterns:
        for receipt_path in sorted(dataset_root.glob(pattern)):
            receipt = read_json(receipt_path)
            if receipt["split"] not in {"target", "pretrain"}:
                raise ValueError(f"Unexpected dataset split: {receipt_path}")
            name = receipt["task"]
            # Compare the canonical task directory with the download receipt.
            relative = receipt_path.relative_to(dataset_root)
            if relative.parts[2] != name:
                raise ValueError(f"Task directory disagrees with receipt: {receipt_path}")
            choices.setdefault("robocasa_" + name.lower(), []).append(
                Candidate(receipt_path.parent, receipt)
            )
    return {task_id: min(options, key=lambda item: item.priority) for task_id, options in choices.items()}


def export_task(task: dict, candidate: Candidate, dataset_root: Path, gallery_root: Path) -> dict:
    path = candidate.path
    receipt = candidate.receipt
    name = receipt["task"]
    if task["id"] != "robocasa_" + name.lower():
        raise ValueError(f"Task ID mismatch: {task['id']} / {name}")
    info = read_json(path / "meta/info.json")
    labels = {item["task"] for item in read_jsonl(path / "meta/tasks.jsonl")}
    if name not in labels:
        raise ValueError(f"Canonical task is absent from meta/tasks.jsonl: {name}")
    episodes = [row for row in read_jsonl(path / "meta/episodes.jsonl") if row["episode_index"] == EPISODE]
    if len(episodes) != 1:
        raise ValueError(f"Missing or duplicate episode zero: {name}")
    episode = episodes[0]
    if not episode["tasks"] or any(label not in labels for label in episode["tasks"]):
        raise ValueError(f"Episode task labels disagree with task metadata: {name}")
    train_start, train_stop = (int(value) for value in info["splits"]["train"].split(":"))
    if not train_start <= EPISODE < train_stop:
        raise ValueError(f"Selected episode is outside the training split: {name}")
    video_key = info["features"][CAMERA]
    if video_key["dtype"] != "video":
        raise ValueError(f"Missing external camera video: {name}")
    relative_video = info["video_path"].format(
        episode_chunk=EPISODE // info["chunks_size"], video_key=CAMERA, episode_index=EPISODE
    )
    source_video = path / relative_video
    source_probe = probe(source_video)
    frames = int(source_probe["nb_frames"])
    fps = Fraction(source_probe["avg_frame_rate"])
    if frames != episode["length"] or fps != Fraction(str(info["fps"])):
        raise ValueError(f"Source video frame count or FPS disagrees with metadata: {name}")
    if video_key["shape"][:2] != [source_probe["height"], source_probe["width"]]:
        raise ValueError(f"Source video dimensions disagree with metadata: {name}")

    output_dir = gallery_root / "media/demos/robocasa"
    output_dir.mkdir(parents=True, exist_ok=True)
    video = output_dir / f"{task['id']}.mp4"
    poster = output_dir / f"{task['id']}.jpg"
    # The released H.264/yuv420p videos already fit the site budget. Remuxing
    # moves the index to the front without any frame or quality changes.
    compatible = source_probe["codec_name"] == "h264" and source_probe["pix_fmt"] == "yuv420p"
    codec_args = ["-c:v", "copy"] if compatible else [
        "-c:v", "libx264", "-preset", "fast", "-crf", "29", "-pix_fmt", "yuv420p",
        "-threads", "2", "-vsync", "0",
    ]
    with tempfile.TemporaryDirectory(prefix=f".{task['id']}-", dir=output_dir) as temp_dir:
        temp_video = Path(temp_dir) / "video.mp4"
        temp_poster = Path(temp_dir) / "poster.jpg"
        run("ffmpeg", "-nostdin", "-v", "error", "-xerror", "-y", "-i", str(source_video),
            "-map", "0:v:0", "-an", *codec_args, "-movflags", "+faststart", str(temp_video))
        actual = probe(temp_video, count_frames=True)
        if (int(actual["nb_frames"]) != frames or int(actual["nb_read_frames"]) != frames
                or Fraction(actual["avg_frame_rate"]) != fps
                or (actual["width"], actual["height"]) != (source_probe["width"], source_probe["height"])):
            raise ValueError(f"Output did not preserve all source frames and timing: {name}")
        if not faststart(temp_video):
            raise ValueError(f"Output MP4 lacks a front-loaded index: {name}")
        run("ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-i", str(temp_video),
            "-map", "0:v:0", "-f", "null", "-")
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "2", "-i", str(temp_video),
            "-frames:v", "1", "-q:v", "2", "-threads", "1", str(temp_poster))
        temp_video.replace(video)
        temp_poster.replace(poster)

    return {
        "taskId": task["id"],
        "benchmark": "robocasa",
        "status": "available",
        "instruction": " ".join(episode["tasks"]),
        "video": video.relative_to(gallery_root).as_posix(),
        "poster": poster.relative_to(gallery_root).as_posix(),
        "width": source_probe["width"],
        "height": source_probe["height"],
        "frames": frames,
        "fps": float(fps),
        "durationSeconds": round(float(Fraction(frames, 1) / fps), 6),
        "cameras": ["Agent view (left)"],
        "source": {
            "dataset": DATASET,
            "url": receipt.get("shared_url", receipt["url"]),
            "relativePath": (Path("v1.0") / source_video.relative_to(dataset_root)).as_posix(),
            "episode": "episode_000000",
            "split": receipt["split"] + "/train",
            "taskName": name,
            "demonstrationType": receipt["source"],
            "videoSha256": sha256(source_video),
        },
        "videoBytes": video.stat().st_size,
        "videoSha256": sha256(video),
        "posterSha256": sha256(poster),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, required=True, help="Extracted RoboCasa v1.0 directory")
    parser.add_argument("--gallery-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true", help="Report exact-task coverage without exporting")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")
    dataset_root = args.dataset_root.resolve()
    gallery_root = args.gallery_root.resolve()
    gallery = read_json(gallery_root / "data/gallery.json")
    tasks = next(bench["tasks"] for bench in gallery["benchmarks"] if bench["id"] == "robocasa")
    available = candidates(dataset_root)
    missing = [task["id"] for task in tasks if task["id"] not in available]
    print(json.dumps({"tasks": len(tasks), "available": len(tasks) - len(missing), "unavailable": missing}), flush=True)
    if args.dry_run:
        return
    records = {
        task_id: {
            "taskId": task_id,
            "benchmark": "robocasa",
            "status": "unavailable",
            "reason": "No released training demonstration for this task",
            "source": {"dataset": DATASET, "url": DATASET_URL},
        }
        for task_id in missing
    }
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(export_task, task, available[task["id"]], dataset_root, gallery_root): task["id"]
            for task in tasks if task["id"] in available
        }
        completed = 0
        for future in as_completed(futures):
            task_id = futures[future]
            records[task_id] = future.result()
            completed += 1
            if completed % 25 == 0 or completed == len(futures):
                print(f"Validated {completed}/{len(futures)} full training videos", flush=True)
    output = gallery_root / "artifacts/task-demos/robocasa.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    ordered = [records[task["id"]] for task in tasks]
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(output)
    print(json.dumps({
        "artifact": output.relative_to(gallery_root).as_posix(),
        "available": len(futures), "unavailable": len(missing),
        "videoBytes": sum(record.get("videoBytes", 0) for record in ordered),
        "frames": sum(record.get("frames", 0) for record in ordered),
    }), flush=True)


if __name__ == "__main__":
    main()
