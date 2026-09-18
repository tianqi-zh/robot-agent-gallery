"""Synthetic complete collections and read-only rejection of real partial audits."""
import copy
import importlib.util
import json
import os
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/robocasa_export.py"
spec = importlib.util.spec_from_file_location("robocasa_export", MODULE_PATH)
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def make_manifest(root, seed=100000):
    specs = [{"task_name": f"Task{i:03d}", "episode_key": f"Task{i:03d}_r00", "task_group": "atomic" if i < 65 else "composite",
              "rollout_id": 0, "seed": seed, "max_steps": 400, "max_tool_calls": 1500, "image_size": 512} for i in range(365)]
    manifest = {"created_at": "2026-09-18T05:56:37+00:00", "protocol": {"base_seed": seed},
                "config": {"seed_base": seed, "model": "gpt-6-astra", "reasoning_effort": "high", "workers": 8,
                           "episodes_per_task": 1, "max_tool_calls": 1500, "image_size": 512}, "episodes": specs}
    manifest["manifest_sha256"] = export.digest(manifest)
    write(root / "manifest.json", manifest)
    return manifest


def make_attempt(root, manifest, index, number=1, status="success", initial=False):
    spec = manifest["episodes"][index]
    directory = root / "episodes" / spec["episode_key"] / f"attempt_{number:03d}"
    scene = directory / "frames/scene"
    scene.mkdir(parents=True, exist_ok=True)
    video = scene / "rollout.mp4"
    video.write_bytes(f"synthetic-video-{root.name}-{index}-{number}".encode())
    steps = 0 if initial else 1
    metadata = {"path": str(video), "frame_index": str(scene / "video_frames.jsonl"), "fps": 20, "codec": "h264",
                "frames": steps + 1, "closed": True, "error": None, "width": 1536, "height": 512,
                "cameras_left_to_right": export.CAMERAS, "includes_initial_frame": True, "includes_warmup": False}
    environment = {"task_name": spec["task_name"], "seed": spec["seed"], "max_steps": 400,
                   "steps": steps, "success": status == "success" or initial, "tool_calls": 1,
                   "error": "RuntimeError: Initial scene already satisfies the task" if initial else None, "video": metadata}
    result = {"episode_key": spec["episode_key"], "manifest_sha256": manifest["manifest_sha256"], "status": status,
              "reason": "simulation_error" if initial else "codex_error" if status == "error" else "test_outcome",
              "steps": steps, "success": status == "success", "wall_seconds": 1.5, "environment": environment,
              "audit": {"visual_observations": 0 if initial else 1, "thread_ids": ["PRIVATE-THREAD-DO-NOT-EXPORT"]}}
    write(directory / "result.json", result)
    write(directory / "env_result.json", environment)
    write(scene / "video.json", metadata)
    write(scene / "actions.jsonl", {"event": "reset", "task_name": spec["task_name"], "seed": spec["seed"],
                                   "max_steps": 400, "language": f"Perform task {index} from RGB observations."})
    row = {"task_name": spec["task_name"], "episode_key": spec["episode_key"], "run_dir": str(root),
           "manifest_sha256": manifest["manifest_sha256"], "seed": spec["seed"], "attempt": directory.name,
           "attempt_dir": str(directory), "attempts": number, "passed": True, "status": status,
           "steps": steps, "native_actions": steps, "native_score": int(status == "success"),
           "video": str(video), "video_frames": steps + 1, "video_sha256": export.sha256(video),
           "result_sha256": export.sha256(directory / "result.json"), "artifact_fingerprint": export.artifact_fingerprint(directory),
           "threads": ["PRIVATE-THREAD-DO-NOT-EXPORT"]}
    return row


