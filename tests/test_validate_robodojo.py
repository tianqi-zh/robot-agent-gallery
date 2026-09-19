"""Synthetic RoboDojo publication metadata: no simulator, private run, or network."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_gallery import aggregate, publish_metadata
from validate_gallery import (EXPECTED_RUNS, ROBODOJO_HORIZONS, ROBODOJO_TASKS,
                              ValidationError, probe_video, validate_gallery)
import test_validate_robocasa as historical_fixture


@pytest.fixture(scope="module")
def collection():
    fixture = historical_fixture.RoboCasaPublicationTests
    fixture.setUpClass()
    try:
        root = fixture.root
        gallery, report = deepcopy(fixture.base_gallery), deepcopy(fixture.base_report)
        run, manifest = EXPECTED_RUNS["robodojo"]
        provenance = dict(run=run, manifestSha256=manifest, auditKind="robodojo_firstpass",
                          auditSha256="a" * 64, policyBoundaryAuditSha256="b" * 64)
        tasks, selections, suites = [], [], []
        payload = b"Synthetic RoboDojo metadata fixture, not a playable recording."
        digest = hashlib.sha256(payload).hexdigest()
        for group, names in ROBODOJO_TASKS.items():
            suite = "robodojo_" + group.replace("-", "_")
            for name in names:
                task_id = "robodojo_" + name.lower()
                key, success = task_id + "_r00", len(tasks) < 6
                status = "success" if success else "failure"
                instruction = "  Synthetic native instruction.\nPreserve whitespace and UTF-8: 杯子.  "
                instruction_hash = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
                episode = dict(id=key, index=0, status=status, seed=0, initStateId=None, steps=1,
                               maxSteps=ROBODOJO_HORIZONS[name], toolCalls=1000, wallSeconds=2.0,
                               durationSeconds=.08, video=f"media/robodojo/{key}.mp4",
                               poster=f"media/robodojo/{key}.jpg", width=1920, height=480, frames=2,
                               nativeScore=1.0 if success else .25, layoutId=0,
                               terminationReason="robodojo_success" if success else "agent_finished")
                for field in ("video", "poster"):
                    path = root / episode[field]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                task = dict(id=task_id, name=name, nativeTaskName=name, taskGroup=group,
                            instruction=instruction, instructionSha256=instruction_hash,
                            suite=suite, suiteName=group, episodes=[episode])
                task.update({k: v for k, v in aggregate([episode], 1).items()
                             if k in {"successes", "failures", "successRate"}})
                tasks.append(task)
                selections.append(dict(episode=key, sourceEpisodeKey=name + "_r00", seed=0,
                                       selectedAttempt="attempt_001", resultSha256="c" * 64,
                                       sourceVideoSha256=digest, instructionSha256=instruction_hash,
                                       nativeStateSha256="d" * 64,
                                       nativeSuccess=success, nativeScore=episode["nativeScore"],
                                       status=status, steps=1, excludedAttempts=[]))
                report["media"].append(dict(episode=key, benchmark="robodojo", sourceSha256=digest,
                    sourceBytes=len(payload), video=episode["video"], videoSha256=digest, videoBytes=len(payload),
                    poster=episode["poster"], posterSha256=digest, posterBytes=len(payload), posterFrame=1,
                    codec="h264", pixelFormat="yuv420p", width=1920, height=480, fps="25", frames=2,
                    durationSeconds=.08, fastStart=True, verified=True))
            suites.append(dict(id=suite, name=group,
                               **aggregate([t["episodes"][0] for t in tasks if t["suite"] == suite], len(names))))
        gallery["benchmarks"].append(dict(id="robodojo", name="RoboDojo42", evaluationDate="2026-09-19",
            provenance=provenance, protocol={"episodesPerTask": 1}, suites=suites, tasks=tasks,
            summary=aggregate([t["episodes"][0] for t in tasks], 42)))
        gallery.update(evaluationDate="2026-09-19", evaluationDates=["2026-09-17", "2026-09-18", "2026-09-19"])
        report["runs"].append(dict(**deepcopy(provenance), benchmark="robodojo", selectedEpisodes=42,
                                  excludedAttemptCount=0, attemptSelection=selections))
        report.update(expectedEpisodes=857, verifiedEpisodes=857,
                      videoBytes=sum(m["videoBytes"] for m in report["media"]),
                      posterBytes=sum(m["posterBytes"] for m in report["media"]),
                      sourceBytes=sum(m["sourceBytes"] for m in report["media"]))
        report["publishedMediaBytes"] = report["videoBytes"] + report["posterBytes"]
        report["pagesMediaBytes"] = report["publishedMediaBytes"] - report["externalVideoBytes"]
        report["validation"]["decodedFrameCount"] = sum(m["frames"] for m in report["media"])
        catalog = {"schemaVersion": 1, "coverage": {}, "tasks": {}}
        for benchmark in gallery["benchmarks"][:-1]:
            catalog["coverage"][benchmark["id"]] = dict(tasks=len(benchmark["tasks"]), available=0,
                                                        unavailable=len(benchmark["tasks"]))
            for task in benchmark["tasks"]:
                catalog["tasks"][task["id"]] = dict(taskId=task["id"], benchmark=benchmark["id"],
                    status="unavailable", reason="Synthetic test fixture only.",
                    source={"dataset": "Synthetic", "url": "https://example.invalid/fixture"})
        yield root, gallery, report, catalog
    finally:
        fixture.tearDownClass()


@pytest.fixture
def data(collection):
    root, gallery, report, catalog = collection
    gallery, report, catalog = deepcopy(gallery), deepcopy(report), deepcopy(catalog)
    benchmark, run = gallery["benchmarks"][-1], report["runs"][-1]

    def validate(**kwargs):
        publish_metadata(root, gallery)
        (root / "data/export-report.json").write_text(json.dumps(report))
        (root / "data/task-demos.json").write_text(json.dumps(catalog))
        return validate_gallery(root, check_interface=False, require_robocasa=True,
                                require_robodojo=True, require_demos=True, **kwargs)

    return dict(root=root, gallery=gallery, report=report, catalog=catalog, benchmark=benchmark, run=run,
                task=benchmark["tasks"][0], episode=benchmark["tasks"][0]["episodes"][0],
                selection=run["attemptSelection"][0], media=report["media"][-42], validate=validate)


def test_complete_857_preserves_historical_815_and_demo_coverage(data, collection):
    result, videos = data["validate"]()
    assert (result["episodes"], result["tasks"], len(videos)) == (857, 497, 857)
    assert result["benchmarks"]["robodojo"] == dict(tasks=42, episodes=42, successes=6, failures=36,
                                                  timeouts=0, successRate=6 / 42)
    assert data["gallery"]["benchmarks"][:-1] == collection[1]["benchmarks"][:-1]
    assert sum(group["tasks"] for group in result["training_demos"].values()) == 455
    assert "robodojo" not in result["training_demos"]
    assert videos[-1][1] == dict(width=1920, height=480, frames=2, fps=25)


@pytest.mark.parametrize("part,field,value", [
    ("task", "instruction", "Trimmed or augmented instruction"),
    ("task", "instructionSha256", "0" * 64), ("task", "nativeTaskName", "STACK_BOWLS"),
    ("task", "taskGroup", "open"), ("task", "suite", "robodojo_open"),
    ("task", "analysis", "Private policy explanation"), ("task", "reasoning", "Do not publish this"),
    ("episode", "frames", 1), ("episode", "width", 1536), ("episode", "height", 512),
    ("episode", "seed", 1), ("episode", "layoutId", 1), ("episode", "maxSteps", 799),
    ("episode", "toolCalls", 1501), ("episode", "status", "timeout"),
    ("episode", "nativeScore", float("nan")), ("episode", "nativeScore", True),
    ("episode", "terminationReason", "step_budget"),
    ("episode", "remoteVideo", "https://example.invalid/video.mp4"), ("episode", "environment", {"score": 1}),
    ("selection", "sourceEpisodeKey", "Stack_bowls_r00"), ("selection", "selectedAttempt", "attempt_002"),
    ("selection", "instructionSha256", "0" * 64), ("selection", "sourceVideoSha256", "0" * 64),
    ("selection", "nativeSuccess", False), ("selection", "nativeScore", 0),
    ("selection", "steps", 2), ("selection", "seed", 1),
    ("selection", "sourcePath", "/playpen/private/result.json"), ("selection", "resultSha256", "bad"),
    ("selection", "nativeStateSha256", "bad"),
    ("selection", "excludedAttempts", [{"attempt": "attempt_001", "status": "failure"}]),
    ("run", "auditSha256", "0" * 64), ("run", "policyBoundaryAuditSha256", "0" * 64),
    ("run", "auditKind", "other"), ("run", "manifestSha256", "0" * 64),
    ("media", "fps", "20"), ("media", "videoSha256", "0" * 64),
    ("media", "sourceSha256", "0" * 64), ("media", "videoBytes", 1),
    ("media", "notes", "Hidden chain of thought"),
])
def test_rejects_boundary_native_identity_and_media_corruption(data, part, field, value):
    data[part][field] = value
    with pytest.raises(ValidationError):
        data["validate"]()


def test_empty_native_instruction_is_preserved_without_augmentation(data):
    data["task"]["instruction"] = ""
    digest = hashlib.sha256(b"").hexdigest()
    data["task"]["instructionSha256"] = data["selection"]["instructionSha256"] = digest
    data["validate"]()


def test_partial_native_score_does_not_become_success(data):
    assert data["benchmark"]["tasks"][6]["episodes"][0]["nativeScore"] == .25
    result, _ = data["validate"]()
    assert result["benchmarks"]["robodojo"]["successes"] == 6


def test_old_training_catalog_cannot_lose_a_task(data):
    del data["catalog"]["tasks"][next(iter(data["catalog"]["tasks"]))]
    with pytest.raises(ValidationError, match="every gallery task"):
        data["validate"]()


def test_partial_robodojo_training_import_cannot_claim_full_coverage(data):
    task_id = data["task"]["id"]
    data["catalog"]["tasks"][task_id] = dict(taskId=task_id, benchmark="robodojo", status="unavailable")
    with pytest.raises(ValidationError, match="every gallery task"):
        data["validate"]()


def test_require_robodojo_rejects_an_old_collection(data):
    data["gallery"]["benchmarks"].pop()
    with pytest.raises(ValidationError, match="RoboDojo42 collection is required"):
        data["validate"]()


@pytest.mark.parametrize("change", [{"nb_read_frames": "1"}, {"avg_frame_rate": "20/1"}, {"width": 1536}])
def test_decode_checks_real_probe_fields(monkeypatch, change):
    stream = dict(codec_name="h264", pix_fmt="yuv420p", width=1920, height=480,
                  nb_read_frames="2", avg_frame_rate="25/1")
    stream.update(change)
    monkeypatch.setattr("validate_gallery.subprocess.run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"streams": [stream]})))
    with pytest.raises(ValidationError):
        probe_video((Path("synthetic.mp4"), dict(width=1920, height=480, frames=2, fps=25)))
