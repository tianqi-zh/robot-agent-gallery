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
MAX_SITE_BYTES = 1_600_000_000
MAX_FILE_BYTES = 100_000_000
EXPECTED_SUITES = {"libero_spatial": 95, "libero_goal": 79, "libero_object": 89, "libero_10": 59}
EXPECTED_RUNS = {
    "libero": ("astra_libero_v5_calibrated_parallel10_r4",
               "df08694520ff7ea3e9bfee061a29223e46c4db76bc54a07e637cbfcbe93f42f8"),
    "robotwin": ("robotwin_astra_firstpass_20260917",
                 "8f0b9bfc28b7e2dccc7fe7a056114f1b7d2fdbf36e4bcbf72771931c5a9c6c38"),
    "robocasa": ("robocasa365_astra_firstpass_20260918",
                 "3a2a7f6939e18b5ee3fb6d6bac10d8f2f8704cd422d91efc8e56a038cf28c12c"),
    "robodojo": ("robodojo42_astra_firstpass_20260919",
                 "fe327cacc7615e868096a025c1287a8ad070408851bac9104cf132c1349f6fd4"),
    "robotwin_nvidia10": ("robotwin_goal_spec_full_v1",
                          "5044e7c5eaed3389b689c0534c0863966d5ee1b3fbafc9e4990a0c85960a5f88"),
}
# Exact standard task matrix from the frozen RoboDojo manifest. Native names are
# case-sensitive; gallery IDs are lowercased and the suite ID uses underscores.
ROBODOJO_TASKS = {
    "generalization": ("stack_bowls", "push_T", "pack_objects_into_box", "fold_clothes", "hang_mugs",
                       "sweep_blocks", "pour_liquid_into_cup", "make_toast", "arrange_largest_number",
                       "sort_nesting_dolls_by_size", "store_laptop_and_headphones", "stack_blocks"),
    "memory": ("cover_blocks", "match_and_pick_from_conveyor", "swap_blocks", "swap_T", "press_by_number",
               "imitate_sorting_sequence"),
    "precision": ("fasten_screws", "plug_in_charger", "insert_tubes", "pour_balls_into_vase", "play_Xylophone",
                  "deposit_coin", "insert_key", "build_tower"),
    "long-horizon": ("fill_pen_holder", "classify_objects", "put_bottles_into_dustbin", "play_tic_tac_toe",
                     "fill_egg_holder", "organize_table", "make_kong", "play_stacking_toy"),
    "open": ("align_blocks", "general_pickup", "solve_equation", "stack_blocks_by_language",
             "classify_objects_by_language", "pick_from_conveyor_by_image", "store_tools_in_toolbox",
             "pour_by_language"),
}
ROBODOJO_SUITES = {"robodojo_" + group.replace("-", "_"): names for group, names in ROBODOJO_TASKS.items()}
ROBODOJO_HORIZONS = dict(zip(
    (name for names in ROBODOJO_TASKS.values() for name in names),
    (800, 600, 1300, 500, 800, 1000, 400, 1400, 1050, 1050, 800, 550,
     800, 700, 700, 400, 700, 1600, 1900, 400, 500, 600, 500, 300, 300, 1050,
     1100, 1100, 700, 1100, 700, 1000, 600, 1200, 200, 200, 300, 400, 1100, 700, 900, 800),
))
ROBODOJO_PROVENANCE_KEYS = {"run", "manifestSha256", "auditKind", "auditSha256", "policyBoundaryAuditSha256"}
ROBODOJO_EPISODE_KEYS = {"id", "index", "status", "seed", "initStateId", "steps", "maxSteps", "toolCalls",
                       "wallSeconds", "durationSeconds", "video", "poster", "width", "height", "frames",
                       "nativeScore", "terminationReason", "layoutId"}
