"""Exercise RoboCasa publication invariants with explicitly synthetic metadata.

Existing presentation files are linked read-only into an ignored temporary tree;
synthetic RoboCasa bytes are only used by metadata validation, never published.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from export_gallery import aggregate, publish_metadata
from release_media import RELEASE_HOSTING, remote_video_url
from validate_gallery import EXPECTED_RUNS, ValidationError, validate_gallery


class RoboCasaPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache = ROOT / ".gallery-cache"
        cache.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="validator-test-", dir=cache)
        cls.root = Path(cls.temporary.name)
        gallery = json.loads((ROOT / "data/gallery.json").read_text())
        report = json.loads((ROOT / "data/export-report.json").read_text())
        # These regression inputs are the two historical, unchanged exports.
        gallery["benchmarks"] = [b for b in gallery["benchmarks"] if b["id"] != "robocasa"]
        for benchmark in gallery["benchmarks"]:
            benchmark["evaluationDate"] = "2026-09-17"
        report["runs"] = [r for r in report["runs"] if r["benchmark"] != "robocasa"]
        report["media"] = [m for m in report["media"] if m["benchmark"] != "robocasa"]
        for item in report["media"]:
            for key in ("video", "poster"):
                target = cls.root / item[key]
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(ROOT / item[key], target)
        run, manifest = EXPECTED_RUNS["robocasa"]
        provenance = {"run": run, "manifestSha256": manifest, "auditKind": "robocasa_collection",
                      "auditSha256": "a" * 64, "planSha256": "b" * 64,
                      "sources": [{"run": run, "manifestSha256": manifest, "seedBase": 100000}]}
        tasks, selections = [], []
        for index in range(365):
            name = f"SyntheticTask{index:03d}"
            task_id = f"robocasa_{name.lower()}"
            key = task_id + "_r00"
            suite = "robocasa_atomic" if index < 65 else "robocasa_composite"
            status = "timeout" if index == 0 else ("success" if index % 2 else "failure")
            episode = {"id": key, "index": 0, "status": status, "seed": 100000, "initStateId": None,
                       "steps": 1, "maxSteps": 300, "toolCalls": 1000, "wallSeconds": 2.0,
                       "durationSeconds": .1, "video": f"media/robocasa/{key}.mp4",
                       "poster": f"media/robocasa/{key}.jpg", "remoteVideo": remote_video_url(key),
                       "width": 1536, "height": 512, "frames": 2}
            payload = b"synthetic metadata fixture, not a playable recording"
            digest = sha256(payload).hexdigest()
            for field in ("video", "poster"):
                path = cls.root / episode[field]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            task = {"id": task_id, "name": name, "instruction": "Synthetic test instruction.",
                    "suite": suite, "suiteName": suite, "episodes": [episode]}
            task.update({k: v for k, v in aggregate([episode], 1).items()
                         if k in ("successes", "failures", "successRate")})
            tasks.append(task)
            selections.append({"episode": key, "sourceEpisodeKey": name + "_r00", "run": run,
                               "manifestSha256": manifest, "seed": 100000, "selectedAttempt": "attempt_001",
                               "resultSha256": "c" * 64, "sourceVideoSha256": digest,
                               "status": status, "steps": 1, "nativeScore": int(status == "success"),
                               "excludedAttempts": []})
            report["media"].append({"episode": key, "benchmark": "robocasa", "sourceSha256": digest,
                                    "sourceBytes": len(payload), "video": episode["video"],
                                    "videoSha256": digest, "videoBytes": len(payload), "poster": episode["poster"],
                                    "posterSha256": digest, "posterBytes": len(payload), "posterFrame": 1,
                                    "codec": "h264", "pixelFormat": "yuv420p", "width": 1536, "height": 512,
                                    "fps": "20", "frames": 2, "durationSeconds": .1, "fastStart": True, "verified": True})
        suites = [{"id": suite, "name": suite,
                   **aggregate([t["episodes"][0] for t in tasks if t["suite"] == suite], count)}
                  for suite, count in (("robocasa_atomic", 65), ("robocasa_composite", 300))]
        gallery["benchmarks"].append({"id": "robocasa", "name": "RoboCasa365", "provenance": provenance,
                                       "videoHosting": deepcopy(RELEASE_HOSTING), "evaluationDate": "2026-09-18",
                                       "protocol": {"episodesPerTask": 1}, "tasks": tasks, "suites": suites,
                                       "summary": aggregate([t["episodes"][0] for t in tasks], 365)})
        gallery.update(evaluationDate="2026-09-18", evaluationDates=["2026-09-17", "2026-09-18"])
        report["runs"].append({**deepcopy(provenance), "benchmark": "robocasa", "selectedEpisodes": 365,
                               "excludedAttemptCount": 0, "attemptSelection": selections})
        report.update(expectedEpisodes=815, verifiedEpisodes=815, complete=True,
                      videoBytes=sum(m["videoBytes"] for m in report["media"]),
                      posterBytes=sum(m["posterBytes"] for m in report["media"]),
                      sourceBytes=sum(m["sourceBytes"] for m in report["media"]))
        report["publishedMediaBytes"] = report["videoBytes"] + report["posterBytes"]
        report["videoHosting"] = {"robocasa": deepcopy(RELEASE_HOSTING)}
        report["externalVideoBytes"] = sum(m["videoBytes"] for m in report["media"] if m["benchmark"] == "robocasa")
        report["pagesMediaBytes"] = report["publishedMediaBytes"] - report["externalVideoBytes"]
        report["validation"]["decodedFrameCount"] = sum(m["frames"] for m in report["media"])
        cls.base_gallery, cls.base_report = gallery, report

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.gallery, self.report = deepcopy(self.base_gallery), deepcopy(self.base_report)
        self.benchmark = self.gallery["benchmarks"][-1]
        self.run = self.report["runs"][-1]
        self.selection = self.run["attemptSelection"][0]
        self.episode = self.benchmark["tasks"][0]["episodes"][0]

    def validate(self, release_assets=None):
        publish_metadata(self.root, self.gallery)
        (self.root / "data/export-report.json").write_text(json.dumps(self.report))
        return validate_gallery(self.root, check_interface=False, require_robocasa=True, release_assets=release_assets)

    def test_complete_815_includes_policy_timeout_and_1500_tool_budget(self):
        result, videos = self.validate()
        self.assertEqual((result["episodes"], result["tasks"], len(videos)), (815, 455, 815))
        self.assertEqual(result["benchmarks"]["robocasa"]["timeouts"], 1)

    def test_native_score_cannot_turn_a_timeout_into_success(self):
        self.selection["nativeScore"] = 1
        with self.assertRaisesRegex(ValidationError, "native score mismatch"):
            self.validate()

    def test_selected_video_must_match_audit_fingerprint(self):
        self.selection["sourceVideoSha256"] = "d" * 64
        with self.assertRaisesRegex(ValidationError, "audit/source video mismatch"):
            self.validate()

    def test_all_native_action_frames_required(self):
        self.episode["frames"] = 1
        with self.assertRaisesRegex(ValidationError, "action/frame mismatch"):
            self.validate()

    def test_atomic_and_composite_matrix_is_fixed(self):
        self.benchmark["tasks"][0]["suite"] = "robocasa_composite"
        with self.assertRaisesRegex(ValidationError, "task group"):
            self.validate()

    def test_cross_run_initial_scene_exclusions_are_retained(self):
        primary = self.run["sources"][0]
        replacement = {"run": "robocasa365_initialization_recovery_SyntheticTask000_seed100001_20260918",
                       "manifestSha256": "e" * 64, "seedBase": 100001}
        self.run["sources"].append(replacement)
        self.benchmark["provenance"]["sources"].append(deepcopy(replacement))
        self.selection.update(run=replacement["run"], manifestSha256=replacement["manifestSha256"], seed=100001)
        self.episode["seed"] = 100001
        self.selection["excludedAttempts"] = [
            {"run": primary["run"], "manifestSha256": primary["manifestSha256"],
             "sourceEpisodeKey": self.selection["sourceEpisodeKey"], "seed": 100000, "attempt": f"attempt_{number:03d}",
             "status": "error", "reason": "simulation_error", "steps": 0, "visualObservations": 0,
             "nativeSuccess": True, "countsAsValidEpisode": False, "countedAsValidSuccess": False,
             "resultSha256": "f" * 64, "videoSha256": "9" * 64}
            for number in (1, 2)]
        self.run["excludedAttemptCount"] = 2
        self.validate()

    def test_api_failure_cannot_justify_a_new_seed(self):
        self.test_cross_run_initial_scene_exclusions_are_retained()
        self.selection["excludedAttempts"][0].update(reason="codex_error", steps=1, visualObservations=1,
                                                     nativeSuccess=False)
        with self.assertRaisesRegex(ValidationError, "API failure cannot advance"):
            self.validate()

    def test_machine_local_paths_cannot_leak_into_public_data(self):
        self.selection["sourcePath"] = "/playpen/private/result.json"
        with self.assertRaisesRegex(ValidationError, "Machine-local path"):
            self.validate()

    def release_assets(self):
        return {f"{record['episode']}.mp4": {"state": "uploaded", "size": record["videoBytes"],
                "digest": f"sha256:{record['videoSha256']}", "browser_download_url": remote_video_url(record["episode"])}
                for record in self.report["media"] if record["benchmark"] == "robocasa"}

    def test_ci_validates_release_when_local_mp4_is_absent(self):
        path = self.root / self.episode["video"]
        original = path.read_bytes()
        try:
            path.unlink()
            result, videos = self.validate(self.release_assets())
            self.assertEqual(result["episodes"], 815)
            self.assertEqual(videos[-365][0], self.episode["remoteVideo"])
            with self.assertRaisesRegex(ValidationError, "Missing video"):
                self.validate()
        finally:
            path.write_bytes(original)

    def test_remote_digest_cannot_differ_from_locally_verified_export(self):
        assets = self.release_assets()
        assets[f"{self.episode['id']}.mp4"]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValidationError, "Release asset fingerprint mismatch"):
            self.validate(assets)

    def test_remote_video_cannot_point_to_another_repository(self):
        self.episode["remoteVideo"] = self.episode["remoteVideo"].replace("tianqi-zh", "different-owner")
        with self.assertRaisesRegex(ValidationError, "Incorrect release video URL"):
            self.validate()

    def test_historical_evaluation_dates_remain_separate(self):
        self.gallery["benchmarks"][0]["evaluationDate"] = "2026-09-18"
        with self.assertRaisesRegex(ValidationError, "Incorrect evaluation date"):
            self.validate()

    def test_historical_video_cannot_be_redirected_without_validation(self):
        self.gallery["benchmarks"][0]["tasks"][0]["episodes"][0]["remoteVideo"] = "https://example.com/unverified.mp4"
        with self.assertRaisesRegex(ValidationError, "Unexpected remote video"):
            self.validate()

    def test_release_mode_still_checks_existing_local_files(self):
        path = self.root / self.episode["video"]
        original = path.read_bytes()
        try:
            path.write_bytes(b"changed local video")
            with self.assertRaisesRegex(ValidationError, "Local release video fingerprint mismatch"):
                self.validate(self.release_assets())
        finally:
            path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
