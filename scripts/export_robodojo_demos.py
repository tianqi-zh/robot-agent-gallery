#!/usr/bin/env python3
"""Download and export complete, exact-task official RoboDojo demo videos.

The input metadata is a complete Hugging Face tree listing for data/RoboDojo
with repo, revision, and files fields. Only one head-camera preview per matching
task is downloaded; HDF5 episodes and the other cameras are never downloaded.

Example:
    python3 scripts/export_robodojo_demos.py \
        --metadata /tmp/robodojo-RoboDojo-metadata.json --plan-only
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from fractions import Fraction
from http.client import HTTPException
import json
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from export_robocasa_demos import faststart, probe, run, sha256


REPO_ID = "RoboDojo-Benchmark/RoboDojo"
REVISION = "91f76c28d93dd20c5fa46ce6a5a1d96a4f384acd"
DATASET = "RoboDojo official training demonstrations"
DATASET_URL = f"https://huggingface.co/datasets/{REPO_ID}"
PREFIX = "data/RoboDojo"
EPISODE = "episode_0000000"
CAMERA = "cam_head"
VIDEO_SUFFIX = f"arx_x5/preview_video/{EPISODE}_{CAMERA}.mp4"
SELECTION_RULE = (
    "Exact case-sensitive nativeTaskName folder only; arx_x5, episode zero, "
    "head camera. Preserve the complete source video. No task aliases."
)


@dataclass(frozen=True)
class Candidate:
    task_name: str
    relative_path: str
    size: int
    digest: str

    @property
    def url(self) -> str:
        return f"{DATASET_URL}/resolve/{REVISION}/{quote(self.relative_path, safe='/')}?download=true"

    def source(self) -> dict:
        return {
            "dataset": DATASET,
            "url": f"{DATASET_URL}/blob/{REVISION}/{quote(self.relative_path, safe='/')}",
            "downloadUrl": self.url,
            "repoId": REPO_ID,
            "revision": REVISION,
            "relativePath": self.relative_path,
            "taskName": self.task_name,
            "episode": EPISODE,
            "camera": CAMERA,
            "robot": "arx_x5",
            "split": "train",
            "sourceBytes": self.size,
            "sourceSha256": self.digest,
            "videoSha256": self.digest,
        }


def select_sources(tasks: list[dict], metadata: dict) -> tuple[dict[str, Candidate], list[dict]]:
    """Fail closed on inconsistent metadata; never substitute a similar task."""
    if metadata.get("repo") != REPO_ID or metadata.get("revision") != REVISION:
        raise ValueError("Source metadata must identify the pinned official repository and revision")
    files = metadata.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Source metadata must contain the complete data/RoboDojo file listing")
    summary = metadata.get("summary", {})
    if "files" in summary and summary["files"] != len(files):
        raise ValueError("Source file listing is incomplete according to its summary")
    by_path, task_names = {}, set()
    for item in files:
        path = item.get("path", "")
        parts = PurePosixPath(path).parts
        if (not isinstance(path, str) or not path.startswith(PREFIX + "/")
                or len(parts) < 5 or ".." in parts or "\\" in path
                or PurePosixPath(path).as_posix() != path):
            raise ValueError(f"Invalid source path: {path!r}")
        if path in by_path:
            raise ValueError(f"Duplicate source path: {path}")
        by_path[path] = item
        task_names.add(parts[2])
    if "subdirs" in summary and set(summary["subdirs"]) != task_names:
        raise ValueError("Source task folders disagree with metadata summary")

    selected, unavailable, seen = {}, [], set()
    for task in tasks:
        task_id, name = task.get("id"), task.get("nativeTaskName")
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", name)
                or task_id != f"robodojo_{name.lower()}" or task_id in seen):
            raise ValueError(f"Invalid or duplicate gallery task identity: {task_id!r} / {name!r}")
        seen.add(task_id)
        path = f"{PREFIX}/{name}/{VIDEO_SUFFIX}"
        if name not in task_names:
            unavailable.append({
                "taskId": task_id,
                "benchmark": "robodojo",
                "status": "unavailable",
                "reason": "Exact task is absent from the pinned official RoboDojo training dataset",
                "source": {
                    "dataset": DATASET,
                    "url": f"{DATASET_URL}/tree/{REVISION}/{PREFIX}",
                    "repoId": REPO_ID,
                    "revision": REVISION,
                    "taskName": name,
                },
            })
            continue
        if path not in by_path:
            raise ValueError(f"Task exists but its selected episode/head-camera video is missing: {name}")
        item = by_path[path]
        lfs = item.get("lfs", {})
        size, digest = item.get("size"), lfs.get("oid")
        if (type(size) is not int or size <= 0 or lfs.get("size") != size
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError(f"Missing or inconsistent LFS size/SHA-256: {path}")
        selected[task_id] = Candidate(name, path, size, digest)
    return selected, unavailable


def load_instructions(receipt: dict, metadata: dict, selected: dict[str, Candidate]) -> dict[str, dict]:
    """Bind an optional HDF5 metadata receipt to the exact downloaded episode.

    The receipt contains instruction fields read from pinned HDF5 sources using
    bounded HTTP ranges; its source digest identifies the official complete HDF5
    file, not a digest claimed to have been recomputed from a partial download.
    """
    if receipt.get("repo") != REPO_ID or receipt.get("revision") != REVISION:
        raise ValueError("Instruction metadata must identify the pinned repository and revision")
    if not isinstance(receipt.get("records"), list):
        raise ValueError("Instruction metadata must contain source records")
    sources = {item["path"]: item for item in metadata["files"]}
    instructions, seen = {}, set()
    for record in receipt["records"]:
        name = record.get("taskName")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", name) or name in seen:
            raise ValueError("Instruction metadata has invalid or duplicate task names")
        seen.add(name)
        task_id = f"robodojo_{name.lower()}"
        if task_id not in selected:
            continue
        if selected[task_id].task_name != name:
            raise ValueError("Instruction task name does not exactly match selected video")
        expected = f"{PREFIX}/{name}/arx_x5/data/{EPISODE}.hdf5"
        item = sources.get(expected, {})
        if (record.get("sourcePath") != expected or not item
                or record.get("sourceSha256") != item.get("lfs", {}).get("oid")
                or record.get("sourceBytes") != item.get("size")):
            raise ValueError(f"Instruction source does not match the selected pinned HDF5 episode: {name}")
        instruction = record.get("instructions", {}).get("instruction")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError(f"Instruction source lacks an instruction string: {name}")
        instructions[task_id] = {
            "instruction": instruction,
            "instructionSource": {
                "relativePath": expected,
                "url": f"{DATASET_URL}/blob/{REVISION}/{quote(expected, safe='/')}",
                "sourceSha256": record["sourceSha256"],
                "sourceBytes": record["sourceBytes"],
                "field": "instruction",
                "verification": "HDF5 instruction read from pinned source using HTTP ranges",
            },
        }
    return instructions


def download(candidate: Candidate, dataset_root: Path, *, retries: int = 4) -> Path:
    """Resume a partial response and publish only size/SHA-256 verified bytes."""
    destination = dataset_root / candidate.relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    if destination.exists():
        if destination.stat().st_size == candidate.size and sha256(destination) == candidate.digest:
            return destination
        raise ValueError(f"Existing source failed pinned size/SHA-256 validation: {destination}")
    for attempt in range(retries):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset >= candidate.size:
                if offset == candidate.size and sha256(partial) == candidate.digest:
                    partial.replace(destination)
                    return destination
                partial.unlink()
                offset = 0
            headers = {"Accept-Encoding": "identity", "User-Agent": "robot-agent-gallery/1.0"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            # Fresh redirect URLs on retries avoid stale signed download URLs.
            url = candidate.url + (f"&retry={time.time_ns()}" if attempt else "")
            with urlopen(Request(url, headers=headers), timeout=60) as response:
                status = response.status
                if status == 206:
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", ""))
                    if (not match or int(match[1]) != offset or int(match[3]) != candidate.size
                            or int(match[2]) != candidate.size - 1):
                        raise ValueError("Download returned an unexpected Content-Range")
                elif status == 200:
                    # Servers may ignore Range. Replace, never append, a full body.
                    offset = 0
                else:
                    raise ValueError(f"Unexpected download status: {status}")
                encoding = response.headers.get("Content-Encoding", "identity")
                if encoding != "identity":
                    raise ValueError(f"Unexpected download content encoding: {encoding}")
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) != candidate.size - offset:
                    raise ValueError("Download Content-Length disagrees with the pinned source size")
                with partial.open("ab" if offset else "wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                        if handle.tell() > candidate.size:
                            raise ValueError("Download exceeded the pinned source size")
            if partial.stat().st_size != candidate.size:
                raise ValueError("Download ended before the pinned source size")
            if sha256(partial) != candidate.digest:
                partial.unlink()
                raise ValueError("Downloaded source SHA-256 disagrees with the pinned LFS hash")
            partial.replace(destination)
            return destination
        except (HTTPError, URLError, HTTPException, OSError, ValueError) as error:
            if attempt + 1 == retries:
                raise RuntimeError(f"Unable to verify {candidate.relative_path}: {error}") from error
            time.sleep(min(2 ** attempt, 8))
    raise ValueError("retries must be at least 1")


def export_task(task: dict, candidate: Candidate, dataset_root: Path, gallery_root: Path,
                instruction: dict | None = None) -> dict:
    if (task.get("nativeTaskName") != candidate.task_name
            or task.get("id") != f"robodojo_{candidate.task_name.lower()}"):
        raise ValueError("Gallery task and selected source differ")
    source_video = download(candidate, dataset_root)
    original = probe(source_video, count_frames=True)
    frames = int(original["nb_read_frames"])
    fps = Fraction(original["avg_frame_rate"])
    if frames < 1 or fps <= 0:
        raise ValueError(f"Source has invalid frame count or FPS: {candidate.task_name}")
    if original.get("nb_frames", "N/A") != "N/A" and int(original["nb_frames"]) != frames:
        raise ValueError(f"Source declared and decoded frame counts differ: {candidate.task_name}")
    output_dir = gallery_root / "media/demos/robodojo"
    output_dir.mkdir(parents=True, exist_ok=True)
    video = output_dir / f"{task['id']}.mp4"
    poster = output_dir / f"{task['id']}.jpg"
    compatible = original["codec_name"] == "h264" and original["pix_fmt"] == "yuv420p"
    codec_args = ["-c:v", "copy"] if compatible else [
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-threads", "2", "-vsync", "0",
    ]
    with tempfile.TemporaryDirectory(prefix=f".{task['id']}-", dir=output_dir) as temporary:
        temp_video, temp_poster = Path(temporary) / "video.mp4", Path(temporary) / "poster.jpg"
        run("ffmpeg", "-nostdin", "-v", "error", "-xerror", "-y", "-i", str(source_video),
            "-map", "0:v:0", "-an", *codec_args, "-movflags", "+faststart", str(temp_video))
        actual = probe(temp_video, count_frames=True)
        if (int(actual["nb_frames"]) != frames or int(actual["nb_read_frames"]) != frames
                or Fraction(actual["avg_frame_rate"]) != fps
                or (actual["width"], actual["height"]) != (original["width"], original["height"])
                or actual["codec_name"] != "h264" or actual["pix_fmt"] != "yuv420p"):
            raise ValueError(f"Output did not preserve source frames, FPS, and dimensions: {candidate.task_name}")
        if not faststart(temp_video):
            raise ValueError(f"Output MP4 lacks a front-loaded index: {candidate.task_name}")
        run("ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-i", str(temp_video),
            "-map", "0:v:0", "-f", "null", "-")
        run("ffmpeg", "-nostdin", "-v", "error", "-y", "-threads", "2", "-i", str(temp_video),
            "-frames:v", "1", "-q:v", "2", "-threads", "1", str(temp_poster))
        temp_video.replace(video)
        temp_poster.replace(poster)
    # Only a source HDF5 receipt can supply language; a gallery evaluation
    # instruction is not evidence of this demonstration's instruction.
    source = candidate.source()
    source.update({"frames": frames, "fps": float(fps), "width": original["width"], "height": original["height"]})
    record = {
        "taskId": task["id"], "benchmark": "robodojo", "status": "available",
        "video": video.relative_to(gallery_root).as_posix(),
        "poster": poster.relative_to(gallery_root).as_posix(),
        "width": original["width"], "height": original["height"],
        "frames": frames, "fps": float(fps),
        "durationSeconds": round(float(Fraction(frames, 1) / fps), 6),
        "cameras": ["Head camera"], "source": source,
        "videoBytes": video.stat().st_size, "videoSha256": sha256(video),
        "posterBytes": poster.stat().st_size, "posterSha256": sha256(poster),
    }
    if instruction is not None:
        record["instruction"] = instruction["instruction"]
        source["instructionSource"] = instruction["instructionSource"]
    return record


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=f".{path.name}-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
            handle.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True, help="Pinned official data/RoboDojo HF tree metadata")
    parser.add_argument("--instructions", type=Path, help="Optional pinned HDF5 instruction metadata receipt")
    parser.add_argument("--dataset-root", type=Path, default=Path("/playpen-ssd/dataset/robodojo"))
    parser.add_argument("--gallery-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--plan-only", action="store_true", help="Report exact task coverage without downloads or writes")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    gallery_root, dataset_root = args.gallery_root.resolve(), args.dataset_root.resolve()
    gallery = json.loads((gallery_root / "data/gallery.json").read_text())
    benchmarks = [bench for bench in gallery["benchmarks"] if bench["id"] == "robodojo"]
    if len(benchmarks) != 1 or not benchmarks[0]["tasks"]:
        raise ValueError("Import RoboDojo gallery tasks before exporting their demonstrations")
    tasks = benchmarks[0]["tasks"]
    metadata = json.loads(args.metadata.read_text())
    selected, unavailable = select_sources(tasks, metadata)
    instructions = (load_instructions(json.loads(args.instructions.read_text()), metadata, selected)
                    if args.instructions else {})
    summary = {"tasks": len(tasks), "available": len(selected), "unavailable": [item["taskId"] for item in unavailable],
               "downloadBytes": sum(item.size for item in selected.values()), "sourceInstructions": len(instructions),
               "repoId": REPO_ID, "revision": REVISION}
    print(json.dumps(summary, indent=2), flush=True)
    if args.plan_only:
        return
    manifest = {
        "schemaVersion": 1, "repoId": REPO_ID, "revision": REVISION,
        "metadataSha256": sha256(args.metadata), "metadataFiles": len(metadata["files"]),
        "selectionRule": SELECTION_RULE, "summary": summary,
        "selected": [{"taskId": task["id"], "source": selected[task["id"]].source(),
                      **instructions.get(task["id"], {})}
                     for task in tasks if task["id"] in selected],
        "unavailable": unavailable,
    }
    if args.instructions:
        manifest["instructionReceiptSha256"] = sha256(args.instructions)
    write_json(dataset_root / "robodojo-demo-selection.json", manifest)
    records = {item["taskId"]: item for item in unavailable}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(export_task, task, selected[task["id"]], dataset_root, gallery_root,
                               instructions.get(task["id"])): task["id"]
                   for task in tasks if task["id"] in selected}
        for completed, future in enumerate(as_completed(futures), 1):
            task_id = futures[future]
            records[task_id] = future.result()
            print(f"Validated {completed}/{len(futures)} complete demonstration videos: {task_id}", flush=True)
    output = gallery_root / "artifacts/task-demos/robodojo.json"
    write_json(output, [records[task["id"]] for task in tasks])
    print(f"Wrote {len(records)} task records to {output}", flush=True)


if __name__ == "__main__":
    main()