ROBODOJO_SELECTION_KEYS = {"episode", "sourceEpisodeKey", "seed", "selectedAttempt", "resultSha256",
                         "sourceVideoSha256", "instructionSha256", "nativeSuccess", "nativeScore",
                         "status", "steps", "excludedAttempts", "nativeStateSha256"}
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
    require(site_total < MAX_SITE_BYTES, f"Pages gallery exceeds the configured size limit: {site_total} bytes")
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


def public_fields(value, allowed, label):
    require(isinstance(value, dict) and set(value) <= allowed, f"Unexpected public {label} fields")


def validate_robodojo_task(task):
    public_fields(task, {"id", "name", "instruction", "instructionSha256", "suite", "suiteName", "episodes",
                         "successes", "failures", "successRate", "nativeTaskName", "taskGroup"}, "RoboDojo task")
    native_name = task.get("nativeTaskName")
    group = task.get("taskGroup")
    require(group in ROBODOJO_TASKS and native_name in ROBODOJO_TASKS[group]
            and task["id"] == "robodojo_" + native_name.lower()
            and task["suite"] == "robodojo_" + group.replace("-", "_"),
            "RoboDojo native task/group identity mismatch")
    digest = hashlib.sha256(task["instruction"].encode("utf-8")).hexdigest()
    require(task.get("instructionSha256") == digest, "RoboDojo native instruction fingerprint mismatch")


def validate_robodojo_episode(episode, task):
    public_fields(episode, ROBODOJO_EPISODE_KEYS, "RoboDojo episode")
    require(episode["seed"] == 0 and episode["maxSteps"] == ROBODOJO_HORIZONS[task["nativeTaskName"]],
            "Incorrect RoboDojo seed or native horizon")
    require(type(episode.get("layoutId")) is int and episode["layoutId"] == 0, "Incorrect RoboDojo native layout")
    score = episode.get("nativeScore")
    require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1,
            "Invalid RoboDojo native score")
    reason = episode.get("terminationReason")
    require(reason in {"step_budget", "agent_finished", "robodojo_success", "environment_done"},
            "Invalid RoboDojo termination reason")
    require((reason == "robodojo_success") == (episode["status"] == "success"),
            "RoboDojo termination/outcome mismatch")
    if reason == "step_budget":
        require(episode["steps"] == episode["maxSteps"], "RoboDojo exhausted horizon mismatch")


