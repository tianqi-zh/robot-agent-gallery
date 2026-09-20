#!/usr/bin/env python3
"""Import the RoboTwin 10-rollout NVIDIA Responses run into the static gallery.

The source run contains 500 planned episodes. Only episodes with a scored
success/failure result and a real rollout MP4 are imported as playable gallery
episodes. Simulation/API infrastructure errors remain documented in the
provenance report but are not inserted as playable cards.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ID = "robotwin_nvidia10"
SUITE_ID = "robotwin_nvidia10"
RUN_NAME = "robotwin_nvidia10_full_v1"
EVALUATION_DATE = "2026-09-19"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def title(text: str) -> str:
    replacements = {"qrcode": "QR code", "rgb": "RGB", "dustbin": "dustbin"}
    words = [replacements.get(word, word) for word in text.split("_")]
    value = " ".join(words)
    return value[:1].upper() + value[1:]


def probe(path: Path) -> dict:
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-threads", "1", "-select_streams", "v:0",
        "-count_frames", "-show_entries",
        "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_read_frames,duration:format=duration",
        "-of", "json", str(path),
    ], text=True))
    stream = data["streams"][0]
    return {
        "codec": stream["codec_name"],
        "pixelFormat": stream["pix_fmt"],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": str(Fraction(stream["avg_frame_rate"])),
        "frames": int(stream["nb_read_frames"]),
        "durationSeconds": float(stream.get("duration", data["format"]["duration"])),
    }


def is_faststart(path: Path) -> bool:
    atoms = []
    with path.open("rb") as stream:
        while header := stream.read(8):
            if len(header) != 8:
                return False
            size, kind = struct.unpack(">I4s", header)
            header_size = 8
            if size == 1:
                extended = stream.read(8)
                if len(extended) != 8:
                    return False
                size = struct.unpack(">Q", extended)[0]
                header_size = 16
            atoms.append(kind)
            if kind == b"mdat":
                return b"moov" in atoms
            if size == 0 or size < header_size:
                return False
            stream.seek(size - header_size, 1)
    return False


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def encode_video(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return
    tmp = target.with_suffix(".tmp.mp4")
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(source),
        "-map", "0:v:0", "-c:v", "copy", "-movflags", "+faststart", str(tmp),
    ])
    tmp.replace(target)


def make_poster(video: Path, target: Path, frame: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return
    tmp = target.with_suffix(".tmp.jpg")
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", "-q:v", "4", str(tmp),
    ])
    tmp.replace(target)


def counts(episodes: list[dict], tasks: int) -> dict:
    counter = Counter(episode["status"] for episode in episodes)
    total = len(episodes)
    return {
        "tasks": tasks,
        "episodes": total,
        "successes": counter["success"],
        "failures": counter["failure"] + counter["timeout"],
        "timeouts": counter["timeout"],
        "successRate": counter["success"] / total if total else 0,
    }


def clean_existing(gallery: dict, report: dict, demos: dict) -> None:
    gallery["benchmarks"] = [b for b in gallery["benchmarks"] if b["id"] != BENCHMARK_ID]
    report["media"] = [m for m in report["media"] if m.get("benchmark") != BENCHMARK_ID]
    report["runs"] = [r for r in report["runs"] if r.get("benchmark") != BENCHMARK_ID]
    if "videoHosting" in report:
        report["videoHosting"].pop(BENCHMARK_ID, None)
    tasks = demos.get("tasks", {})
    for key in list(tasks):
        if tasks[key].get("benchmark") == BENCHMARK_ID or key.startswith(f"{BENCHMARK_ID}_"):
            del tasks[key]


def selected_attempt(result_path: Path) -> str:
    return result_path.parent.name


def resolved_instruction(source_video: Path) -> str:
    """Read the concrete RoboTwin language instruction resolved for this rollout."""
    for name in ("result.json", "state.json"):
        path = source_video.with_name(name)
        if not path.is_file():
            continue
        language = read_json(path).get("language")
        if isinstance(language, str) and language.strip() and "{" not in language:
            if re.search(r"\bsk-[A-Za-z0-9_-]{20,}\b", language):
                raise ValueError(f"Unsafe instruction in {path}")
            return language.strip()
    raise ValueError(f"Missing resolved RoboTwin instruction next to {source_video}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gallery-root", type=Path, default=ROOT)
    args = parser.parse_args()

    root = args.gallery_root.resolve()
    run_dir = args.run_dir.resolve()
    manifest = read_json(run_dir / "manifest.json")
    manifest_hash = manifest["manifest_sha256"]
    specs = {item["episode_key"]: item for item in manifest["episodes"]}

    gallery = read_json(root / "data/gallery.json")
    report = read_json(root / "data/export-report.json")
    demos = read_json(root / "data/task-demos.json")
    clean_existing(gallery, report, demos)

    media_dir = root / "media" / BENCHMARK_ID
    media_dir.mkdir(parents=True, exist_ok=True)

    result_paths = sorted((run_dir / "episodes").glob("*/attempt_*_nvidia_api/result.nvidia_responses.json"))
    result_keys = set()
    tasks: dict[str, dict] = {}
    jobs = []
    selections = []
    skipped = []

    for result_path in result_paths:
        result = read_json(result_path)
        result_keys.add(result.get("episode_key"))
        status = result["status"]
        env = result.get("environment", {})
        video_info = env.get("video") or {}
        source_video = Path(video_info.get("path", ""))
        if status not in {"success", "failure"} or not source_video.is_file():
            skipped.append({
                "sourceEpisodeKey": result.get("episode_key"),
                "status": status,
                "reason": result.get("reason"),
                "environmentError": env.get("error"),
                "selectedAttempt": selected_attempt(result_path),
                "resultSha256": sha256(result_path),
            })
            continue

        source_key = result["episode_key"]
        spec = specs[source_key]
        task_name = result["task_name"]
        instruction = resolved_instruction(source_video)
        task_id = f"{BENCHMARK_ID}_{task_name}"
        episode_id = f"{BENCHMARK_ID}_{source_key}"
        task = tasks.setdefault(task_id, {
            "id": task_id,
            "name": title(task_name),
            "instruction": instruction,
            "suite": SUITE_ID,
            "suiteName": "RoboTwin 10-rollout",
            "episodes": [],
        })

        target_video = root / "media" / BENCHMARK_ID / f"{episode_id}.mp4"
        target_poster = root / "media" / BENCHMARK_ID / f"{episode_id}.jpg"
        encode_video(source_video, target_video)
        metadata = probe(target_video)
        poster_frame = max(0, metadata["frames"] // 2)
        make_poster(target_video, target_poster, poster_frame)

        status_public = "success" if result["success"] else "failure"
        episode = {
            "id": episode_id,
            "sourceEpisodeKey": source_key,
            "index": int(spec["rollout_id"]),
            "instruction": instruction,
            "status": status_public,
            "seed": int(env["seed"]),
            "initStateId": None,
            "steps": int(result.get("steps") or env.get("steps") or 0),
            "maxSteps": int(spec["max_steps"]),
            "toolCalls": int(env.get("tool_calls") or result.get("tool_calls") or 0),
            "wallSeconds": result["wall_seconds"],
            "durationSeconds": metadata["durationSeconds"],
            "video": f"media/{BENCHMARK_ID}/{episode_id}.mp4",
            "poster": f"media/{BENCHMARK_ID}/{episode_id}.jpg",
            "width": metadata["width"],
            "height": metadata["height"],
            "frames": metadata["frames"],
        }
        task["episodes"].append(episode)

        source_sha = sha256(source_video)
        media_record = {
            "episode": episode_id,
            "benchmark": BENCHMARK_ID,
            "sourceEpisodeKey": source_key,
            "sourceSha256": source_sha,
            "sourceBytes": source_video.stat().st_size,
            "video": episode["video"],
            "videoSha256": sha256(target_video),
            "videoBytes": target_video.stat().st_size,
            "poster": episode["poster"],
            "posterSha256": sha256(target_poster),
            "posterBytes": target_poster.stat().st_size,
            "posterFrame": poster_frame,
            "codec": metadata["codec"],
            "pixelFormat": metadata["pixelFormat"],
            "width": metadata["width"],
            "height": metadata["height"],
            "fps": metadata["fps"],
            "frames": metadata["frames"],
            "durationSeconds": metadata["durationSeconds"],
            "fastStart": is_faststart(target_video),
            "verified": True,
        }
        report["media"].append(media_record)
        selection = {
            "episode": episode_id,
            "sourceEpisodeKey": source_key,
            "selectedAttempt": selected_attempt(result_path),
            "resultSha256": sha256(result_path),
            "sourceVideoSha256": source_sha,
            "status": status_public,
            "excludedAttempts": [],
        }
        selections.append(selection)
        jobs.append((episode, media_record))

    for task in tasks.values():
        task["episodes"].sort(key=lambda item: item["index"])
        task["instruction"] = task["episodes"][0]["instruction"]
        task_counts = counts(task["episodes"], 1)
        task.update({key: task_counts[key] for key in ("successes", "failures", "successRate")})

    all_episodes = [episode for task in tasks.values() for episode in task["episodes"]]
    suite_counts = counts(all_episodes, len(tasks))
    benchmark = {
        "id": BENCHMARK_ID,
        "name": "RoboTwin 10-rollout",
        "evaluationDate": EVALUATION_DATE,
        "summary": suite_counts,
        "suites": [{"id": SUITE_ID, "name": "RoboTwin 10-rollout", **suite_counts}],
        "protocol": {
            "label": "Up to 10 episodes per task · playable scored rollouts only",
            "description": (
                "50 official RoboTwin tasks were evaluated with ten requested seeds per task through the "
                "NVIDIA Responses API model route. This public view includes the 482 scored success/failure "
                "episodes that produced complete MP4 recordings; 17 simulator errors and one API content-policy "
                "block are retained only in provenance."
            ),
            "cameras": ["Head camera", "Left wrist", "Right wrist"],
            "videoNote": (
                "10 fps: initial frame and one frame after each native policy action. "
                "Actions have variable physics duration, so playback time is not simulation time. "
                "Only episodes with complete recorded MP4s are shown."
            ),
            "stepsLabel": "Native actions",
            "episodesPerTask": 10,
        },
        "provenance": {
            "run": RUN_NAME,
            "manifestSha256": manifest_hash,
            "plannedEpisodes": len(manifest["episodes"]),
            "terminalResults": len(result_paths),
            "playableEpisodes": len(all_episodes),
            "excludedEpisodeCount": len(skipped) + (len(manifest["episodes"]) - len(result_paths)),
        },
        "tasks": [tasks[key] for key in sorted(tasks)],
    }
    gallery["benchmarks"].append(benchmark)
    gallery["evaluationDate"] = EVALUATION_DATE
    dates = sorted({*(gallery.get("evaluationDates") or []), EVALUATION_DATE})
    if "2026-09-17" not in dates:
        dates.insert(0, "2026-09-17")
    gallery["evaluationDates"] = dates
    gallery["generatedAt"] = datetime.now(timezone.utc).isoformat()

    report["runs"].append({
        "benchmark": BENCHMARK_ID,
        "run": RUN_NAME,
        "manifestSha256": manifest_hash,
        "selectedEpisodes": len(all_episodes),
        "excludedAttemptCount": len(skipped) + (len(manifest["episodes"]) - len(result_paths)),
        "skippedEpisodes": skipped + [
            {"sourceEpisodeKey": key, "status": "missing_terminal_result"}
            for key in sorted(specs) if key not in result_keys
        ],
        "attemptSelection": selections,
        "instructionSource": "Episode-specific RoboTwin resolved language from frames/*/result.json field language.",
    })
    report["generatedAt"] = gallery["generatedAt"]
    report["expectedEpisodes"] = sum(b["summary"]["episodes"] for b in gallery["benchmarks"])
    report["verifiedEpisodes"] = report["expectedEpisodes"]
    report["videoBytes"] = sum(item["videoBytes"] for item in report["media"])
    report["posterBytes"] = sum(item["posterBytes"] for item in report["media"])
    report["publishedMediaBytes"] = report["videoBytes"] + report["posterBytes"]
    report["sourceBytes"] = sum(item["sourceBytes"] for item in report["media"])
    report["externalVideoBytes"] = sum(item["videoBytes"] for item in report["media"] if item["benchmark"] == "robocasa")
    report["pagesMediaBytes"] = report["publishedMediaBytes"] - report["externalVideoBytes"]
    report["validation"]["decodedFrameCount"] = sum(item["frames"] for item in report["media"])
    report["selectionRule"] = (
        report["selectionRule"].rstrip()
        + " RoboTwin 10-rollout publishes every scored success/failure episode from "
        + "robotwin_nvidia10_full_v1 that produced a complete MP4; simulator/API infrastructure errors are excluded from playable media."
    )

    demo_tasks = demos.setdefault("tasks", {})
    for task in benchmark["tasks"]:
        demo_tasks[task["id"]] = {
            "taskId": task["id"],
            "benchmark": BENCHMARK_ID,
            "status": "unavailable",
            "reason": "This derived 10-rollout evaluation reuses the RoboTwin task family; no separate training-demo asset is imported for the derived benchmark entry.",
            "source": {
                "dataset": "RoboTwin 2.0 demonstrations",
                "url": "https://robotwin-platform.github.io/",
            },
        }
    coverage = {}
    for record in demo_tasks.values():
        item = coverage.setdefault(record["benchmark"], {"tasks": 0, "available": 0, "unavailable": 0})
        item["tasks"] += 1
        item[record["status"]] += 1
    demos["coverage"] = coverage

    write_json(root / "data/gallery.json", gallery)
    write_json(root / "data/export-report.json", report)
    write_json(root / "data/task-demos.json", demos)

    fields = ["benchmark", "suite", "task", "instruction", "episode", "rolloutIndex", "status", "seed",
              "initStateId", "steps", "maxSteps", "toolCalls", "wallSeconds", "durationSeconds", "frames",
              "video", "poster", "remoteVideo"]
    with (root / "data/episodes.csv").open("w", encoding="utf-8", newline="") as stream:
        import csv
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for item in gallery["benchmarks"]:
            for task in item["tasks"]:
                for episode in task["episodes"]:
                    writer.writerow({
                        "benchmark": item["id"],
                        "suite": task["suite"],
                        "task": task["id"],
                        "instruction": episode.get("instruction", task["instruction"]),
                        "episode": episode["id"],
                        "rolloutIndex": episode["index"],
                        "status": episode["status"],
                        "seed": episode["seed"],
                        "initStateId": episode["initStateId"],
                        "steps": episode["steps"],
                        "maxSteps": episode["maxSteps"],
                        "toolCalls": episode["toolCalls"],
                        "wallSeconds": episode["wallSeconds"],
                        "durationSeconds": episode["durationSeconds"],
                        "frames": episode["frames"],
                        "video": episode["video"],
                        "poster": episode["poster"],
                        "remoteVideo": episode.get("remoteVideo"),
                    })

    print(json.dumps({
        "benchmark": BENCHMARK_ID,
        "tasks": len(tasks),
        "episodes": len(all_episodes),
        "successes": suite_counts["successes"],
        "failures": suite_counts["failures"],
        "skipped": len(skipped) + (len(manifest["episodes"]) - len(result_paths)),
        "mediaBytes": sum(item["videoBytes"] + item["posterBytes"] for _, item in jobs),
    }, indent=2))


if __name__ == "__main__":
    main()