def bundle(tmp_path, *, replacement=False, retry=False):
    source_root = tmp_path / "runs"
    root = source_root / "primary"
    manifest = make_manifest(root)
    rows = [make_attempt(root, manifest, i, status=("success", "failure", "timeout")[i % 3]) for i in range(365)]
    initial, infrastructure = [], []
    plan = {"schema_version": 1, "primary": {"run_dir": str(root), "manifest_sha256": manifest["manifest_sha256"]},
            "replacement_candidates": []}
    sources = [plan["primary"].copy()]
    if replacement:
        for number in (1, 2):
            row = make_attempt(root, manifest, 0, number, status="error", initial=True)
            initial.append({"attempt_dir": row["attempt_dir"], "seed": 100000, "proof_passed": True,
                            "result_sha256": row["result_sha256"], "video_sha256": row["video_sha256"],
                            "artifact_fingerprint": row["artifact_fingerprint"],
                            "native_actions": 0, "visual_observations": 0, "counted_as_valid_success": False})
        supplemental = source_root / "supplemental"
        other = make_manifest(supplemental, 100001)
        rows[0] = make_attempt(supplemental, other, 0, status="failure")
        entry = {"run_dir": str(supplemental), "manifest_sha256": other["manifest_sha256"]}
        sources.append(entry)
        plan["replacement_candidates"].append({**entry, "task_name": "Task000", "seed": 100001})
    if retry:
        old = make_attempt(root, manifest, 1, status="error")
        infrastructure.append({"attempt_dir": old["attempt_dir"], "seed": 100000, "proof_passed": True,
                               "result_sha256": old["result_sha256"], "native_actions": 1,
                               "video_sha256": old["video_sha256"], "artifact_fingerprint": old["artifact_fingerprint"],
                               "counts_as_valid_policy_episode": False})
        rows[1] = make_attempt(root, manifest, 1, 2, status="timeout")
    plan_path = tmp_path / "plan.json"
    write(plan_path, plan)
    counts = dict(__import__("collections").Counter(row["status"] for row in rows))
    audit = {"schema_version": 1, "passed": True, "full_goal_complete": True, "scope_complete": True,
             "scope": "all_365_tasks", "allow_partial": False, "valid_episodes": 365, "issues": [], "unresolved": [],
             "primary_peak_initialized_policy_concurrency": 8, "registered_peak_attempt_wall_overlap": 8,
             "plan": str(plan_path), "plan_sha256": export.sha256(plan_path), "source_manifests": sources,
             "selections": rows, "excluded_initial_native_successes": initial, "prior_infrastructure_retry_proofs": infrastructure,
             "status_counts": counts, "successes": counts["success"], "scored_failures": counts["failure"] + counts["timeout"],
             "private_report_note": "/home/private/DO-NOT-EXPORT", "threads": ["PRIVATE-THREAD-DO-NOT-EXPORT"]}
    path = tmp_path / "audit.json"
    write(path, audit)
    return source_root, path, tmp_path / "output", audit


@pytest.mark.parametrize("replacement,retry", [(False, False), (True, True)])
def test_complete_collection_exports_every_outcome_and_only_public_fields(tmp_path, replacement, retry):
    source, path, output, audit = bundle(tmp_path, replacement=replacement, retry=retry)
    benchmark, jobs, provenance = export.load_audited_robocasa(source, path, output)
    assert len(jobs) == benchmark["summary"]["episodes"] == 365
    assert [suite["tasks"] for suite in benchmark["suites"]] == [65, 300]
    assert {job["episode"]["status"] for job in jobs} == {"success", "failure", "timeout"}
    assert all(job["expectedFps"] == "20" and job["source"].is_file() for job in jobs)
    assert provenance["excludedAttemptCount"] == (3 if replacement else 0)
    if replacement:
        first = provenance["attemptSelection"][0]
        assert first["run"] == "supplemental" and first["seed"] == 100001 and first["status"] == "failure"
        assert [old["nativeSuccess"] for old in first["excludedAttempts"]] == [True, True]
        assert all(old["countsAsValidEpisode"] is False for old in first["excludedAttempts"])
        assert provenance["attemptSelection"][1]["selectedAttempt"] == "attempt_002"
    public = json.dumps([benchmark, provenance])
    assert "PRIVATE-THREAD" not in public and "private_report_note" not in public and str(tmp_path) not in public
    assert not output.exists()  # Preparing the export is read-only.


@pytest.mark.parametrize("change", ["partial", "scoped", "not_complete", "issue", "duplicate_task", "error_selection",
                                    "result_changed", "video_changed", "wrong_seed", "unlisted_attempt", "wrong_plan", "wrong_manifest"])
def test_incomplete_or_changed_evidence_is_rejected(tmp_path, change):
    if change in {"partial", "scoped", "not_complete", "issue"}:
        # Gate tests need no source artifacts at all.
        path = tmp_path / "audit.json"
        audit = {"selections": [], "plan_sha256": "0" * 64, "schema_version": 1, "passed": True,
                 "full_goal_complete": True, "scope_complete": True, "scope": "all_365_tasks", "allow_partial": False,
                 "valid_episodes": 365, "issues": [], "unresolved": [], "primary_peak_initialized_policy_concurrency": 8,
                 "registered_peak_attempt_wall_overlap": 8}
        audit.update({"partial": {"allow_partial": True}, "scoped": {"scope": "Task000"},
                      "not_complete": {"full_goal_complete": False}, "issue": {"issues": ["unexpected"]}}[change])
        source, output = tmp_path / "runs", tmp_path / "output"
    else:
        source, path, output, audit = bundle(tmp_path)
        row = audit["selections"][0]
        if change == "duplicate_task":
            audit["selections"][1] = copy.deepcopy(row)
        elif change == "error_selection":
            row["status"] = "error"
        elif change == "result_changed":
            with (Path(row["attempt_dir"]) / "result.json").open("a") as stream:
                stream.write(" ")
        elif change == "video_changed":
            Path(row["video"]).write_bytes(b"different-video")
        elif change == "wrong_seed":
            row["seed"] = 100002
        elif change == "unlisted_attempt":
            (Path(row["attempt_dir"]).parent / "attempt_002").mkdir()
        elif change == "wrong_plan":
            Path(audit["plan"]).write_text("{}")
        elif change == "wrong_manifest":
            manifest = Path(row["run_dir"]) / "manifest.json"
            value = json.loads(manifest.read_text())
            value["config"]["workers"] = 1
            write(manifest, value)
    write(path, audit)
    with pytest.raises(export.RoboCasaExportError):
        export.load_audited_robocasa(source, path, output)
    assert not output.exists()