def validate_training_demos(root, gallery, *, required=False):
    """Validate separate training references without changing evaluation counts."""
    catalog_path = root / "data/task-demos.json"
    if not catalog_path.exists():
        require(not required, "Training demonstration catalog is required")
        return None, [], set()
    catalog = read_json(catalog_path)
    public_metadata(catalog, "data/task-demos.json")
    require(catalog.get("schemaVersion") == 1, "Unsupported training demo schema")
    records = catalog.get("tasks")
    expected = {task["id"]: (benchmark["id"], task)
                for benchmark in gallery["benchmarks"] for task in benchmark["tasks"]}
    # Older evaluation-only RoboDojo imports may have no demonstration group.
    # Once imported, every task needs an available or unavailable source record.
    if isinstance(records, dict) and not any(task_id in records for task_id, (benchmark_id, _) in expected.items()
                                            if benchmark_id == "robodojo"):
        expected = {task_id: value for task_id, value in expected.items() if value[0] != "robodojo"}
    require(isinstance(records, dict) and set(records) == set(expected),
            "Training demo catalog must account for every gallery task exactly once")
    coverage = {benchmark["id"]: {"tasks": len(benchmark["tasks"]), "available": 0, "unavailable": 0}
                for benchmark in gallery["benchmarks"]
                if any(value[0] == benchmark["id"] for value in expected.values())}
    videos, media_paths = [], set()
    for task_id, record in records.items():
        benchmark_id, task = expected[task_id]
        require(record.get("taskId") == task_id and record.get("benchmark") == benchmark_id,
                f"Training demo task identity mismatch: {task_id}")
        status = record.get("status")
        require(status in {"available", "unavailable"}, f"Invalid training demo status: {task_id}")
        coverage[benchmark_id][status] += 1
        source = record.get("source", {})
        require(isinstance(source, dict) and isinstance(source.get("dataset"), str) and source["dataset"].strip()
                and isinstance(source.get("url"), str) and source["url"].startswith("https://"),
                f"Missing training dataset attribution: {task_id}")
        if status == "unavailable":
            require(isinstance(record.get("reason"), str) and record["reason"].strip(),
                    f"Missing unavailable-demo explanation: {task_id}")
            require(not any(key in record for key in ("video", "poster", "remoteVideo", "frames")),
                    f"Unavailable training demo must not claim media: {task_id}")
            continue
        relative_source = source.get("relativePath")
        require(isinstance(relative_source, str) and relative_source and
                not PurePosixPath(relative_source).is_absolute() and ".." not in PurePosixPath(relative_source).parts,
                f"Missing relative training source path: {task_id}")
        require(source.get("episode") is not None, f"Missing training episode selection: {task_id}")
        if benchmark_id in {"robotwin", "robocasa", "robodojo"}:
            require(isinstance(source.get("taskName"), str) and
                    f"{benchmark_id}_{source['taskName'].lower()}" == task_id,
                    f"Training source task differs from gallery task: {task_id}")
        if benchmark_id == "robodojo":
            require(source["taskName"] == task.get("nativeTaskName"),
                    f"Training source native task differs from gallery task: {task_id}")
        for key in ("width", "height", "frames"):
            integer(record.get(key), f"{task_id} demo {key}", 1)
        fps = record.get("fps")
        require(type(fps) in (int, float) and math.isfinite(fps) and fps > 0,
                f"Invalid training demo frame rate: {task_id}")
        duration = record.get("durationSeconds")
        require(type(duration) in (int, float) and math.isfinite(duration)
                and abs(duration - record["frames"] / fps) < .001,
                f"Training demo duration/frame mismatch: {task_id}")
        require(isinstance(record.get("cameras"), list) and record["cameras"] and
                all(isinstance(value, str) and value.strip() for value in record["cameras"]),
                f"Missing training camera labels: {task_id}")
        for key, suffix in (("video", ".mp4"), ("poster", ".jpg")):
            relative = f"media/demos/{benchmark_id}/{task_id}{suffix}"
            require(record.get(key) == relative and relative not in media_paths,
                    f"Incorrect training demo asset mapping: {task_id}")
            path = local_asset(root, relative, f"training {key}")
            check_digest(record.get(f"{key}Sha256"), f"training {key}")
            require(sha256(path) == record[f"{key}Sha256"], f"Training media digest mismatch: {relative}")
            if key == "video" or f"{key}Bytes" in record:
                require(path.stat().st_size == record.get(f"{key}Bytes"),
                        f"Training media byte count mismatch: {relative}")
            media_paths.add(relative)
        videos.append((root / record["video"], {key: record[key] for key in ("width", "height", "frames", "fps")}))
    require(catalog.get("coverage") == coverage, "Training demo coverage summary differs from catalog")
    return coverage, videos, media_paths


def validate_blog_media(root):
    """Allow only explicit, complete essay clip references into the media tree.

    The separate blog validator checks experiment claims and clip fingerprints.
    This inventory check also supports references to existing baseline media.
    """
    path = root / "data/libero-blog-media.json"
    if not path.exists():
        return set()
    catalog = read_json(path)
    public_metadata(catalog, "data/libero-blog-media.json")
    require(isinstance(catalog, dict) and catalog.get("schemaVersion") == 1,
            "Unsupported blog media schema")
    require(catalog.get("complete") is True, "The blog media export is not complete")
    clips = catalog.get("clips")
    require(isinstance(clips, dict) and clips, "Blog media must declare its clips")
    paths = set()
    for identifier, clip in clips.items():
        require(isinstance(clip, dict) and clip.get("id") == identifier,
                "Invalid blog clip identity")
        for key, suffix in (("video", ".mp4"), ("poster", ".jpg")):
            relative = clip.get(key)
            asset = local_asset(root, relative, f"blog {key}")
            require(PurePosixPath(relative).parts[0] == "media" and asset.suffix == suffix,
                    f"Blog {key} must reference a {suffix} file under media")
            paths.add(relative)
    return paths


