#!/usr/bin/env python3
"""Export one recorded LIBERO / RoboTwin training demonstration per gallery task.

Requires numpy, h5py, OpenCV, ffmpeg and ffprobe. No simulator is used. RoboTwin
uses the upstream decoder: its legacy JPEGs and marked RGB JPEGs need different
color handling. Only one HDF5 member is extracted from each ZIP, into --work-dir.

Example:
    python scripts/export_training_demos.py --benchmarks libero robotwin \
        --dataset-root /path/to/dataset --robotwin-repo /path/to/RoboTwin \
        --work-dir /path/on/ssd/demo-work

The resulting per-benchmark records are staged in artifacts/task-demos/ for the
gallery's combined data/task-demos.json manifest. Evaluation media is untouched.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterable
from urllib.parse import quote
import zipfile

import cv2
import h5py
import numpy as np


def sha256(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def load_robotwin_decoder(repo: Path):
    path = repo / "data/decode_image_bit.py"
    spec = importlib.util.spec_from_file_location("robotwin_image_codec", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import the official RoboTwin codec: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.decode_image_bit


def encode_video(
    frames: Iterable[np.ndarray], count: int, fps: float, video: Path, poster: Path
) -> dict:
    frames = iter(frames)
    first = next(frames)
    if first.dtype != np.uint8 or first.ndim != 3 or first.shape[-1] != 3:
        raise ValueError(f"Expected uint8 RGB frames, got {first.shape}/{first.dtype}")
    height, width = first.shape[:2]
    if width % 2 or height % 2:
        raise ValueError("Native dimensions must be even for yuv420p")
    video.parent.mkdir(parents=True, exist_ok=True)
    temporary = video.with_suffix(".partial.mp4")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
        "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "pipe:0", "-an", "-c:v", "libx264", "-threads", "2",
        "-preset", "medium", "-crf", "28", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(temporary),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    actual_count = 0
    try:
        assert process.stdin is not None
        process.stdin.write(np.ascontiguousarray(first).tobytes())
        actual_count = 1
        for frame in frames:
            if frame.dtype != np.uint8 or frame.shape != first.shape:
                raise ValueError(f"Inconsistent frame {actual_count}: {frame.shape}")
            process.stdin.write(np.ascontiguousarray(frame).tobytes())
            actual_count += 1
        process.stdin.close()
        assert process.stderr is not None
        error = process.stderr.read().decode(errors="replace")
        if process.wait():
            raise RuntimeError(f"ffmpeg failed for {video.name}: {error}")
    except BaseException:
        process.kill()
        process.wait()
        temporary.unlink(missing_ok=True)
        raise
    if actual_count != count:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"Frame count changed: {actual_count} != {count}")
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,pix_fmt,width,height,nb_read_frames,r_frame_rate,duration",
        "-of", "json", str(temporary),
    ]))["streams"][0]
    numerator, denominator = map(float, probe["r_frame_rate"].split("/"))
    if (probe["codec_name"] != "h264" or probe["pix_fmt"] != "yuv420p"
            or int(probe["nb_read_frames"]) != count
            or probe["width"] != width or probe["height"] != height
            or abs(numerator / denominator - fps) > 1e-6
            or abs(float(probe["duration"]) - count / fps) > 0.01):
        raise RuntimeError(f"Unexpected encoded video: {probe}")
    # Decode the entire stream, treating corruption as an error.
    subprocess.run([
        "ffmpeg", "-hide_banner", "-v", "error", "-xerror", "-i", str(temporary),
        "-f", "null", "-",
    ], check=True, capture_output=True)
    temporary.replace(video)
    poster_temporary = poster.with_suffix(".partial.jpg")
    if not cv2.imwrite(str(poster_temporary), cv2.cvtColor(first, cv2.COLOR_RGB2BGR),
                       [cv2.IMWRITE_JPEG_QUALITY, 90]):
        raise RuntimeError(f"Cannot write poster {poster}")
    poster_temporary.replace(poster)
    return {
        "width": width, "height": height, "frames": count,
        "fps": int(fps) if fps.is_integer() else fps,
        "durationSeconds": round(count / fps, 6),
        "videoBytes": video.stat().st_size,
        "videoSha256": sha256(video), "posterSha256": sha256(poster),
    }


def media_paths(root: Path, benchmark: str, task_id: str):
    relative = Path("media/demos") / benchmark / task_id
    return relative.with_suffix(".mp4"), relative.with_suffix(".jpg")


def source_record(manifest: dict, relative: str, dataset: str) -> dict:
    base = manifest.get("source") or "https://huggingface.co/datasets/" + manifest["repo_id"]
    entry = next(row for row in manifest["files"] if row["path"] == relative)
    return {
        "dataset": dataset,
        "url": f"{base}/blob/{manifest['revision']}/{quote(relative, safe='/')}",
        "revision": manifest["revision"], "relativePath": relative,
        "fileSha256": entry["lfs"]["oid"], "split": "train",
    }


def match_libero_file(root: Path, task: dict) -> Path:
    # Some long-horizon files have SCENE prefixes. Match the full instruction,
    # then also validate the HDF5 language metadata rather than relying on index.
    suffix = task["instruction"].replace(" ", "_") + "_demo.hdf5"
    matches = [p for p in (root / task["suite"]).glob("*.hdf5") if p.name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"Task {task['id']} has {len(matches)} matching training files")
    return matches[0]


def export_libero(task: dict, args, manifest: dict) -> dict:
    path = match_libero_file(args.dataset_root / "libero", task)
    video, poster = media_paths(args.gallery_root, "libero", task["id"])
    relative = path.relative_to(args.dataset_root / "libero").as_posix()
    source = source_record(manifest, relative, "LIBERO demonstrations")
    source.update({"episode": "demo_0", "taskName": path.stem.removesuffix("_demo"),
                   "cameraKey": "data/demo_0/obs/agentview_rgb"})
    with h5py.File(path, "r") as h:
        data = h["data"]
        instruction = json.loads(data.attrs["problem_info"])["language_instruction"]
        if instruction != task["instruction"]:
            raise ValueError(f"Instruction mismatch for {task['id']}")
        episode = data["demo_0"]
        if int(episode["dones"][-1]) != 1 or int(episode["rewards"][-1]) != 1:
            raise ValueError(f"Training episode is not marked successful: {path.name}")
        convention = data.attrs.get("macros_image_convention", "")
        if convention not in ("opengl", "opencv"):
            raise ValueError(f"Unknown image orientation: {convention!r}")
        fps = float(json.loads(data.attrs["env_args"])["env_kwargs"]["control_freq"])
        images = episode["obs/agentview_rgb"]
        # LIBERO's own VideoWriter flips OpenGL rows (video_utils.py).
        frames = (image[::-1] if convention == "opengl" else image for image in images)
        info = encode_video(frames, len(images), fps, args.gallery_root / video,
                            args.gallery_root / poster)
        source["imageOrientation"] = "vertical flip from OpenGL" if convention == "opengl" else "native"
    return {"taskId": task["id"], "benchmark": "libero", "status": "available",
            "instruction": instruction, "video": video.as_posix(), "poster": poster.as_posix(),
            **info, "cameras": ["Agent view"], "source": source}


def export_robotwin(task: dict, args, manifest: dict, decode_image_bit) -> dict:
    task_name = task["id"].removeprefix("robotwin_")
    relative = f"dataset/{task_name}/demo_clean.zip"
    path = args.dataset_root / "robotwin" / relative
    video, poster = media_paths(args.gallery_root, "robotwin", task["id"])
    source = source_record(manifest, relative, "RoboTwin 2.0 demonstrations")
    source.update({"taskName": task_name, "configuration": "demo_clean",
                   "episode": "episode_0000000", "cameraKey": "vision/cam_head/colors",
                   "imageOrientation": "native RGB via official decode_image_bit"})
    with tempfile.TemporaryDirectory(prefix=f"{task_name}-", dir=args.work_dir) as work:
        extracted = Path(work) / "episode_0000000.hdf5"
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist()
                       if name.endswith("/data/episode_0000000.hdf5")]
            if len(members) != 1:
                raise ValueError(f"Expected one first episode in {relative}, got {members}")
            source["archiveMember"] = members[0]
            with archive.open(members[0]) as incoming, extracted.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
        source["episodeSha256"] = sha256(extracted)
        with h5py.File(extracted, "r") as h:
            fps = float(h["additional_info/frequency"][()])
            if not 1 <= fps <= 120:
                raise ValueError(f"Unexpected recorded frequency {fps}")
            instructions = json.loads(h["instructions"][()])
            if not isinstance(instructions, list) or not instructions:
                raise ValueError(f"Missing episode language in {relative}")
            images = h["vision/cam_head/colors"]
            frames = (decode_image_bit(image) for image in images)
            info = encode_video(frames, len(images), fps, args.gallery_root / video,
                                args.gallery_root / poster)
    return {"taskId": task["id"], "benchmark": "robotwin", "status": "available",
            "instruction": instructions[0], "video": video.as_posix(), "poster": poster.as_posix(),
            **info, "cameras": ["Head camera"], "source": source}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", choices=["libero", "robotwin"], nargs="+",
                        default=["libero", "robotwin"])
    parser.add_argument("--gallery-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--robotwin-repo", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if "robotwin" in args.benchmarks and args.robotwin_repo is None:
        parser.error("--robotwin-repo is required for the official RGB decoder")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    gallery = read_json(args.gallery_root / "data/gallery.json")
    for benchmark in args.benchmarks:
        tasks = next(b["tasks"] for b in gallery["benchmarks"] if b["id"] == benchmark)
        manifest_name = "manifest.json" if benchmark == "libero" else "training_manifest.json"
        manifest = read_json(args.dataset_root / ".download-management" / benchmark / manifest_name)
        if benchmark == "libero":
            export = lambda task: export_libero(task, args, manifest)
        else:
            decoder = load_robotwin_decoder(args.robotwin_repo)
            export = lambda task: export_robotwin(task, args, manifest, decoder)
        records = []
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for record in pool.map(export, tasks):
                records.append(record)
                print(f"{benchmark} {len(records)}/{len(tasks)} {record['taskId']} "
                      f"{record['frames']} frames @ {record['fps']} fps "
                      f"{record['videoBytes']} bytes", flush=True)
        destination = args.gallery_root / "artifacts/task-demos" / f"{benchmark}.json"
        write_json(destination, records)
        print(f"Saved {len(records)} verified videos to {destination}", flush=True)


if __name__ == "__main__":
    main()
