#!/usr/bin/env python3
"""Validate the complete public gallery with the Python standard library."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {".git", "node_modules", "_site", "artifacts", ".venv", "__pycache__", ".gallery-cache"}
MAX_SITE_BYTES = 1_000_000_000
MAX_FILE_BYTES = 100_000_000
EXPECTED_SUITES = {"libero_spatial": 95, "libero_goal": 79, "libero_object": 89, "libero_10": 59}
EXPECTED_RUNS = {
    "libero": ("astra_libero_v5_calibrated_parallel10_r4",
               "df08694520ff7ea3e9bfee061a29223e46c4db76bc54a07e637cbfcbe93f42f8"),
    "robotwin": ("robotwin_astra_firstpass_20260917",
                 "8f0b9bfc28b7e2dccc7fe7a056114f1b7d2fdbf36e4bcbf72771931c5a9c6c38"),
    "robocasa": ("robocasa365_astra_firstpass_20260918",
                 "3a2a7f6939e18b5ee3fb6d6bac10d8f2f8704cd422d91efc8e56a038cf28c12c"),
}
PRIVATE_KEYS = {
    "auth", "authorization", "authentication", "credentials", "credential", "apikey",
    "accesstoken", "refreshtoken", "idtoken", "bearertoken", "secret", "password",
    "thread", "threads", "threadid", "conversation", "conversations", "conversationid",
    "codexhome", "workspace", "workspacedir", "rawlogs", "rawevents", "reasoning",
    "reasoningcontent", "chainofthought", "transcript", "stdout", "stderr", "prompt",
    "systemprompt", "messages", "oauth", "authorizationheader", "eventlog", "codexevents",
}


class ValidationError(Exception):
    """An exported asset does not satisfy the publication contract."""


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValidationError(f"Cannot read JSON {path.name}: {exc}") from exc


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f"{label} must be an integer >= {minimum}")
    return value


def public_metadata(value, location="data"):
    """Check public JSON without printing potentially private values in errors."""
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            require(normalized not in PRIVATE_KEYS, f"Private metadata key at {location}")
            public_metadata(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            public_metadata(child, f"{location}[{index}]")
    elif isinstance(value, str):
        require(not re.search(r"(?:^|[\s\"'=])/(?:home|playpen|tmp|Users|root|mnt|private)/", value),
                f"Machine-local path at {location}")
        require(not value.startswith(("/", "file:", "\\\\")) and not re.match(r"^[A-Za-z]:[\\/]", value),
                f"Absolute local path at {location}")
        require(not re.search(r"\bsk-[A-Za-z0-9_-]{20,}\b", value), f"Possible secret at {location}")
        require(not any(marker in value.lower() for marker in ("auth.json", "codex_home", "codex-events.jsonl")),
                f"Private artifact reference at {location}")
    elif type(value) is float:
        require(math.isfinite(value), f"Non-finite metadata number at {location}")


def local_asset(root, relative, label, *, allow_missing=False):
    require(isinstance(relative, str) and relative, f"Missing {label} path")
    path = PurePosixPath(relative)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in relative
            and ":" not in relative and "?" not in relative and "#" not in relative,
            f"{label} must be a plain repository-relative path")
    require(path.parts[0] in {"media", "assets"}, f"{label} must be a public media asset")
    candidate = root.joinpath(*path.parts)
    require(allow_missing or candidate.is_file(), f"Missing {label}: {relative}")
    require(not candidate.is_symlink() and candidate.resolve().is_relative_to(root.resolve()),
            f"Unsafe {label}: {relative}")
    return candidate


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_tree(root, external_media=()):
    total, site_total, files = 0, 0, 0
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts):
            continue
        require(not path.is_symlink(), f"Symlinks are not allowed: {relative.as_posix()}")
        if path.is_file():
            size = path.stat().st_size
            external = relative.as_posix() in external_media
            require(size < (2 * 1024**3 if external else MAX_FILE_BYTES),
                    f"File exceeds its hosting limit: {relative.as_posix()}")
            total += size
            if not external:
                site_total += size
            files += 1
    require(site_total < MAX_SITE_BYTES, f"Pages gallery reaches 1 GB: {site_total} bytes")
    return {"files": files, "bytes": total, "siteBytes": site_total}


def probe_video(item):
    path, expected = item
    label = str(path).rsplit("/", 1)[-1]
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,pix_fmt,width,height,nb_read_frames,avg_frame_rate", "-of", "json", str(path)],
        check=False, capture_output=True, text=True, timeout=120,
    )
    require(completed.returncode == 0 and not completed.stderr.strip(), f"Video decode failed: {label}")
    try:
        streams = json.loads(completed.stdout)["streams"]
        require(len(streams) == 1, f"Expected one video stream: {label}")
        stream = streams[0]
        require(stream["codec_name"] == "h264", f"Expected H.264: {label}")
        require(stream["pix_fmt"] == "yuv420p", f"Expected yuv420p: {label}")
        require(stream["width"] == expected["width"] and stream["height"] == expected["height"],
                f"Video dimensions differ from metadata: {label}")
        frames = int(stream["nb_read_frames"])
        require(frames == expected["frames"], f"Video frame count differs from source mapping: {label}")
        numerator, denominator = map(int, stream["avg_frame_rate"].split("/"))
        require(denominator > 0 and abs(numerator / denominator - expected["fps"]) < 1e-8,
                f"Video frame rate differs from metadata: {label}")
        return frames
    except (KeyError, ValueError, TypeError) as exc:
        raise ValidationError(f"Incomplete video metadata: {label}") from exc


def counts(episodes, tasks=None):
    statuses = Counter(episode["status"] for episode in episodes)
    result = {
        "episodes": len(episodes), "successes": statuses["success"],
        "failures": statuses["failure"] + statuses["timeout"], "timeouts": statuses["timeout"],
        "successRate": statuses["success"] / len(episodes) if episodes else 0,
    }
    if tasks is not None:
        result["tasks"] = tasks
    return result


def check_summary(actual, expected, label, keys=None):
    require(isinstance(actual, dict), f"Missing {label}")
    for key in keys or expected:
        require(actual.get(key) == expected[key], f"Wrong {label}.{key}: expected {expected[key]}")


def check_digest(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), f"Invalid {label} fingerprint")


def validate_gallery(root, *, check_interface=True, require_robocasa=False, release_assets=None):
    required_files = ("index.html", "app.js", "styles.css", ".nojekyll", "METHODOLOGY.md") if check_interface else ()
    for filename in required_files:
        require((root / filename).is_file(), f"Required public file is missing: {filename}")
    require({path.relative_to(root / "data").as_posix() for path in (root / "data").rglob("*") if path.is_file()}
            == {"gallery.json", "episodes.csv", "export-report.json"},
            "The public data directory contains missing or unexpected files")
    gallery = read_json(root / "data/gallery.json")
    report = read_json(root / "data/export-report.json")
    for path in (root / "data").rglob("*.json"):
        public_metadata(read_json(path), path.relative_to(root).as_posix())
    require(gallery.get("schemaVersion") == 1 and report.get("schemaVersion") == 1, "Unsupported schema version")
    require(gallery.get("model") == "gpt-6-astra", "Unexpected model")
    require(report.get("complete") is True, "The media export is not complete")
    benchmarks = gallery["benchmarks"]
    benchmark_ids = {item["id"] for item in benchmarks}
    has_robocasa = "robocasa" in benchmark_ids
    require(release_assets is None or has_robocasa, "Release validation requires RoboCasa365")
    expected_benchmarks = {"libero", "robotwin"} | ({"robocasa"} if has_robocasa else set())
    require(benchmark_ids == expected_benchmarks and len(benchmarks) == len(expected_benchmarks),
            "Expected LIBERO and RoboTwin, with the complete RoboCasa365 collection when present")
    require(not require_robocasa or has_robocasa, "The complete RoboCasa365 collection is required")
    expected_episodes, expected_tasks_total = (815, 455) if has_robocasa else (450, 90)
    require(gallery.get("evaluationDate") == ("2026-09-18" if has_robocasa else "2026-09-17"),
            "Unexpected evaluation date")
    if has_robocasa:
        require(gallery.get("evaluationDates") == ["2026-09-17", "2026-09-18"], "Incorrect evaluation dates")
    require(report.get("expectedEpisodes") == expected_episodes and report.get("verifiedEpisodes") == expected_episodes,
            f"The export must contain {expected_episodes} verified episodes")
    episodes, task_ids, media_paths, summaries = {}, set(), set(), {}
    benchmark_by_id = {item["id"]: item for item in benchmarks}
    external_media = set()
    if has_robocasa:
        from release_media import RELEASE_HOSTING, remote_video_url

        require(report.get("videoHosting") == {"robocasa": RELEASE_HOSTING}
                and benchmark_by_id["robocasa"].get("videoHosting") == RELEASE_HOSTING,
                "Incorrect RoboCasa video hosting declaration")
        external_media = {episode["video"] for task in benchmark_by_id["robocasa"]["tasks"] for episode in task["episodes"]}
    tree = check_tree(root, external_media)
    for benchmark in benchmarks:
        benchmark_id = benchmark["id"]
        is_libero = benchmark_id == "libero"
        is_robocasa = benchmark_id == "robocasa"
        require(is_robocasa or "videoHosting" not in benchmark, "Unexpected external hosting for a historical benchmark")
        if has_robocasa:
            require(benchmark.get("evaluationDate") == ("2026-09-18" if is_robocasa else "2026-09-17"),
                    f"Incorrect evaluation date: {benchmark_id}")
        expected_tasks, per_task = {"libero": (40, 10), "robotwin": (50, 1), "robocasa": (365, 1)}[benchmark_id]
        tasks = benchmark["tasks"]
        require(len(tasks) == expected_tasks, f"Wrong task count for {benchmark_id}")
        require(benchmark["protocol"]["episodesPerTask"] == per_task, f"Wrong sampling for {benchmark_id}")
        check_digest(benchmark["provenance"]["manifestSha256"], f"{benchmark_id} manifest")
        require((benchmark["provenance"]["run"], benchmark["provenance"]["manifestSha256"]) == EXPECTED_RUNS[benchmark_id],
                f"Unexpected frozen source run for {benchmark_id}")
        expected_suites = set(EXPECTED_SUITES) if is_libero else ({"robocasa_atomic", "robocasa_composite"} if is_robocasa else {"robotwin"})
        suites = benchmark["suites"]
        require(len(suites) == len(expected_suites) and {item["id"] for item in suites} == expected_suites,
                f"Wrong suites for {benchmark_id}")
        all_episodes = []
        for task in tasks:
            task_id = task["id"]
            require(isinstance(task_id, str) and re.fullmatch(r"[a-z0-9_]+", task_id), "Invalid task ID")
            require(task_id not in task_ids, f"Duplicate task ID: {task_id}")
            task_ids.add(task_id)
            require(task["suite"] in expected_suites, f"Wrong suite for {task_id}")
            require(isinstance(task["instruction"], str) and task["instruction"].strip(), f"Missing instruction: {task_id}")
            task_episodes = task["episodes"]
            require(len(task_episodes) == per_task, f"Wrong episode count for {task_id}")
            require({item["index"] for item in task_episodes} == set(range(per_task)), f"Wrong rollout indices: {task_id}")
            if is_libero:
                require({item["initStateId"] for item in task_episodes} == set(range(10)), f"Wrong initial states: {task_id}")
            for episode in task_episodes:
                episode_id = episode["id"]
                require(is_robocasa or "remoteVideo" not in episode, "Unexpected remote video for a historical benchmark")
                require(isinstance(episode_id, str) and re.fullmatch(r"[a-z0-9_]+", episode_id), "Invalid episode ID")
                require(episode_id not in episodes, f"Duplicate episode ID: {episode_id}")
                require(is_libero or task_id.startswith(f"{benchmark_id}_"), f"Unexpected {benchmark_id} task identifier")
                expected_prefix = task_id if is_libero or is_robocasa else task_id.removeprefix("robotwin_")
                require(episode_id == f"{expected_prefix}_r{episode['index']:02d}", f"Episode/task identity mismatch: {episode_id}")
                require(episode["status"] in {"success", "failure", "timeout"}, f"Unscored episode: {episode_id}")
                for key in ("index", "seed", "steps", "maxSteps", "toolCalls", "width", "height", "frames"):
                    integer(episode[key], f"{episode_id}.{key}", 1 if key in {"width", "height", "frames", "maxSteps"} else 0)
                require(episode["steps"] <= episode["maxSteps"] and episode["toolCalls"] <= (1500 if is_robocasa else 750),
                        f"Recorded controls exceed the protocol: {episode_id}")
                require(episode["steps"] > 0, f"Episode has no recorded action: {episode_id}")
                fps = 20 if is_libero or is_robocasa else 10
                if is_libero:
                    require(episode["maxSteps"] == 500 and episode["seed"] == episode["index"] == episode["initStateId"],
                            f"Incorrect LIBERO episode protocol: {episode_id}")
                    require(episode["frames"] == episode["steps"] + 11, f"LIBERO warmup/frame mismatch: {episode_id}")
                else:
                    require(episode["index"] == 0 and episode["initStateId"] is None,
                            f"Incorrect {benchmark_id} episode protocol: {episode_id}")
                    require(episode["frames"] == episode["steps"] + 1, f"{benchmark_id} action/frame mismatch: {episode_id}")
                    if is_robocasa:
                        require(episode["seed"] >= 100000 and episode["maxSteps"] <= 7200,
                                f"Incorrect RoboCasa365 seed or step budget: {episode_id}")
                        require(episode["width"] == 3 * episode["height"], f"Incorrect three-camera layout: {episode_id}")
                        require(episode.get("remoteVideo") == remote_video_url(episode_id),
                                f"Incorrect release video URL: {episode_id}")
                        require(episode["video"] == f"media/robocasa/{episode_id}.mp4"
                                and episode["poster"] == f"media/robocasa/{episode_id}.jpg",
                                f"Incorrect RoboCasa local media paths: {episode_id}")
                for key in ("wallSeconds", "durationSeconds"):
                    require(type(episode[key]) in (int, float) and math.isfinite(episode[key]) and episode[key] >= 0,
                            f"Invalid duration: {episode_id}.{key}")
                require(abs(episode["durationSeconds"] - episode["frames"] / fps) < 1e-6,
                        f"Playback duration/frame mismatch: {episode_id}")
                for key, suffix in (("video", ".mp4"), ("poster", ".jpg")):
                    relative = episode[key]
                    require(relative not in media_paths, f"Duplicate media reference: {relative}")
                    media_paths.add(relative)
                    allow_missing = is_robocasa and key == "video" and release_assets is not None
                    require(local_asset(root, relative, key, allow_missing=allow_missing).suffix == suffix,
                            f"Unexpected media format: {relative}")
                episodes[episode_id] = {"episode": episode, "benchmark": benchmark_id, "task": task, "fps": fps}
                all_episodes.append(episode)
            check_summary(task, counts(task_episodes), task_id, ("successes", "failures", "successRate"))
        if is_libero:
            require({task["id"] for task in tasks} == {f"{suite}_t{index:02d}" for suite in EXPECTED_SUITES for index in range(10)},
                    "LIBERO must contain tasks 0–9 in each official suite")
        expected = counts(all_episodes, len(tasks))
        fixed = {"tasks": 40, "episodes": 400, "successes": 322, "failures": 78, "timeouts": 0, "successRate": .805} if is_libero else {
            "tasks": 50, "episodes": 50, "successes": 36, "failures": 14, "timeouts": 1, "successRate": .72}
        if not is_robocasa:
            require(expected == fixed, f"Wrong native outcome aggregate for {benchmark_id}")
        check_summary(benchmark["summary"], expected, f"{benchmark_id} summary")
        summaries[benchmark_id] = expected
        for suite in suites:
            suite_tasks = [task for task in tasks if task["suite"] == suite["id"]]
            selected = [episode for task in suite_tasks for episode in task["episodes"]]
            expected = counts(selected, len(suite_tasks))
            if is_libero:
                require(expected["tasks"] == 10 and expected["episodes"] == 100 and expected["successes"] == EXPECTED_SUITES[suite["id"]],
                        f"Wrong LIBERO suite outcome: {suite['id']}")
            elif is_robocasa:
                require(expected["tasks"] == expected["episodes"] == (65 if suite["id"] == "robocasa_atomic" else 300),
                        f"Wrong RoboCasa365 task group: {suite['id']}")
            check_summary(suite, expected, f"{suite['id']} summary")
    require(len(episodes) == expected_episodes and len(task_ids) == expected_tasks_total,
            f"Expected {expected_episodes} unique episodes across {expected_tasks_total} tasks")
    runs = report["runs"]
    require(len(runs) == len(expected_benchmarks) and {run["benchmark"] for run in runs} == expected_benchmarks,
            "Wrong provenance runs")
    for run in runs:
        benchmark_id = run["benchmark"]
        is_robocasa = benchmark_id == "robocasa"
        expected_ids = {key for key, item in episodes.items() if item["benchmark"] == benchmark_id}
        provenance = benchmark_by_id[benchmark_id]["provenance"]
        require(run["run"] == provenance["run"] and run["manifestSha256"] == provenance["manifestSha256"],
                f"Provenance mismatch: {benchmark_id}")
        sources = {}
        if is_robocasa:
            require(run.get("auditKind") == provenance.get("auditKind") == "robocasa_collection",
                    "RoboCasa requires a complete collection audit")
            for key in ("auditSha256", "planSha256"):
                check_digest(run.get(key), f"RoboCasa {key}")
                require(run[key] == provenance.get(key), f"RoboCasa {key} mismatch")
            require(run.get("sources") == provenance.get("sources") and isinstance(run.get("sources"), list),
                    "RoboCasa source registry mismatch")
            for source in run["sources"]:
                name = source.get("run")
                require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", name) and name not in sources,
                        "Invalid or duplicate RoboCasa source run")
                check_digest(source.get("manifestSha256"), "RoboCasa source manifest")
                integer(source.get("seedBase"), "RoboCasa source seed", 100000)
                sources[name] = source
            require(run["run"] in sources and sources[run["run"]]["manifestSha256"] == run["manifestSha256"]
                    and sources[run["run"]]["seedBase"] == 100000, "RoboCasa primary source mismatch")
        selections = run["attemptSelection"]
        require(len(selections) == len(expected_ids) and {item["episode"] for item in selections} == expected_ids,
                f"Incomplete source selection mapping: {benchmark_id}")
        require(run["selectedEpisodes"] == len(expected_ids), f"Incorrect selected episode count: {benchmark_id}")
        excluded_count = 0
        for selection in selections:
            episode = episodes[selection["episode"]]["episode"]
            check_digest(selection["resultSha256"], "selected result")
            selected_attempt = selection["selectedAttempt"]
            require(re.fullmatch(r"attempt_\d+", selected_attempt), "Invalid selected attempt identifier")
            if is_robocasa:
                source = sources.get(selection.get("run"))
                require(source is not None and source["manifestSha256"] == selection.get("manifestSha256")
                        and source["seedBase"] == selection.get("seed") == episode["seed"],
                        "RoboCasa selected source or seed mismatch")
                original_key = selection.get("sourceEpisodeKey")
                require(isinstance(original_key, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*_r00", original_key)
                        and selection["episode"] == f"robocasa_{original_key.lower()}", "RoboCasa source episode mismatch")
                require(selection.get("status") == episode["status"] and selection.get("steps") == episode["steps"],
                        "RoboCasa selected outcome mismatch")
                require(type(selection.get("nativeScore")) is int
                        and selection["nativeScore"] == int(episode["status"] == "success"),
                        "RoboCasa native score mismatch")
                check_digest(selection.get("sourceVideoSha256"), "RoboCasa selected source video")
            excluded_attempts = set()
            for excluded in selection["excludedAttempts"]:
                require(excluded["status"] in {"error", "interrupted"}, "A policy outcome was excluded by a retry")
                require(re.fullmatch(r"attempt_\d+", excluded["attempt"]), "Invalid excluded attempt identifier")
                identity = (excluded.get("run"), excluded["attempt"]) if is_robocasa else excluded["attempt"]
                require(identity not in excluded_attempts, "Duplicate excluded attempt")
                excluded_attempts.add(identity)
                if not is_robocasa or excluded.get("run") == selection["run"]:
                    require(int(excluded["attempt"].split("_")[-1]) < int(selected_attempt.split("_")[-1]),
                            "The selected result is not the latest attempt")
                if is_robocasa:
                    source = sources.get(excluded.get("run"))
                    require(source is not None and excluded.get("manifestSha256") == source["manifestSha256"]
                            and excluded.get("seed") == source["seedBase"] <= selection["seed"],
                            "RoboCasa excluded source or seed mismatch")
                    require(excluded.get("sourceEpisodeKey") == selection["sourceEpisodeKey"],
                            "RoboCasa excluded task mismatch")
                    require(excluded.get("countsAsValidEpisode") is False and excluded.get("countedAsValidSuccess") is False,
                            "RoboCasa infrastructure attempts must not count as policy episodes")
                    require(excluded["status"] == "error" and excluded.get("reason") in {
                        "simulation_error", "codex_error", "video_recording_error"}, "Unsupported RoboCasa excluded outcome")
                    integer(excluded.get("steps"), "RoboCasa excluded steps")
                    integer(excluded.get("visualObservations"), "RoboCasa excluded RGB observations")
                    if excluded["reason"] == "simulation_error":
                        require(excluded["steps"] == excluded["visualObservations"] == 0
                                and excluded.get("nativeSuccess") is True, "Unproved initial-scene exclusion")
                    else:
                        require(excluded.get("nativeSuccess") is False and excluded["steps"] > 0
                                and excluded["visualObservations"] > 0, "Unproved retained API failure")
                        require(excluded["seed"] == selection["seed"], "An API failure cannot advance the seed")
                    check_digest(excluded.get("videoSha256"), "RoboCasa excluded video")
                check_digest(excluded["resultSha256"], "excluded result")
                excluded_count += 1
        require(excluded_count == run["excludedAttemptCount"],
                f"Wrong infrastructure/interruption retry count: {benchmark_id}")
        if not is_robocasa:
            require(excluded_count == (4 if benchmark_id == "libero" else 6),
                    f"Unexpected historical retry count: {benchmark_id}")
    media = report["media"]
    require(len(media) == expected_episodes and {item["episode"] for item in media} == set(episodes), "Incomplete media provenance mapping")
    videos, video_bytes, poster_bytes = [], 0, 0
    if release_assets is not None:
        require(set(release_assets) == {f"{key}.mp4" for key, item in episodes.items() if item["benchmark"] == "robocasa"},
                "Release must contain exactly the 365 selected RoboCasa videos")
    for record in media:
        item = episodes[record["episode"]]
        episode = item["episode"]
        require(record["benchmark"] == item["benchmark"], "Wrong media benchmark mapping")
        for key in ("video", "poster", "width", "height", "frames"):
            require(record[key] == episode[key], f"Media/source mapping mismatch: {record['episode']}.{key}")
        require(record["codec"] == "h264" and record["pixelFormat"] == "yuv420p"
                and record["fastStart"] is True and record["verified"] is True, "Unverified or incompatible video export")
        require(Fraction(record["fps"]) == item["fps"], "Video frame-rate mapping differs from the source protocol")
        require(abs(record["durationSeconds"] - episode["durationSeconds"]) < 1e-3, "Video duration mapping differs from source")
        require(0 <= integer(record["posterFrame"], "poster frame") < episode["frames"], "Poster references a missing source frame")
        check_digest(record["sourceSha256"], "source video")
        if item["benchmark"] == "robocasa":
            selection = next(selection for run in runs if run["benchmark"] == "robocasa"
                             for selection in run["attemptSelection"] if selection["episode"] == record["episode"])
            require(record["sourceSha256"] == selection["sourceVideoSha256"], "RoboCasa audit/source video mismatch")
        integer(record["sourceBytes"], "source video size", 1)
        for key in ("video", "poster"):
            check_digest(record[f"{key}Sha256"], f"{key} export")
            is_release_video = item["benchmark"] == "robocasa" and key == "video" and release_assets is not None
            path = local_asset(root, record[key], key, allow_missing=is_release_video)
            if is_release_video:
                asset = release_assets[f"{record['episode']}.mp4"]
                require(asset.get("state") == "uploaded" and asset.get("size") == record["videoBytes"]
                        and asset.get("digest") == f"sha256:{record['videoSha256']}"
                        and asset.get("browser_download_url") == episode["remoteVideo"],
                        f"Release asset fingerprint mismatch: {record['episode']}")
                if path.exists():
                    require(path.is_file() and path.stat().st_size == record["videoBytes"]
                            and sha256(path) == record["videoSha256"],
                            f"Local release video fingerprint mismatch: {record['episode']}")
            else:
                require(path.stat().st_size == record[f"{key}Bytes"], f"Media byte count mismatch: {record[key]}")
                require(sha256(path) == record[f"{key}Sha256"], f"Media digest mismatch: {record[key]}")
        video_bytes += record["videoBytes"]
        poster_bytes += record["posterBytes"]
        video_source = episode["remoteVideo"] if item["benchmark"] == "robocasa" and release_assets is not None else root / record["video"]
        videos.append((video_source, {"width": record["width"], "height": record["height"],
                                               "frames": record["frames"], "fps": item["fps"]}))
    require(report["videoBytes"] == video_bytes and report["posterBytes"] == poster_bytes
            and report["publishedMediaBytes"] == video_bytes + poster_bytes, "Incorrect published media size total")
    require(report["sourceBytes"] == sum(record["sourceBytes"] for record in media), "Incorrect source media size total")
    if has_robocasa:
        external_bytes = sum(record["videoBytes"] for record in media if record["benchmark"] == "robocasa")
        pages_bytes = video_bytes + poster_bytes - external_bytes
        require(report.get("externalVideoBytes") == external_bytes and report.get("pagesMediaBytes") == pages_bytes,
                "Incorrect release/Pages media size totals")
        require(pages_bytes < 800_000_000, "Pages media exceeds 800 MB")
    require(report["validation"]["decodedFrameCount"] == sum(record["frames"] for record in media),
            "Incorrect mapped frame total")
    actual_media = {path.relative_to(root).as_posix() for path in (root / "media").rglob("*") if path.is_file()}
    require(actual_media == media_paths if release_assets is None else
            media_paths - external_media <= actual_media <= media_paths,
            "The media directory contains missing or unlisted files")
    with (root / "data/episodes.csv").open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    require(len(csv_rows) == expected_episodes and {row["episode"] for row in csv_rows} == set(episodes), "CSV episode mapping is incomplete")
    for row in csv_rows:
        public_metadata(row, "episodes.csv")
        item = episodes[row["episode"]]
        expected_row = {"benchmark": item["benchmark"], "suite": item["task"]["suite"], "task": item["task"]["id"],
                        "instruction": item["task"]["instruction"], "episode": row["episode"],
                        **{key: item["episode"][key] for key in ("status", "seed", "initStateId", "steps", "maxSteps",
                           "toolCalls", "wallSeconds", "durationSeconds", "frames", "video", "poster")},
                        "rolloutIndex": item["episode"]["index"]}
        if has_robocasa:
            expected_row["remoteVideo"] = item["episode"].get("remoteVideo")
        require(row == {key: "" if value is None else str(value) for key, value in expected_row.items()},
                f"CSV/JSON mismatch: {row['episode']}")
    return {"benchmarks": summaries, "episodes": len(episodes), "tasks": len(task_ids),
            "media_files": len(media_paths), "media_bytes": video_bytes + poster_bytes,
            "repository_files": tree["files"], "repository_bytes": tree["bytes"], "pages_bytes": tree["siteBytes"]}, videos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Gallery repository root")
    parser.add_argument("--videos", action="store_true", help="Decode and validate every video with ffprobe")
    parser.add_argument("--require-robocasa", action="store_true", help="Require all 365 RoboCasa episodes in addition to LIBERO and RoboTwin")
    parser.add_argument("--release-media", action="store_true", help="Verify RoboCasa videos through the public Release asset SHA256/size registry")
    parser.add_argument("--workers", type=int, default=4, help="Concurrent ffprobe processes (default: 4)")
    args = parser.parse_args()
    try:
        require(args.root.is_dir(), "Gallery root is missing")
        require(1 <= args.workers <= 32, "Workers must be between 1 and 32")
        release_assets = None
        if args.release_media:
            from release_media import fetch_release_assets
            release_assets = fetch_release_assets()
        result, videos = validate_gallery(args.root.resolve(), require_robocasa=args.require_robocasa,
                                         release_assets=release_assets)
        if args.videos:
            require(shutil.which("ffprobe") is not None, "Install ffprobe to use --videos")
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                frames = sum(pool.map(probe_video, videos))
            result.update(videos_decoded=len(videos), frames_decoded=frames)
        result["passed"] = True
        print(json.dumps(result, indent=2, sort_keys=True))
    except (ValidationError, OSError, KeyError, TypeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Gallery validation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