def validate_media_inventory(root, media_paths, external_media=()):
    actual_media = {path.relative_to(root).as_posix() for path in (root / "media").rglob("*") if path.is_file()}
    require(media_paths - set(external_media) <= actual_media <= media_paths,
            "The media directory contains missing or unlisted files")


def validate_gallery(root, *, check_interface=True, require_robocasa=False, release_assets=None,
                     require_demos=False, require_robodojo=False):
    required_files = ("index.html", "app.js", "styles.css", ".nojekyll", "METHODOLOGY.md") if check_interface else ()
    for filename in required_files:
        require((root / filename).is_file(), f"Required public file is missing: {filename}")
    expected_data_files = {"gallery.json", "episodes.csv", "export-report.json"}
    if (root / "data/task-demos.json").exists():
        expected_data_files.add("task-demos.json")
    for name in ("libero-blog-media.json", "libero-alignment.json", "libero-alignment-episodes.csv",
                 "libero-human-review.json", "robotwin-alignment-summary.json"):
        if (root / "data" / name).exists():
            expected_data_files.add(name)
    require({path.relative_to(root / "data").as_posix() for path in (root / "data").rglob("*") if path.is_file()}
            == expected_data_files,
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
    has_robodojo = "robodojo" in benchmark_ids
    has_robotwin_nvidia10 = "robotwin_nvidia10" in benchmark_ids
    require(release_assets is None or has_robocasa, "Release validation requires RoboCasa365")
    expected_benchmarks = ({"libero", "robotwin"} | ({"robocasa"} if has_robocasa else set())
                           | ({"robodojo"} if has_robodojo else set())
                           | ({"robotwin_nvidia10"} if has_robotwin_nvidia10 else set()))
    require(benchmark_ids == expected_benchmarks and len(benchmarks) == len(expected_benchmarks),
            "Expected LIBERO and RoboTwin, with complete optional benchmark collections")
    require(not require_robocasa or has_robocasa, "The complete RoboCasa365 collection is required")
    require(not require_robodojo or has_robodojo, "The complete RoboDojo42 collection is required")
    expected_episodes, expected_tasks_total = (815, 455) if has_robocasa else (450, 90)
    if has_robodojo:
        expected_episodes += 42
        expected_tasks_total += 42
    if has_robotwin_nvidia10:
        expected_episodes += 479
        expected_tasks_total += 50
    require(gallery.get("evaluationDate") == ("2026-09-22" if has_robotwin_nvidia10 else "2026-09-19" if has_robodojo else "2026-09-18" if has_robocasa else "2026-09-17"),
            "Unexpected evaluation date")
    if has_robocasa or has_robodojo or has_robotwin_nvidia10:
        dates = ["2026-09-17"] + (["2026-09-18"] if has_robocasa else []) + (["2026-09-19"] if has_robodojo else []) + (["2026-09-22"] if has_robotwin_nvidia10 else [])
        require(gallery.get("evaluationDates") == dates, "Incorrect evaluation dates")
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
        is_robodojo = benchmark_id == "robodojo"
        is_robotwin_nvidia10 = benchmark_id == "robotwin_nvidia10"
        if is_robodojo:
            public_fields(benchmark, {"id", "name", "evaluationDate", "summary", "suites", "protocol", "provenance", "tasks"},
                          "RoboDojo benchmark")
            public_fields(benchmark["protocol"], {"label", "description", "cameras", "videoNote", "stepsLabel", "episodesPerTask", "trainingDemoNote"},
                          "RoboDojo protocol")
            public_fields(benchmark["provenance"], ROBODOJO_PROVENANCE_KEYS, "RoboDojo provenance")
            public_fields(benchmark["summary"], set(counts([], 0)), "RoboDojo summary")
        require(is_robocasa or "videoHosting" not in benchmark, "Unexpected external hosting for a historical benchmark")
        if has_robocasa or has_robodojo or has_robotwin_nvidia10:
            require(benchmark.get("evaluationDate") == ("2026-09-22" if is_robotwin_nvidia10 else "2026-09-19" if is_robodojo else "2026-09-18" if is_robocasa else "2026-09-17"),
                    f"Incorrect evaluation date: {benchmark_id}")
        expected_tasks, per_task = {"libero": (40, 10), "robotwin": (50, 1), "robocasa": (365, 1), "robodojo": (42, 1),
                                    "robotwin_nvidia10": (50, 10)}[benchmark_id]
        tasks = benchmark["tasks"]
        require(len(tasks) == expected_tasks, f"Wrong task count for {benchmark_id}")
        require(benchmark["protocol"]["episodesPerTask"] == per_task, f"Wrong sampling for {benchmark_id}")
        check_digest(benchmark["provenance"]["manifestSha256"], f"{benchmark_id} manifest")
        require((benchmark["provenance"]["run"], benchmark["provenance"]["manifestSha256"]) == EXPECTED_RUNS[benchmark_id],
                f"Unexpected frozen source run for {benchmark_id}")
        expected_suites = set(EXPECTED_SUITES) if is_libero else ({"robocasa_atomic", "robocasa_composite"} if is_robocasa else {"robotwin_nvidia10"} if is_robotwin_nvidia10 else {"robotwin"})
        if is_robodojo:
            expected_suites = set(ROBODOJO_SUITES)
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
            require(isinstance(task["instruction"], str) and (is_robodojo or task["instruction"].strip()), f"Missing instruction: {task_id}")
            if is_robodojo:
                validate_robodojo_task(task)
            task_episodes = task["episodes"]
            if is_robotwin_nvidia10:
                require(1 <= len(task_episodes) <= per_task, f"Wrong episode count for {task_id}")
                require({item["index"] for item in task_episodes}.issubset(set(range(per_task))), f"Wrong rollout indices: {task_id}")
            else:
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
                expected_prefix = task_id if is_libero or is_robocasa or is_robodojo else task_id.removeprefix("robotwin_")
                if is_robotwin_nvidia10:
                    expected_prefix = task_id
                require(episode_id == f"{expected_prefix}_r{episode['index']:02d}", f"Episode/task identity mismatch: {episode_id}")
                require(episode["status"] in {"success", "failure", "timeout"}, f"Unscored episode: {episode_id}")
                if is_robotwin_nvidia10:
                    require(isinstance(episode.get("instruction"), str) and episode["instruction"].strip(),
                            f"Missing episode instruction: {episode_id}")
                for key in ("index", "seed", "steps", "maxSteps", "toolCalls", "width", "height", "frames"):
                    integer(episode[key], f"{episode_id}.{key}", 1 if key in {"width", "height", "frames", "maxSteps"} else 0)
                require(episode["steps"] <= episode["maxSteps"] and episode["toolCalls"] <= (1500 if is_robocasa or is_robodojo else 750),
                        f"Recorded controls exceed the protocol: {episode_id}")
                require(episode["steps"] > 0, f"Episode has no recorded action: {episode_id}")
                fps = 25 if is_robodojo else 20 if is_libero or is_robocasa else 10
                if is_libero:
                    require(episode["maxSteps"] == 500 and episode["seed"] == episode["index"] == episode["initStateId"],
                            f"Incorrect LIBERO episode protocol: {episode_id}")
                    require(episode["frames"] == episode["steps"] + 11, f"LIBERO warmup/frame mismatch: {episode_id}")
                elif is_robotwin_nvidia10:
                    require(episode["initStateId"] is None and 0 <= episode["index"] < 10,
                            f"Incorrect RoboTwin 10-rollout protocol: {episode_id}")
                    require(episode["seed"] >= 100000,
                            f"Incorrect RoboTwin 10-rollout seed: {episode_id}")
                    require(episode["frames"] == episode["steps"] + 1, f"{benchmark_id} action/frame mismatch: {episode_id}")
                    require(episode["video"] == f"media/robotwin_nvidia10/{episode_id}.mp4"
                            and episode["poster"] == f"media/robotwin_nvidia10/{episode_id}.jpg",
                            f"Incorrect RoboTwin 10-rollout local media paths: {episode_id}")
                else:
                    require(episode["index"] == 0 and episode["initStateId"] is None,
                            f"Incorrect {benchmark_id} episode protocol: {episode_id}")
                    require(episode["frames"] == episode["steps"] + 1, f"{benchmark_id} action/frame mismatch: {episode_id}")
                    if is_robodojo:
                        validate_robodojo_episode(episode, task)
                        require((episode["width"], episode["height"]) == (1920, 480),
                                f"Incorrect RoboDojo native camera layout: {episode_id}")
                        require(episode["video"] == f"media/robodojo/{episode_id}.mp4"
                                and episode["poster"] == f"media/robodojo/{episode_id}.jpg",
                                f"Incorrect RoboDojo local media paths: {episode_id}")
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
        if not is_robocasa and not is_robotwin_nvidia10:
            if is_robodojo:
                fixed = {"tasks": 42, "episodes": 42, "successes": 6, "failures": 36, "timeouts": 0, "successRate": 6 / 42}
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
            elif is_robodojo:
                public_fields(suite, {"id", "name", *counts([], 0)}, "RoboDojo suite")
                require({task["id"] for task in suite_tasks} ==
                        {"robodojo_" + name.lower() for name in ROBODOJO_SUITES[suite["id"]]},
                        f"Wrong RoboDojo standard task matrix: {suite['id']}")
            check_summary(suite, expected, f"{suite['id']} summary")
    require(len(episodes) == expected_episodes and len(task_ids) == expected_tasks_total,
            f"Expected {expected_episodes} unique episodes across {expected_tasks_total} tasks")
    runs = report["runs"]
    require(len(runs) == len(expected_benchmarks) and {run["benchmark"] for run in runs} == expected_benchmarks,
            "Wrong provenance runs")
    for run in runs:
        benchmark_id = run["benchmark"]
        is_robocasa = benchmark_id == "robocasa"
        is_robodojo = benchmark_id == "robodojo"
        is_robotwin_nvidia10 = benchmark_id == "robotwin_nvidia10"
        expected_ids = {key for key, item in episodes.items() if item["benchmark"] == benchmark_id}
        provenance = benchmark_by_id[benchmark_id]["provenance"]
        require(run["run"] == provenance["run"] and run["manifestSha256"] == provenance["manifestSha256"],
                f"Provenance mismatch: {benchmark_id}")
        sources = {}
        if is_robodojo:
            public_fields(run, ROBODOJO_PROVENANCE_KEYS | {"benchmark", "selectedEpisodes", "excludedAttemptCount", "attemptSelection"},
                          "RoboDojo run")
            require(run.get("auditKind") == provenance.get("auditKind") == "robodojo_firstpass",
                    "RoboDojo requires the complete first-pass audits")
            for key in ("auditSha256", "policyBoundaryAuditSha256"):
                check_digest(run.get(key), f"RoboDojo {key}")
                require(run[key] == provenance.get(key), f"RoboDojo {key} mismatch")
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
            if is_robotwin_nvidia10:
                require(re.fullmatch(r"attempt_\d+_nvidia_goal_spec_full_v1", selected_attempt),
                        "Invalid selected attempt identifier")
            else:
                require(re.fullmatch(r"attempt_\d+", selected_attempt), "Invalid selected attempt identifier")
            if is_robodojo:
                public_fields(selection, ROBODOJO_SELECTION_KEYS, "RoboDojo selection")
                task = episodes[selection["episode"]]["task"]
                require(selection.get("sourceEpisodeKey") == task["nativeTaskName"] + "_r00"
                        and selected_attempt == "attempt_001" and selection["excludedAttempts"] == [],
                        "RoboDojo first-pass source identity mismatch")
                require(selection.get("seed") == episode["seed"]
                        and selection.get("status") == episode["status"]
                        and selection.get("steps") == episode["steps"], "RoboDojo selected outcome mismatch")
                require(type(selection.get("nativeSuccess")) is bool
                        and selection["nativeSuccess"] == (episode["status"] == "success"),
                        "RoboDojo native success mismatch")
                require(type(selection.get("nativeScore")) in (int, float)
                        and selection["nativeScore"] == episode["nativeScore"], "RoboDojo native score mismatch")
                require(selection.get("instructionSha256") == task["instructionSha256"],
                        "RoboDojo selected native instruction fingerprint mismatch")
                check_digest(selection.get("sourceVideoSha256"), "RoboDojo selected source video")
                check_digest(selection.get("nativeStateSha256"), "RoboDojo selected native state")
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
            if is_robotwin_nvidia10:
                require(selection.get("sourceEpisodeKey") == episode.get("sourceEpisodeKey")
                        and selection.get("status") == episode["status"]
                        and selection["excludedAttempts"] == [],
                        "RoboTwin 10-rollout source identity mismatch")
                check_digest(selection.get("sourceVideoSha256"), "RoboTwin 10-rollout selected source video")
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
        if not is_robotwin_nvidia10:
            require(excluded_count == run["excludedAttemptCount"],
                    f"Wrong infrastructure/interruption retry count: {benchmark_id}")
        if not is_robocasa and not is_robotwin_nvidia10:
            require(excluded_count == {"libero": 4, "robotwin": 6, "robodojo": 0}[benchmark_id],
                    f"Unexpected historical retry count: {benchmark_id}")
        if is_robotwin_nvidia10:
            require(run["excludedAttemptCount"] == 21, "Unexpected RoboTwin 10-rollout excluded episode count")
    media = report["media"]
    require(len(media) == expected_episodes and {item["episode"] for item in media} == set(episodes), "Incomplete media provenance mapping")
    videos, video_bytes, poster_bytes = [], 0, 0
    if release_assets is not None:
        require(set(release_assets) == {f"{key}.mp4" for key, item in episodes.items() if item["benchmark"] == "robocasa"},
                "Release must contain exactly the 365 selected RoboCasa videos")
    for record in media:
        item = episodes[record["episode"]]
        episode = item["episode"]
        if item["benchmark"] == "robodojo":
            public_fields(record, {"episode", "benchmark", "sourceSha256", "sourceBytes", "video", "videoSha256", "videoBytes",
                                   "poster", "posterSha256", "posterBytes", "posterFrame", "codec", "pixelFormat", "width",
                                   "height", "fps", "frames", "durationSeconds", "fastStart", "verified"}, "RoboDojo media")
        require(record["benchmark"] == item["benchmark"], "Wrong media benchmark mapping")
        for key in ("video", "poster", "width", "height", "frames"):
            require(record[key] == episode[key], f"Media/source mapping mismatch: {record['episode']}.{key}")
        require(record["codec"] == "h264" and record["pixelFormat"] == "yuv420p"
                and record["fastStart"] is True and record["verified"] is True, "Unverified or incompatible video export")
        require(Fraction(record["fps"]) == item["fps"], "Video frame-rate mapping differs from the source protocol")
        require(abs(record["durationSeconds"] - episode["durationSeconds"]) < 1e-3, "Video duration mapping differs from source")
        require(0 <= integer(record["posterFrame"], "poster frame") < episode["frames"], "Poster references a missing source frame")
        check_digest(record["sourceSha256"], "source video")
        if item["benchmark"] in {"robocasa", "robodojo", "robotwin_nvidia10"}:
            selection = next(selection for run in runs if run["benchmark"] == item["benchmark"]
                             for selection in run["attemptSelection"] if selection["episode"] == record["episode"])
            label = {"robocasa": "RoboCasa", "robodojo": "RoboDojo", "robotwin_nvidia10": "RoboTwin 10-rollout"}[item["benchmark"]]
            require(record["sourceSha256"] == selection["sourceVideoSha256"], f"{label} audit/source video mismatch")
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
        require(pages_bytes < 1_500_000_000, "Pages media exceeds 1.5 GB")
    require(report["validation"]["decodedFrameCount"] == sum(record["frames"] for record in media),
            "Incorrect mapped frame total")
    demo_coverage, demo_videos, demo_paths = validate_training_demos(root, gallery, required=require_demos)
    require(not media_paths.intersection(demo_paths), "Training and evaluation media must have distinct assets")
    demo_bytes = sum((root / relative).stat().st_size for relative in demo_paths)
    if has_robocasa:
        require(pages_bytes + demo_bytes < 1_500_000_000, "Pages media including training demos exceeds 1.5 GB")
    media_paths.update(demo_paths)
    videos.extend(demo_videos)
    blog_paths = validate_blog_media(root)
    additional_blog_paths = blog_paths - media_paths
    blog_bytes = sum((root / relative).stat().st_size for relative in additional_blog_paths)
    media_paths.update(blog_paths)
    if has_robocasa:
        require(pages_bytes + demo_bytes + blog_bytes < 1_500_000_000,
                "Pages media including training demos and blog clips exceeds 1.5 GB")
    validate_media_inventory(root, media_paths, external_media if release_assets is not None else ())
    with (root / "data/episodes.csv").open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    require(len(csv_rows) == expected_episodes and {row["episode"] for row in csv_rows} == set(episodes), "CSV episode mapping is incomplete")
    for row in csv_rows:
        public_metadata(row, "episodes.csv")
        item = episodes[row["episode"]]
        expected_row = {"benchmark": item["benchmark"], "suite": item["task"]["suite"], "task": item["task"]["id"],
                        "instruction": item["episode"].get("instruction", item["task"]["instruction"]), "episode": row["episode"],
                        **{key: item["episode"][key] for key in ("status", "seed", "initStateId", "steps", "maxSteps",
                           "toolCalls", "wallSeconds", "durationSeconds", "frames", "video", "poster")},
                        "rolloutIndex": item["episode"]["index"]}
        if has_robocasa:
            expected_row["remoteVideo"] = item["episode"].get("remoteVideo")
        require(row == {key: "" if value is None else str(value) for key, value in expected_row.items()},
                f"CSV/JSON mismatch: {row['episode']}")
    return {"benchmarks": summaries, "episodes": len(episodes), "tasks": len(task_ids),
            "training_demos": demo_coverage,
            "training_demo_bytes": demo_bytes,
            "blog_media_files": len(additional_blog_paths), "blog_media_bytes": blog_bytes,
            "media_files": len(media_paths), "media_bytes": video_bytes + poster_bytes + demo_bytes + blog_bytes,
            "repository_files": tree["files"], "repository_bytes": tree["bytes"], "pages_bytes": tree["siteBytes"]}, videos


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Gallery repository root")
    parser.add_argument("--videos", action="store_true", help="Decode and validate every video with ffprobe")
    parser.add_argument("--require-robocasa", action="store_true", help="Require all 365 RoboCasa episodes in addition to LIBERO and RoboTwin")
    parser.add_argument("--require-robodojo", action="store_true", help="Require all 42 standard RoboDojo episodes")
    parser.add_argument("--require-demos", action="store_true", help="Require the training catalog; RoboDojo may remain wholly unimported")
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
                                         release_assets=release_assets, require_demos=args.require_demos,
                                         require_robodojo=args.require_robodojo)
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
