"""Load a completed, hash-bound RoboCasa365 collection for the gallery.

Only a full collection audit is publishable, including a primary-only collection.
Legacy audit_robocasa_run reports lack result/video fingerprints and are rejected:
run audit_robocasa_collection.py without --task or --allow-partial first.
This adapter reads evidence only; it never starts an episode or writes an export.
All public dictionaries are constructed from a whitelist, never copied from logs.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re


CAMERAS = ["robot0_agentview_left", "robot0_agentview_right", "robot0_eye_in_hand"]
VALID_STATUSES = {"success", "failure", "timeout"}
INFRA_REASONS = {"simulation_error", "codex_error", "video_recording_error"}


class RoboCasaExportError(ValueError):
    """The source is incomplete, changed, or outside the audited selection."""


def require(condition, message):
    if not condition:
        raise RoboCasaExportError(message)


def read_json(path):
    return json.loads(Path(path).read_text())


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def artifact_fingerprint(directory):
    return digest([[str(path.relative_to(directory)), path.stat().st_size, path.stat().st_mtime_ns]
                   for path in sorted(directory.rglob("*")) if path.is_file()])


def identifier(value, label):
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", value),
            f"Invalid public {label}")
    return value


def positive_integer(value, label, *, zero=False):
    require(type(value) is int and value >= (0 if zero else 1), f"Invalid {label}")
    return value


def summary(episodes, tasks):
    counts = Counter(episode["status"] for episode in episodes)
    return {"tasks": tasks, "episodes": len(episodes), "successes": counts["success"],
            "failures": counts["failure"] + counts["timeout"], "timeouts": counts["timeout"],
            "successRate": counts["success"] / len(episodes)}


def instruction_from_reset(video, spec):
    with video.with_name("actions.jsonl").open() as stream:
        reset = json.loads(stream.readline())
    require(reset.get("event") == "reset" and reset.get("task_name") == spec["task_name"]
            and reset.get("seed") == spec["seed"] and reset.get("max_steps") == spec["max_steps"],
            "Reset instruction belongs to a different task or seed")
    language = reset.get("language")
    require(isinstance(language, str) and language.strip() and len(language) <= 10000
            and not re.search(r"\{[^}]+\}|(?:^|[\s\"'=])/(?:home|playpen|tmp|Users|root|mnt|private)/", language)
            and not any(marker in language.lower() for marker in ("auth.json", "codex_home", "codex-events.jsonl"))
            and not re.search(r"\bsk-[A-Za-z0-9_-]{20,}\b", language), "Unsafe or unresolved public task instruction")
    return language


def load_audited_robocasa(source_root, audit_path, output_root):
    """Return (benchmark, encoding jobs, public provenance), without writing files."""
    source_root, audit_path, output_root = map(lambda p: Path(p).resolve(), (source_root, audit_path, output_root))
    require(output_root != source_root and not output_root.is_relative_to(source_root)
            and not source_root.is_relative_to(output_root), "Source and output directories must be separate")
    audit_hash = sha256(audit_path)
    audit = read_json(audit_path)
    require("selections" in audit and "plan_sha256" in audit,
            "A full hash-bound collection audit is required; run audit_robocasa_collection.py without --task or --allow-partial")
    require(audit.get("schema_version") == 1 and audit.get("passed") is True
            and audit.get("full_goal_complete") is True and audit.get("scope_complete") is True
            and audit.get("scope") == "all_365_tasks" and audit.get("allow_partial") is False
            and audit.get("valid_episodes") == 365 and audit.get("issues") == [] and audit.get("unresolved") == []
            and audit.get("primary_peak_initialized_policy_concurrency") == 8
            and type(audit.get("registered_peak_attempt_wall_overlap")) is int
            and 1 <= audit["registered_peak_attempt_wall_overlap"] <= 8,
            "RoboCasa collection is incomplete, partial, or failed its final audit")
    plan_path = Path(audit["plan"]).resolve()
    require(sha256(plan_path) == audit["plan_sha256"], "Collection plan changed after audit")
    plan = read_json(plan_path)
    require(plan.get("schema_version") == 1 and isinstance(plan.get("replacement_candidates"), list), "Invalid collection plan")
    entries = [plan["primary"], *plan["replacement_candidates"]]
    sources, ordered_sources, frozen_reads = {}, [], {audit_path: audit_hash, plan_path: audit["plan_sha256"]}
    for entry in entries:
        candidate = Path(entry["run_dir"])
        root = (candidate if candidate.is_absolute() else plan_path.parent / candidate).resolve()
        require(root.is_relative_to(source_root) and root != source_root and root not in sources, "Invalid or duplicate source run")
        run_name = identifier(root.name, "run name")
        require(run_name not in {s["public"]["run"] for s in ordered_sources}, "Ambiguous public source run name")
        manifest_path = root / "manifest.json"
        manifest = read_json(manifest_path)
        manifest_hash = digest({key: value for key, value in manifest.items() if key != "manifest_sha256"})
        require(manifest_hash == manifest.get("manifest_sha256") == entry["manifest_sha256"], "Source manifest changed after audit")
        frozen_reads[manifest_path] = sha256(manifest_path)
        config = manifest["config"]
        require(config.get("model") == "gpt-6-astra" and config.get("reasoning_effort") == "high"
                and config.get("workers") == 8 and config.get("episodes_per_task") == 1
                and config.get("max_tool_calls") == 1500 and config.get("image_size") == 512
                and manifest.get("protocol", {}).get("base_seed") == config.get("seed_base"), "Unexpected RoboCasa protocol")
        specs = manifest["episodes"]
        require(len(specs) == 365 and len({s["task_name"] for s in specs}) == 365
                and Counter(s["task_group"] for s in specs) == {"atomic": 65, "composite": 300}, "Incomplete RoboCasa task catalog")
        for spec in specs:
            identifier(spec["task_name"], "task name")
            require(spec.get("episode_key") == f"{spec['task_name']}_r00" and spec.get("rollout_id") == 0
                    and spec.get("seed") == config["seed_base"] and spec.get("max_tool_calls") == 1500
                    and spec.get("image_size") == 512, "Incorrect source episode identity or protocol")
        source = {"root": root, "manifest": manifest, "specs": {s["task_name"]: s for s in specs}, "entry": entry,
                  "public": {"run": run_name, "manifestSha256": manifest_hash, "seedBase": config["seed_base"]}}
        sources[root] = source
        ordered_sources.append(source)
    primary = ordered_sources[0]
    require(primary["public"]["seedBase"] == 100000, "Unexpected primary seed")
    require(audit["source_manifests"] == [{"run_dir": str(s["root"]), "manifest_sha256": s["public"]["manifestSha256"]}
                                          for s in ordered_sources], "Audit source registry differs from the collection plan")
    names = set(primary["specs"])
    candidate_seeds = Counter()
    for source in ordered_sources[1:]:
        entry = source["entry"]
        name = entry["task_name"]
        require(name in names and entry["seed"] == 100001 + candidate_seeds[name]
                and source["public"]["seedBase"] == entry["seed"], "Replacement seeds are not sequential")
        candidate_seeds[name] += 1
        require(set(source["specs"]) == names, "Supplemental task catalog differs")
        def without_seed(manifest):
            return {**{k: v for k, v in manifest.items() if k not in {"created_at", "manifest_sha256", "config", "protocol", "episodes"}},
                    "config": {k: v for k, v in manifest["config"].items() if k != "seed_base"},
                    "protocol": {k: v for k, v in manifest["protocol"].items() if k != "base_seed"},
                    "episodes": [{k: v for k, v in item.items() if k != "seed"} for item in manifest["episodes"]]}
        require(without_seed(source["manifest"]) == without_seed(primary["manifest"]), "Supplemental experiment configuration differs")
    selections = audit["selections"]
    require(len(selections) == 365 and {row["task_name"] for row in selections} == names,
            "Audit must select every task exactly once")
    proofs = {}
    for kind, items in (("initial", audit["excluded_initial_native_successes"]),
                        ("infrastructure", audit["prior_infrastructure_retry_proofs"])):
        for proof in items:
            directory = Path(proof["attempt_dir"]).resolve()
            require(directory not in proofs and proof.get("proof_passed") is True, "Invalid or duplicated exclusion proof")
            proofs[directory] = (kind, proof)
    used_proofs, selected_directories, used_videos = set(), set(), set()
    excluded_fingerprints = {}
    tasks, jobs, public_selections = [], [], []
    for row in selections:
        require(row.get("passed") is True and row.get("status") in VALID_STATUSES, "Unscored audit selection")
        source = sources.get(Path(row["run_dir"]).resolve())
        require(source is not None, "Selected run is not registered")
        name = row["task_name"]
        spec = source["specs"][name]
        require(source is primary or source["entry"]["task_name"] == name, "Replacement run selected for another task")
        expected_directory = source["root"] / "episodes" / spec["episode_key"] / identifier(row["attempt"], "attempt")
        directory = Path(row["attempt_dir"]).resolve()
        require(directory == expected_directory and directory not in selected_directories, "Selected attempt identity differs")
        require(row.get("manifest_sha256") == source["public"]["manifestSha256"]
                and row.get("seed") == spec["seed"] and row.get("episode_key") == spec["episode_key"], "Selected source/seed mismatch")
        fingerprint = artifact_fingerprint(directory)
        require(fingerprint == row["artifact_fingerprint"], "Selected attempt changed after audit")
        result_path = directory / "result.json"
        require(sha256(result_path) == row["result_sha256"], "Selected result changed after audit")
        result = read_json(result_path)
        environment = read_json(directory / "env_result.json")
        require(result.get("environment") == environment and result.get("episode_key") == spec["episode_key"]
                and result.get("manifest_sha256") == source["public"]["manifestSha256"]
                and environment.get("task_name") == name and environment.get("seed") == spec["seed"]
                and environment.get("max_steps") == spec["max_steps"], "Selected native result identity differs")
        steps = positive_integer(result.get("steps"), "selected native steps")
        require(result.get("status") == row["status"] and result.get("success") is (row["status"] == "success")
                and environment.get("success") is result["success"] and not environment.get("error")
                and steps == environment.get("steps") == row.get("steps") == row.get("native_actions")
                and steps <= spec["max_steps"] and row.get("native_score") == int(result["success"]), "Selected outcome differs from audit")
        tool_calls = positive_integer(environment.get("tool_calls"), "tool calls", zero=True)
        require(tool_calls <= 1500, "Tool budget exceeded")
        wall = result.get("wall_seconds")
        require(type(wall) in (int, float) and math.isfinite(wall) and wall >= 0, "Invalid episode wall time")
        metadata = environment["video"]
        video = Path(metadata["path"])
        require(video.is_absolute() and video.is_relative_to(directory / "frames") and video.name == "rollout.mp4"
                and str(video) == row["video"] and video.resolve() not in used_videos, "Selected recording path differs or is reused")
        require(read_json(video.with_name("video.json")) == metadata and metadata.get("closed") is True
                and metadata.get("error") is None and metadata.get("fps") == 20 and metadata.get("codec") == "h264"
                and metadata.get("frames") == steps + 1 == row.get("video_frames")
                and metadata.get("width") == 1536 and metadata.get("height") == 512
                and metadata.get("cameras_left_to_right") == CAMERAS
                and metadata.get("includes_initial_frame") is True and metadata.get("includes_warmup") is False,
                "Selected recording metadata differs from the RoboCasa protocol")
        video_hash = sha256(video)
        require(video_hash == row["video_sha256"], "Selected video changed after audit")
        language = instruction_from_reset(video, spec)
        excluded = []
        for prior_source in ordered_sources:
            if prior_source is not primary and prior_source["entry"]["task_name"] != name:
                continue
            task_directory = prior_source["root"] / "episodes" / spec["episode_key"]
            attempts = sorted(task_directory.glob("attempt_*"))
            require([p.name for p in attempts] == [f"attempt_{i:03d}" for i in range(1, len(attempts) + 1)], "Missing retained attempt")
            if prior_source is source:
                require(attempts and attempts[-1] == directory and len(attempts) == row["attempts"], "Audited attempt is no longer final")
            for prior in attempts:
                if prior == directory:
                    continue
                require(prior in proofs, "Retained attempt has no independent exclusion proof")
                kind, proof = proofs[prior]
                old_fingerprint = artifact_fingerprint(prior)
                require(old_fingerprint == proof.get("artifact_fingerprint"), "Excluded evidence changed after audit")
                old_path = prior / "result.json"
                old_hash = sha256(old_path)
                require(old_hash == proof["result_sha256"], "Excluded result changed after audit")
                old = read_json(old_path)
                env = old["environment"]
                require(old.get("status") == "error" and old.get("reason") in INFRA_REASONS
                        and old.get("episode_key") == spec["episode_key"]
                        and old.get("manifest_sha256") == prior_source["public"]["manifestSha256"]
                        and env.get("task_name") == name and env.get("seed") == prior_source["public"]["seedBase"] == proof["seed"],
                        "Excluded attempt identity or outcome differs")
                old_video = Path(env["video"]["path"])
                require(old_video.is_absolute() and old_video.is_relative_to(prior / "frames"), "Excluded recording outside its attempt")
                old_video_hash = sha256(old_video)
                require(old_video_hash == proof.get("video_sha256"), "Excluded video changed after audit")
                if kind == "initial":
                    require(old_video_hash == proof["video_sha256"] and old.get("steps") == 0
                            and env.get("success") is True and env.get("error") == "RuntimeError: Initial scene already satisfies the task"
                            and proof.get("native_actions") == proof.get("visual_observations") == 0
                            and proof.get("counted_as_valid_success") is False, "Invalid initial-scene exclusion")
                else:
                    require(proof.get("counts_as_valid_policy_episode") is False and old.get("steps") == proof.get("native_actions")
                            and env.get("success") is False, "Invalid infrastructure exclusion")
                    extra = proof.get("video_probe_timeout_exception")
                    if extra:
                        require(old_video_hash == extra["video_sha256"], "Excluded recovered recording changed after audit")
                excluded.append({"run": prior_source["public"]["run"], "manifestSha256": prior_source["public"]["manifestSha256"],
                                 "sourceEpisodeKey": spec["episode_key"], "seed": env["seed"], "attempt": prior.name,
                                 "status": old["status"], "reason": old["reason"], "steps": old["steps"],
                                 "visualObservations": old["audit"]["visual_observations"], "nativeSuccess": env["success"],
                                 "countsAsValidEpisode": False, "countedAsValidSuccess": False,
                                 "resultSha256": old_hash, "videoSha256": old_video_hash})
                require(artifact_fingerprint(prior) == old_fingerprint, "Excluded evidence changed while preparing export")
                excluded_fingerprints[prior] = old_fingerprint
                frozen_reads[old_path] = old_hash
                frozen_reads[old_video] = old_video_hash
                used_proofs.add(prior)
        task_id = f"robocasa_{name.lower()}"
        episode = {"id": f"{task_id}_r00", "index": 0, "status": result["status"], "seed": spec["seed"], "initStateId": None,
                   "steps": steps, "maxSteps": spec["max_steps"], "toolCalls": tool_calls, "wallSeconds": wall,
                   "durationSeconds": metadata["frames"] / 20, "video": f"media/robocasa/{task_id}_r00.mp4",
                   "poster": f"media/robocasa/{task_id}_r00.jpg", "width": 1536, "height": 512, "frames": metadata["frames"]}
        group = spec["task_group"]
        task = {"id": task_id, "name": re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name), "instruction": language,
                "suite": f"robocasa_{group}", "suiteName": "Atomic" if group == "atomic" else "Composite", "episodes": [episode],
                "successes": int(result["success"]), "failures": int(not result["success"]), "successRate": float(result["success"])}
        selection = {"episode": episode["id"], "sourceEpisodeKey": spec["episode_key"], "run": source["public"]["run"],
                     "manifestSha256": source["public"]["manifestSha256"], "seed": spec["seed"], "selectedAttempt": directory.name,
                     "status": result["status"], "steps": steps, "nativeScore": int(result["success"]),
                     "resultSha256": row["result_sha256"], "sourceVideoSha256": video_hash, "excludedAttempts": excluded}
        require(artifact_fingerprint(directory) == fingerprint, "Selected evidence changed while preparing export")
        selected_directories.add(directory)
        used_videos.add(video.resolve())
        frozen_reads[result_path] = row["result_sha256"]
        tasks.append(task)
        public_selections.append(selection)
        jobs.append({"source": video, "episode": episode, "benchmark": "robocasa", "expectedFps": "20",
                     "selection": selection, "outputRoot": output_root})
    require(used_proofs == set(proofs) and len({task["id"] for task in tasks}) == 365, "Unaccounted exclusion or colliding public task ID")
    for source in ordered_sources:
        actual = {p.resolve() for p in (source["root"] / "episodes").glob("*/attempt_*")}
        expected = {p for p in selected_directories | used_proofs if p.is_relative_to(source["root"])}
        require(actual == expected, "Source contains an unaccounted or newly created attempt")
    episodes = [job["episode"] for job in jobs]
    counts = Counter(ep["status"] for ep in episodes)
    require(dict(counts) == audit["status_counts"] and counts["success"] == audit["successes"]
            and counts["failure"] + counts["timeout"] == audit["scored_failures"], "Final outcome counts differ from audit")
    require(all(sha256(path) == expected for path, expected in frozen_reads.items()),
            "Audit, plan, manifest, results or excluded video changed while preparing export")
    require(all(artifact_fingerprint(path) == expected for path, expected in excluded_fingerprints.items()),
            "Excluded evidence changed while preparing export")
    public_sources = [source["public"] for source in ordered_sources]
    common = {"run": primary["public"]["run"], "manifestSha256": primary["public"]["manifestSha256"],
              "auditSha256": audit_hash, "auditKind": "robocasa_collection", "planSha256": audit["plan_sha256"], "sources": public_sources}
    suites = []
    for group in ("atomic", "composite"):
        subset = [task for task in tasks if task["suite"] == f"robocasa_{group}"]
        suites.append({"id": f"robocasa_{group}", "name": "Atomic" if group == "atomic" else "Composite",
                       **summary([task["episodes"][0] for task in subset], len(subset))})
    benchmark = {"id": "robocasa", "name": "RoboCasa365", "evaluationDate": datetime.fromisoformat(primary["manifest"]["created_at"]).date().isoformat(),
                 "summary": summary(episodes, 365), "suites": suites, "tasks": tasks, "provenance": common,
                 "protocol": {"label": "First pass · 1 valid episode per task", "episodesPerTask": 1,
                              "description": "All 65 atomic and 300 composite tasks, one independently audited policy episode each. Native task predicates determine success; failures and timeouts are retained. Infrastructure and initial-scene rejections are excluded with provenance.",
                              "cameras": ["Agent view left", "Agent view right", "Wrist camera"],
                              "videoNote": "20 fps: initial frame and every native robot action. All three camera views and recorded frames are preserved; inference waiting time is omitted.",
                              "stepsLabel": "Native actions"}}
    provenance = {**common, "benchmark": "robocasa", "selectedEpisodes": 365,
                  "excludedAttemptCount": sum(len(item["excludedAttempts"]) for item in public_selections), "attemptSelection": public_selections}
    return benchmark, jobs, provenance
