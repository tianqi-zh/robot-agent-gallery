#!/usr/bin/env python3
"""Export explicitly allowed evaluation metadata and browser-ready episode videos.

Only the latest attempt of every planned episode is eligible. Failed policy
episodes and timeouts stay in the gallery. Source runs are always read-only.
Requires Python 3.10+, ffmpeg and ffprobe; no third-party Python packages.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
import re
import struct
import subprocess


RUNS = {
    "libero": "astra_libero_v5_calibrated_parallel10_r4",
    "robotwin": "robotwin_astra_firstpass_20260917",
}
SUITE_NAMES = {
    "libero_spatial": "LIBERO-Spatial",
    "libero_goal": "LIBERO-Goal",
    "libero_object": "LIBERO-Object",
    "libero_10": "LIBERO-Long",
    "robotwin": "RoboTwin",
}
ENCODING = {
    "codec": "h264", "pixelFormat": "yuv420p", "crf": 28,
    "maxRate": "600k", "bufferSize": "1200k", "preset": "medium",
    "fastStart": True, "resize": False, "preserveFramesAndFps": True,
}
VALID_STATUSES = {"success", "failure", "timeout"}


def read_json(path: Path):
    return json.loads(path.read_text())


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path):
    output = subprocess.check_output([
        "ffprobe", "-v", "error", "-threads", "1", "-select_streams", "v:0",
        "-count_frames", "-show_entries",
        "stream=codec_name,pix_fmt,width,height,avg_frame_rate,nb_read_frames,duration:format=duration",
        "-of", "json", str(path),
    ], text=True)
    data = json.loads(output)
    stream = data["streams"][0]
    return {
        "codec": stream["codec_name"], "pixelFormat": stream["pix_fmt"],
        "width": int(stream["width"]), "height": int(stream["height"]),
        "fps": str(Fraction(stream["avg_frame_rate"])),
        "frames": int(stream["nb_read_frames"]),
        "durationSeconds": float(stream.get("duration", data["format"]["duration"])),
    }


def is_faststart(path: Path) -> bool:
    """Check top-level MP4 atom order without loading media into memory."""
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


def title(text: str) -> str:
    replacements = {"qrcode": "QR code", "rgb": "RGB", "dustbin": "dustbin"}
    words = [replacements.get(word, word) for word in text.split("_")]
    humanized = " ".join(words)
    return humanized[:1].upper() + humanized[1:]


def robotwin_instruction(video: Path) -> str:
    with video.with_name("trajectory.jsonl").open() as stream:
        for line in stream:
            event = json.loads(line)
            if event.get("event") == "reset" and isinstance(event.get("language"), str):
                return event["language"]
    raise ValueError("Missing public RoboTwin reset instruction")


def aggregate(episodes, tasks):
    counts = Counter(episode["status"] for episode in episodes)
    return {
        "tasks": tasks, "episodes": len(episodes), "successes": counts["success"],
        "failures": counts["failure"] + counts["timeout"], "timeouts": counts["timeout"],
        "successRate": counts["success"] / len(episodes),
    }


def load_plan(source_root: Path, output_root: Path):
    gallery = {
        "schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "model": "gpt-6-astra", "evaluationDate": "2026-09-17", "benchmarks": [],
    }
    jobs = []
    provenance = []
    for benchmark_id, run_name in RUNS.items():
        run_dir = source_root / run_name
        manifest = read_json(run_dir / "manifest.json")
        summary = read_json(run_dir / "reports/summary.json")
        manifest_hash = manifest["manifest_sha256"]
        manifest_payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
        computed_hash = hashlib.sha256(json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert computed_hash == manifest_hash, "Source manifest changed after preparation"
        assert manifest_hash == summary["manifest_sha256"]
        assert manifest["config"]["model"] == gallery["model"]
        tasks = {}
        run_attempts = []
        for spec in manifest["episodes"]:
            key = spec["episode_key"]
            assert re.fullmatch(r"[a-z0-9_]+", key)
            attempts = sorted((run_dir / "episodes" / key).glob("attempt_[0-9][0-9][0-9]"))
            assert attempts, key
            result_path = attempts[-1] / "result.json"
            result = read_json(result_path)
            assert result["episode_key"] == key and result["manifest_sha256"] == manifest_hash
            assert result["status"] in VALID_STATUSES, (key, result["status"])
            assert bool(result["success"]) == (result["status"] == "success")
            env = result["environment"]
            assert not result["audit"].get("isolation_violation"), key
            assert bool(env["success"]) == (result["status"] == "success")
            video = Path(env["video"]["path"])
            assert video.is_file() and video.is_relative_to(attempts[-1])
            suite = spec.get("suite", "robotwin")
            task_id = f"{suite}_t{spec['task_id']:02d}" if benchmark_id == "libero" else f"robotwin_{spec['task_name']}"
            instruction = spec["language"] if benchmark_id == "libero" else robotwin_instruction(video)
            task = tasks.setdefault(task_id, {
                "id": task_id, "name": title(spec["task_name"]), "instruction": instruction,
                "suite": suite, "suiteName": SUITE_NAMES[suite], "episodes": [],
            })
            assert task["instruction"] == instruction
            metadata = env["video"]
            episode = {
                "id": key, "index": spec["rollout_id"], "status": result["status"],
                "seed": env["seed"], "initStateId": spec.get("init_state_id"),
                "steps": result["steps"], "maxSteps": spec["max_steps"],
                "toolCalls": env["tool_calls"], "wallSeconds": result["wall_seconds"],
                "durationSeconds": metadata["frames"] / metadata["fps"],
                "video": f"media/{benchmark_id}/{key}.mp4",
                "poster": f"media/{benchmark_id}/{key}.jpg",
                "width": metadata["width"], "height": metadata["height"], "frames": metadata["frames"],
            }
            task["episodes"].append(episode)
            previous = []
            for attempt in attempts[:-1]:
                old = read_json(attempt / "result.json")
                assert old["status"] not in VALID_STATUSES, (key, "policy outcome was retried")
                previous.append({"attempt": attempt.name, "status": old["status"], "resultSha256": sha256(attempt / "result.json")})
            selected = {"episode": key, "selectedAttempt": attempts[-1].name,
                        "resultSha256": sha256(result_path), "excludedAttempts": previous}
            run_attempts.append(selected)
            jobs.append({"source": video, "episode": episode, "benchmark": benchmark_id,
                         "expectedFps": str(Fraction(metadata["fps"])), "selection": selected,
                         "outputRoot": output_root})
        all_episodes = [episode for task in tasks.values() for episode in task["episodes"]]
        expected_tasks, expected_episodes = (40, 400) if benchmark_id == "libero" else (50, 50)
        assert len(tasks) == expected_tasks and len(all_episodes) == expected_episodes
        counts = aggregate(all_episodes, len(tasks))
        assert counts["successes"] == summary["overall"]["successes"]
        assert counts["failures"] == summary["overall"]["failures"]
        assert counts["timeouts"] == summary["overall"]["timeouts"]
        for task in tasks.values():
            expected_indices = list(range(10)) if benchmark_id == "libero" else [0]
            assert sorted(ep["index"] for ep in task["episodes"]) == expected_indices
            task_counts = aggregate(task["episodes"], 1)
            task.update({key: task_counts[key] for key in ("successes", "failures", "successRate")})
        suites = []
        for suite in dict.fromkeys(task["suite"] for task in tasks.values()):
            suite_tasks = [task for task in tasks.values() if task["suite"] == suite]
            suite_episodes = [episode for task in suite_tasks for episode in task["episodes"]]
            suites.append({"id": suite, "name": SUITE_NAMES[suite], **aggregate(suite_episodes, len(suite_tasks))})
        protocol = {
            "label": "10 initial states per task" if benchmark_id == "libero" else "First pass · 1 episode per task",
            "description": (
                "40 tasks across four suites, with initial states 0–9 for every task. "
                "Independent episodes use RGB images, robot proprioception and camera/robot calibration. "
                "Native simulator predicates determine success; failed policy episodes are retained."
                if benchmark_id == "libero" else
                "50 official tasks with demo_clean scenes and seen instructions, one valid seed per task. "
                "Expert validity screening is followed by a reset; the policy receives no expert actions. "
                "Independent RGB, robot proprioception and calibration; native task predicates determine success."
            ),
            "cameras": ["Agent view", "Wrist camera"] if benchmark_id == "libero" else ["Head camera", "Left wrist", "Right wrist"],
            "videoNote": (
                "20 fps: initial frame, 10 warmup frames, then every robot control step. "
                "Inference waiting time is omitted. Original frames and camera layout are preserved."
                if benchmark_id == "libero" else
                "10 fps: initial frame and one frame after each native policy action. "
                "Actions have variable physics duration, so playback time is not simulation time. "
                "Original frames and all three camera views are preserved."
            ),
            "stepsLabel": "Control steps" if benchmark_id == "libero" else "Native actions",
            "episodesPerTask": 10 if benchmark_id == "libero" else 1,
        }
        gallery["benchmarks"].append({
            "id": benchmark_id, "name": "LIBERO" if benchmark_id == "libero" else "RoboTwin",
            "summary": counts, "suites": suites, "protocol": protocol,
            "provenance": {"run": run_name, "manifestSha256": manifest_hash}, "tasks": list(tasks.values()),
        })
        provenance.append({"benchmark": benchmark_id, "run": run_name,
                           "manifestSha256": manifest_hash, "selectedEpisodes": len(all_episodes),
                           "excludedAttemptCount": sum(len(item["excludedAttempts"]) for item in run_attempts),
                           "attemptSelection": run_attempts})
    return gallery, jobs, provenance


def publish_metadata(output_root: Path, gallery):
    write_json(output_root / "data/gallery.json", gallery)
    fields = ["benchmark", "suite", "task", "instruction", "episode", "rolloutIndex", "status", "seed",
              "initStateId", "steps", "maxSteps", "toolCalls", "wallSeconds", "durationSeconds", "frames", "video", "poster"]
    with (output_root / "data/episodes.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for benchmark in gallery["benchmarks"]:
            for task in benchmark["tasks"]:
                for episode in task["episodes"]:
                    writer.writerow({
                        "benchmark": benchmark["id"], "suite": task["suite"], "task": task["id"],
                        "instruction": task["instruction"], "episode": episode["id"], "rolloutIndex": episode["index"],
                        **{key: episode[key] for key in fields[6:]},
                    })


def encode(job, prior):
    episode = job["episode"]
    source = job["source"]
    output_root = job["outputRoot"]
    video = output_root / episode["video"]
    poster = output_root / episode["poster"]
    video.parent.mkdir(parents=True, exist_ok=True)
    source_hash = sha256(source)
    if (prior and prior.get("sourceSha256") == source_hash and video.is_file() and poster.is_file()
            and prior.get("videoSha256") == sha256(video) and prior.get("posterSha256") == sha256(poster)):
        for field in ("width", "height", "frames"):
            assert prior[field] == episode[field], (episode["id"], field)
        assert prior["fps"] == job["expectedFps"]
        return prior
    source_info = probe(source)
    for field in ("width", "height", "frames"):
        assert source_info[field] == episode[field], (episode["id"], field)
    assert source_info["fps"] == job["expectedFps"]
    temporary = video.with_suffix(".encoding.mp4")
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "1", "-filter_threads", "1",
        "-i", str(source), "-map", "0:v:0", "-an", "-map_metadata", "-1", "-map_chapters", "-1",
        "-c:v", "libx264", "-threads", "2", "-preset", ENCODING["preset"],
        "-crf", str(ENCODING["crf"]), "-maxrate", ENCODING["maxRate"], "-bufsize", ENCODING["bufferSize"],
        "-pix_fmt", "yuv420p", "-fps_mode", "passthrough", "-movflags", "+faststart", str(temporary),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    encoded = probe(temporary)
    for field in ("width", "height", "frames", "fps"):
        assert encoded[field] == source_info[field], (episode["id"], field)
    assert abs(encoded["durationSeconds"] - source_info["durationSeconds"]) < 0.001
    assert encoded["codec"] == "h264" and encoded["pixelFormat"] == "yuv420p"
    assert is_faststart(temporary)
    temporary.replace(video)
    poster_frame = episode["frames"] // 2
    poster_temporary = poster.with_suffix(".encoding.jpg")
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-threads", "1",
        "-i", str(video), "-vf", f"select=eq(n\\,{poster_frame}),scale=min(1024\\,iw):-2",
        "-filter_threads", "1", "-frames:v", "1", "-q:v", "4", "-threads", "1",
        "-map_metadata", "-1", str(poster_temporary),
    ], check=True, capture_output=True, text=True)
    poster_temporary.replace(poster)
    assert sha256(source) == source_hash, "Source changed during export"
    return {
        "episode": episode["id"], "benchmark": job["benchmark"],
        "sourceSha256": source_hash, "sourceBytes": source.stat().st_size,
        "video": episode["video"], "videoSha256": sha256(video), "videoBytes": video.stat().st_size,
        "poster": episode["poster"], "posterSha256": sha256(poster), "posterBytes": poster.stat().st_size,
        "posterFrame": poster_frame, **encoded, "fastStart": True, "verified": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="Directory containing both source run directories")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--jobs", type=int, default=6, choices=range(1, 7))
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--sample", type=int, default=0, help="Encode a deterministic representative subset first")
    args = parser.parse_args()
    args.source_root = args.source_root.resolve()
    args.output = args.output.resolve()
    assert (args.output != args.source_root
            and not args.source_root.is_relative_to(args.output)
            and not args.output.is_relative_to(args.source_root)), "Source and output directories must be separate"
    gallery, jobs, provenance = load_plan(args.source_root, args.output)
    publish_metadata(args.output, gallery)
    report_path = args.output / "data/export-report.json"
    prior_report = read_json(report_path) if report_path.exists() else {}
    prior = {item["episode"]: item for item in prior_report.get("media", [])} if prior_report.get("encoding") == ENCODING else {}
    report = {
        "schemaVersion": 1, "generatedAt": gallery["generatedAt"], "complete": False,
        "selectionRule": "Latest attempt for every planned episode. Policy failures and timeouts are included; only earlier infrastructure/interruption attempts are excluded.",
        "encoding": ENCODING, "runs": provenance, "media": list(prior.values()),
        "expectedEpisodes": len(jobs), "verifiedEpisodes": len(prior),
        "sourceBytes": sum(job["source"].stat().st_size for job in jobs),
    }
    write_json(report_path, report)
    print(json.dumps({"planned": len(jobs), "sourceBytes": report["sourceBytes"],
                      "summaries": {benchmark["id"]: benchmark["summary"] for benchmark in gallery["benchmarks"]}}), flush=True)
    if args.plan_only:
        return
    selected_jobs = jobs
    if args.sample:
        # Include each benchmark, short and long episodes, then uniformly spaced episodes.
        selected = [jobs[0], jobs[-1], max(jobs, key=lambda job: job["episode"]["durationSeconds"]),
                    max((job for job in jobs if job["benchmark"] == "robotwin"), key=lambda job: job["episode"]["durationSeconds"])]
        selected += [jobs[round(index * (len(jobs) - 1) / max(1, args.sample - 1))] for index in range(args.sample)]
        selected_jobs = list({job["episode"]["id"]: job for job in selected}.values())[:args.sample]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {executor.submit(encode, job, prior.get(job["episode"]["id"])): job for job in selected_jobs}
        for number, future in enumerate(concurrent.futures.as_completed(futures), 1):
            entry = future.result()
            prior[entry["episode"]] = entry
            report["media"] = sorted(prior.values(), key=lambda item: (item["benchmark"], item["episode"]))
            report["verifiedEpisodes"] = len(prior)
            report["videoBytes"] = sum(item["videoBytes"] for item in prior.values())
            report["posterBytes"] = sum(item["posterBytes"] for item in prior.values())
            write_json(report_path, report)
            if number % 10 == 0 or number <= 4 or number == len(selected_jobs):
                print(json.dumps({"completed": number, "batch": len(selected_jobs), "verifiedTotal": len(prior),
                                  "videoMiB": round(report["videoBytes"] / 1024**2, 2), "episode": entry["episode"]}), flush=True)
    expected_ids = {job["episode"]["id"] for job in jobs}
    report["complete"] = len(selected_jobs) == len(jobs) and set(prior) == expected_ids
    report["publishedMediaBytes"] = report.get("videoBytes", 0) + report.get("posterBytes", 0)
    assert report["publishedMediaBytes"] < 800_000_000, "Published media exceeds export size budget"
    report["validation"] = {
        "expectedEpisodes": len(jobs), "verifiedEpisodes": len(prior),
        "decodedFrameCount": sum(item["frames"] for item in prior.values()),
        "allFramesAndFpsPreserved": all(item["verified"] for item in prior.values()),
        "allBrowserH264Yuv420pFastStart": all(item["codec"] == "h264" and item["pixelFormat"] == "yuv420p" and item["fastStart"] for item in prior.values()),
        "sourceFilesUnmodified": True, "within800MBMediaBudget": True,
    }
    write_json(report_path, report)
    publish_metadata(args.output, gallery)
    print(json.dumps({key: report[key] for key in ("complete", "verifiedEpisodes", "publishedMediaBytes", "validation")}), flush=True)


if __name__ == "__main__":
    main()
