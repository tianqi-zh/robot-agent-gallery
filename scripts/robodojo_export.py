#!/usr/bin/env python3
"""Append the audited RoboDojo first pass without rebuilding prior benchmarks.

Reads retained results only. No simulator, policy, upload, or deployment runs.
Media encoding resumes from a private cache; catalogs change only after all 42
videos have been encoded and their original frames and frame rates verified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

from export_gallery import aggregate, encode, publish_metadata, read_json, sha256, title, write_json


RUN = "robodojo42_astra_firstpass_20260919"
MANIFEST_SHA256 = "fe327cacc7615e868096a025c1287a8ad070408851bac9104cf132c1349f6fd4"
GROUPS = {"generalization": 12, "memory": 6, "precision": 8, "long-horizon": 8, "open": 8}
GROUP_NAMES = {"generalization": "Generalization", "memory": "Memory", "precision": "Precision",
               "long-horizon": "Long horizon", "open": "Open"}
CAMERAS = ["cam_head", "cam_left_wrist", "cam_right_wrist"]
ENCODING = {"codec": "h264", "pixelFormat": "yuv420p", "crf": 26, "maxRate": "1500k",
            "bufferSize": "3000k", "preset": "medium", "fastStart": True,
            "resize": False, "preserveFramesAndFps": True}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_audited_robodojo(run_dir, output_root):
    """Return a whitelisted benchmark, encoding jobs, provenance and read hashes."""
    root, output = Path(run_dir).resolve(), Path(output_root).resolve()
    require(root != output and not root.is_relative_to(output) and not output.is_relative_to(root),
            "Source run and output gallery must be separate")
    require(root.name == RUN, "Expected the completed RoboDojo first-pass run")
    reads = {}

    def read(path):
        path = Path(path)
        value = read_json(path)
        reads[path] = sha256(path)
        return value

    manifest = read(root / "manifest.json")
    mh = digest({key: value for key, value in manifest.items() if key != "manifest_sha256"})
    require(mh == manifest.get("manifest_sha256") == MANIFEST_SHA256, "Frozen manifest differs")
    config, specs = manifest["config"], manifest["episodes"]
    require(config["model"] == "gpt-6-astra" and config["reasoning_effort"] == "high"
            and config["workers"] == 8 and config["episodes_per_task"] == 1
            and config["seed_base"] == 0 and config["max_tool_calls"] == 1500,
            "Unexpected RoboDojo policy protocol")
    names = {s["task_name"] for s in specs}
    require(len(specs) == len(names) == 42 and Counter(s["task_group"] for s in specs) == GROUPS,
            "Expected all 42 basic tasks and native groups")
    require(all(s["variant"] == "standard" and s["rollout_id"] == 0 and s["seed"] == 0
                and not s["task_name"].endswith("_random")
                and s["max_steps"] == s["native_horizon"] for s in specs), "Unexpected task variant or horizon")
    require(len({s["prompt"] for s in specs}) == 1, "Policy prompts differ by task")
    for relative, expected in manifest["provenance"]["code_files"].items():
        path = root / "source_snapshot" / relative
        require(path.resolve().is_relative_to(root / "source_snapshot") and sha256(path) == expected,
                "Frozen source snapshot differs")
        reads[path] = expected

    audit_path, boundary_path = root / "reports/final_audit.json", root / "reports/final_policy_boundary_review.json"
    audit, boundary, summary = read(audit_path), read(boundary_path), read(root / "reports/summary.json")
    require(audit.get("passed") is True and audit.get("scope") == "all_42_basic_tasks"
            and audit.get("audited_episodes") == 42 and audit.get("videos_decoded") is True
            and audit.get("maximum_simultaneous_policy_episodes") == 8 and audit.get("issues") == [],
            "A complete successful 42-task video audit is required")
    require(boundary.get("passed") is True and boundary.get("full_scope_complete") is True
            and boundary.get("scope") == "all_42_terminal_episodes"
            and boundary.get("terminal_episodes_reviewed") == 42 and boundary.get("issues") == [],
            "A complete successful policy-boundary audit is required")
    require(all(record.get("manifest_sha256") == mh for record in (audit, boundary, summary)),
            "Audit and summary manifest identities differ")
    require(summary["overall"]["valid"] == summary["overall"]["total_attempts"] == 42
            and summary["overall"]["retries"] == summary["overall"]["errors"] == 0,
            "Source collection has missing episodes, retries or errors")

    def indexed(rows):
        result = {row["task_name"]: row for row in rows}
        require(len(rows) == len(result) == 42 and set(result) == names, "Incomplete or duplicated audit task coverage")
        return result

    audited, bounded, summarized = map(indexed, (audit["episodes"], boundary["episodes"], summary["episodes"]))
    tasks, jobs, selections = [], [], []
    for spec in specs:
        name, key = spec["task_name"], spec["episode_key"]
        require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name) and key == f"{name}_r00", "Invalid task identity")
        attempts = sorted((root / "episodes" / key).glob("attempt_*"))
        require(len(attempts) == 1 and attempts[0].name == "attempt_001", "Exactly one attempt is required")
        directory = attempts[0]
        result_path = directory / "result.json"
        result, env = read(result_path), read(directory / "env_result.json")
        a, b, s = audited[name], bounded[name], summarized[name]
        require(a["passed"] is True and b["passed"] is True and b["result_sha256"] == reads[result_path],
                "Result changed after the boundary audit")
        events = directory / "codex_events.jsonl"
        require(sha256(events) == b["event_log_sha256"], "Policy evidence changed after its audit")
        reads[events] = b["event_log_sha256"]
        require(result["manifest_sha256"] == env["manifest_sha256"] == mh
                and result["episode_key"] == env["episode_key"] == key,
                "Result assignment differs")
        require(result["status"] in {"success", "failure", "timeout"}
                and result["status"] == a["status"] == b["result_status"] == s["status"], "Unscored or changed outcome")
        require(result["environment"] == env and not env.get("error") and not env.get("invalid_native_layout")
                and env["policy_ready"] is True, "Invalid native environment result")
        require(type(env["success"]) is bool and env["success"] == result["success"]
                == (result["status"] == "success"), "Native success differs from the result")
        score = env["score"]
        require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 1
                and score == a["score"] == s["native_score"], "Invalid native score")
        require(type(env["steps"]) is int and 0 < env["steps"] <= spec["max_steps"]
                and env["steps"] == a["steps"] == s["steps"] == result["steps"], "Native action count differs")
        require(env["seed"] == env["layout_id"] == 0, "Unexpected evaluation layout")
        policy_audit = result["audit"]
        require(policy_audit.get("stream_complete") and not policy_audit.get("isolation_violation")
                and not policy_audit.get("sensor_transport_error"), "Invalid policy sensor or isolation evidence")
        video = Path(env["video"]["path"]).resolve()
        require(video.is_relative_to(directory.resolve()) and video.is_file() and str(video) == a["video"],
                "Source video is outside its selected attempt")
        instruction_record, native = read(video.with_name("instruction.json")), read(video.with_name("native_state.json"))
        require(reads[video.with_name("native_state.json")] == env.get("native_state_sha256"),
                "Native checkpoint changed after its result was finalized")
        instruction = instruction_record["instruction"]
        require(isinstance(instruction, str) and instruction.strip() and len(instruction) <= 10000,
                "Native instruction is missing")
        ih = hashlib.sha256(instruction.encode()).hexdigest()
        require(instruction_record.get("augmented") is False and ih == instruction_record["sha256"]
                == env["instruction_sha256"] == native["instruction_sha256"] == b["instruction_sha256"]
                == a["instruction_sha256"] == policy_audit["instruction_sha256"], "Native instruction parity differs")
        require(all(native[field] == env[field] for field in ("steps", "score", "success")), "Native checkpoint differs")
        metadata = env["video"]
        require(metadata["closed"] is True and not metadata.get("error") and metadata["fps"] == 25
                and metadata["width"] == 1920 and metadata["height"] == 480
                and metadata["frames"] == env["steps"] + 1 == a["decoded_frames"]
                and metadata["cameras_left_to_right"] == CAMERAS, "Native video protocol differs")
        tid = f"robodojo_{name.lower()}"
        eid = f"{tid}_r00"
        suite = f"robodojo_{spec['task_group'].replace('-', '_')}"
        episode = {"id": eid, "index": 0, "status": result["status"], "seed": 0, "initStateId": None,
                   "layoutId": 0, "steps": env["steps"], "maxSteps": spec["max_steps"],
                   "toolCalls": policy_audit["mcp_calls"], "wallSeconds": result["wall_seconds"],
                   "nativeScore": score, "terminationReason": result["reason"],
                   "durationSeconds": metadata["frames"] / 25, "video": f"media/robodojo/{eid}.mp4",
                   "poster": f"media/robodojo/{eid}.jpg", "width": 1920, "height": 480, "frames": metadata["frames"]}
        task = {"id": tid, "name": title(name), "nativeTaskName": name, "taskGroup": spec["task_group"],
                "instruction": instruction, "instructionSha256": ih, "suite": suite,
                "suiteName": GROUP_NAMES[spec["task_group"]], "episodes": [episode],
                "successes": int(env["success"]), "failures": int(not env["success"]), "successRate": float(env["success"])}
        selection = {"episode": eid, "sourceEpisodeKey": key, "selectedAttempt": "attempt_001",
                     "resultSha256": reads[result_path], "sourceVideoSha256": sha256(video),
                     "instructionSha256": ih, "nativeStateSha256": reads[video.with_name("native_state.json")],
                     "nativeSuccess": env["success"], "nativeScore": score, "status": result["status"],
                     "steps": env["steps"], "seed": 0, "excludedAttempts": []}
        tasks.append(task)
        selections.append(selection)
        jobs.append({"source": video, "episode": episode, "benchmark": "robodojo", "expectedFps": "25",
                     "selection": selection, "outputRoot": output, "encoding": ENCODING})
    counts = aggregate([t["episodes"][0] for t in tasks], 42)
    require(counts["successes"] == 6 and counts["failures"] == 36 and counts["timeouts"] == 0,
            "Native first-pass aggregate differs")
    source = {"benchmark": "robodojo", "run": RUN, "manifestSha256": mh,
              "auditKind": "robodojo_firstpass", "auditSha256": reads[audit_path],
              "policyBoundaryAuditSha256": reads[boundary_path], "selectedEpisodes": 42,
              "excludedAttemptCount": 0, "attemptSelection": selections}
    benchmark = {"id": "robodojo", "name": "RoboDojo", "evaluationDate": "2026-09-19",
                 "summary": counts, "tasks": tasks, "suites": [],
                 "provenance": {k: source[k] for k in ("run", "manifestSha256", "auditKind", "auditSha256", "policyBoundaryAuditSha256")},
                 "protocol": {"label": "42 basic tasks · 1 episode per task", "episodesPerTask": 1,
                              "description": "42 basic tasks, one independent Codex episode each, with eight simultaneous policies. Native VLA instructions are delivered verbatim, with no extra task descriptions. Policies see RGB and robot proprioception; no camera calibration, depth, reward or native success labels. All failures are retained and no episode was retried.",
                              "cameras": ["Head camera", "Left wrist", "Right wrist"], "stepsLabel": "Native actions",
                              "trainingDemoNote": "RoboDojo training demonstrations have not been imported into this gallery.",
                              "videoNote": "25 fps: initial frame and every native action, with head, left-wrist and right-wrist views side by side. All recorded frames and native dimensions are preserved; thinking and transport delays are omitted."}}
    for group in GROUPS:
        selected = [t for t in tasks if t["taskGroup"] == group]
        benchmark["suites"].append({"id": selected[0]["suite"], "name": GROUP_NAMES[group],
                                    **aggregate([t["episodes"][0] for t in selected], len(selected))})
    return benchmark, jobs, source, reads


def import_results(run_dir, output, workers=4, plan_only=False):
    output = Path(output).resolve()
    gallery_path, report_path = output / "data/gallery.json", output / "data/export-report.json"
    gallery, report = read_json(gallery_path), read_json(report_path)
    unchanged = {gallery_path: sha256(gallery_path), report_path: sha256(report_path)}
    require(report.get("complete") is True, "Existing gallery export must be complete")
    historical = [b for b in gallery["benchmarks"] if b["id"] != "robodojo"]
    old_media = [r for r in report["media"] if r["benchmark"] != "robodojo"]
    require({b["id"] for b in historical} == {"libero", "robotwin", "robocasa"} and len(old_media) == 815,
            "Expected the existing complete 815-episode gallery")
    benchmark, jobs, source, frozen_reads = load_audited_robodojo(run_dir, output)
    print(json.dumps({"planned": 42, "existingEpisodesPreserved": 815, "summary": benchmark["summary"],
                      "sourceBytes": sum(j["source"].stat().st_size for j in jobs)}), flush=True)
    if plan_only:
        return
    cache_path = output / ".gallery-cache/robodojo-export.json"
    cached = read_json(cache_path) if cache_path.exists() else {}
    prior = {r["episode"]: r for r in cached.get("media", [])} if cached.get("encoding") == ENCODING else {}
    if report.get("encodingByBenchmark", {}).get("robodojo") == ENCODING:
        prior.update({r["episode"]: r for r in report["media"] if r["benchmark"] == "robodojo"})
    complete = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(encode, job, prior.get(job["episode"]["id"])): job for job in jobs}
        for future in as_completed(futures):
            record = future.result()
            complete[record["episode"]] = record
            write_json(cache_path, {"encoding": ENCODING, "manifestSha256": MANIFEST_SHA256,
                                    "media": [complete[k] for k in sorted(complete)]})
            print(json.dumps({"encoded": len(complete), "total": 42, "episode": record["episode"]}), flush=True)
    require(len(complete) == 42, "Incomplete RoboDojo encoding")
    for path, expected in {**unchanged, **frozen_reads}.items():
        require(sha256(path) == expected, "Source evidence or existing gallery changed during import")
    # Whitelist validation before these dictionaries enter the public catalog.
    from validate_gallery import public_metadata
    public_metadata(benchmark, "robodojo")
    public_metadata(source, "robodojo provenance")
    result_gallery, result_report = deepcopy(gallery), deepcopy(report)
    timestamp = datetime.now(timezone.utc).isoformat()
    result_gallery.update(generatedAt=timestamp, evaluationDate="2026-09-19",
                          evaluationDates=["2026-09-17", "2026-09-18", "2026-09-19"],
                          benchmarks=[*historical, benchmark])
    records = [*old_media, *[complete[j["episode"]["id"]] for j in jobs]]
    result_report.update(generatedAt=timestamp, complete=True,
                         runs=[*[r for r in report["runs"] if r["benchmark"] != "robodojo"], source],
                         media=records, expectedEpisodes=857, verifiedEpisodes=857)
    result_report["selectionRule"] = report["selectionRule"].split(" RoboDojo uses")[0] + " RoboDojo uses exactly one attempt for each of its 42 basic tasks, verified by the complete native/video and policy-boundary audits."
    result_report.setdefault("encodingByBenchmark", {})["robodojo"] = ENCODING
    for field in ("sourceBytes", "videoBytes", "posterBytes"):
        result_report[field] = sum(r[field] for r in records)
    result_report["publishedMediaBytes"] = result_report["videoBytes"] + result_report["posterBytes"]
    result_report["externalVideoBytes"] = sum(r["videoBytes"] for r in records if r["benchmark"] in result_report["videoHosting"])
    result_report["pagesMediaBytes"] = result_report["publishedMediaBytes"] - result_report["externalVideoBytes"]
    require(result_report["pagesMediaBytes"] < 800_000_000, "Presentation media exceeds the existing budget")
    result_report["validation"].update(expectedEpisodes=857, verifiedEpisodes=857,
                                       decodedFrameCount=sum(r["frames"] for r in records),
                                       allFramesAndFpsPreserved=all(r["verified"] for r in records),
                                       allBrowserH264Yuv420pFastStart=all(r["codec"] == "h264" and r["pixelFormat"] == "yuv420p" and r["fastStart"] for r in records),
                                       sourceFilesUnmodified=True, within800MBPagesMediaBudget=True)
    write_json(report_path, result_report)
    publish_metadata(output, result_gallery)
    print(json.dumps({"complete": True, "tasks": 497, "episodes": 857,
                      "robodojoVideoBytes": sum(r["videoBytes"] for r in complete.values()),
                      "robodojoFrames": sum(r["frames"] for r in complete.values())}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--jobs", type=int, choices=range(1, 7), default=4)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    import_results(args.run_dir, args.output, args.jobs, args.plan_only)


if __name__ == "__main__":
    main()