def test_unproven_excluded_attempt_cannot_be_hidden(tmp_path):
    source, path, output, audit = bundle(tmp_path, replacement=True)
    audit["excluded_initial_native_successes"].pop()
    write(path, audit)
    with pytest.raises(export.RoboCasaExportError, match="no independent exclusion proof"):
        export.load_audited_robocasa(source, path, output)


def excluded_proof(audit, kind):
    return audit["excluded_initial_native_successes" if kind == "initial" else "prior_infrastructure_retry_proofs"][0]


def change_excluded_evidence(proof, change):
    directory = Path(proof["attempt_dir"])
    if change == "video":
        video = next((directory / "frames").glob("*/rollout.mp4"))
        before = video.stat()
        original = video.read_bytes()
        video.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        # Keep the directory fingerprint unchanged to exercise the independent
        # audit-bound video SHA, rather than merely detecting changed metadata.
        os.utime(video, ns=(before.st_atime_ns, before.st_mtime_ns))
        assert export.artifact_fingerprint(directory) == proof["artifact_fingerprint"]
    else:
        raw = next((directory / "frames").glob("*/actions.jsonl"))
        with raw.open("a") as stream:
            stream.write('{"event":"unexpected_action"}\n')


@pytest.mark.parametrize("kind", ["initial", "infrastructure"])
@pytest.mark.parametrize("change", ["video", "raw"])
def test_excluded_video_and_raw_evidence_are_bound_to_final_audit(tmp_path, kind, change):
    source, path, output, audit = bundle(tmp_path, replacement=kind == "initial", retry=kind == "infrastructure")
    change_excluded_evidence(excluded_proof(audit, kind), change)
    with pytest.raises(export.RoboCasaExportError, match="Excluded (video|evidence) changed after audit"):
        export.load_audited_robocasa(source, path, output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["initial", "infrastructure"])
@pytest.mark.parametrize("field", ["video_sha256", "artifact_fingerprint"])
def test_excluded_attempt_requires_both_final_audit_bindings(tmp_path, kind, field):
    source, path, output, audit = bundle(tmp_path, replacement=kind == "initial", retry=kind == "infrastructure")
    del excluded_proof(audit, kind)[field]
    write(path, audit)
    with pytest.raises(export.RoboCasaExportError, match="Excluded (video|evidence) changed after audit"):
        export.load_audited_robocasa(source, path, output)


@pytest.mark.parametrize("kind", ["initial", "infrastructure"])
@pytest.mark.parametrize("change", ["video", "raw"])
def test_excluded_evidence_stays_stable_until_export_preparation_finishes(tmp_path, monkeypatch, kind, change):
    source, path, output, audit = bundle(tmp_path, replacement=kind == "initial", retry=kind == "infrastructure")
    original = export.instruction_from_reset
    changes = []

    def read_next_task(video, spec):
        if spec["task_name"] == "Task002":
            # The excluded Task000/Task001 attempt has already been checked.
            change_excluded_evidence(excluded_proof(audit, kind), change)
            changes.append(change)
        return original(video, spec)

    monkeypatch.setattr(export, "instruction_from_reset", read_next_task)
    with pytest.raises(export.RoboCasaExportError, match="changed while preparing export"):
        export.load_audited_robocasa(source, path, output)
    assert changes == [change] and not output.exists()


def test_legacy_full_run_report_requires_hash_bound_collection(tmp_path):
    path = tmp_path / "audit.json"
    write(path, {"passed": True, "full_goal_complete": True, "episodes_audited": 365, "episodes": []})
    with pytest.raises(export.RoboCasaExportError, match="hash-bound collection audit"):
        export.load_audited_robocasa(tmp_path / "runs", path, tmp_path / "output")


def test_existing_real_partial_collection_is_not_publishable(tmp_path):
    run = Path('/playpen/tianqi/code/robot-agent/eval_runs/robocasa365_astra_firstpass_20260918')
    path = run / 'reports/collection_preflight/valid_episode_partial.json'
    if not path.exists():
        pytest.skip('Read-only local evaluation fixture is not installed')
    before = export.sha256(path)
    with pytest.raises(export.RoboCasaExportError, match="incomplete, partial"):
        export.load_audited_robocasa(run.parent, path, tmp_path / "output")
    assert export.sha256(path) == before and not (tmp_path / "output").exists()
