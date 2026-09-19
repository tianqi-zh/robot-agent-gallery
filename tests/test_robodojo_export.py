"""Source-selection boundaries for the additive RoboDojo importer."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import robodojo_export as exporter


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


class RoboDojoExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / exporter.RUN
        self.output = self.base / "gallery"
        code = self.root / "source_snapshot/robot_agent/robodojo/backend.py"
        code.parent.mkdir(parents=True)
        code.write_text("# fixture snapshot\n")
        self.specs = []
        for group, count in exporter.GROUPS.items():
            for index in range(count):
                name = f"{group.replace('-', '_')}_Task_{index}"
                self.specs.append({"task_name": name, "episode_key": f"{name}_r00", "task_group": group,
                                   "variant": "standard", "rollout_id": 0, "seed": 0,
                                   "max_steps": 1000, "native_horizon": 1000, "prompt": "generic procedure"})
        manifest = {"config": {"model": "gpt-6-astra", "reasoning_effort": "high", "workers": 8,
                               "episodes_per_task": 1, "seed_base": 0, "max_tool_calls": 1500},
                    "episodes": self.specs,
                    "provenance": {"code_files": {"robot_agent/robodojo/backend.py": exporter.sha256(code)}}}
        mh = exporter.digest(manifest)
        manifest["manifest_sha256"] = mh
        put(self.root / "manifest.json", manifest)
        self.addCleanup(patch.stopall)
        patch.object(exporter, "MANIFEST_SHA256", mh).start()
        audit_rows, boundary_rows, summary_rows = [], [], []
        self.attempts = []
        for index, spec in enumerate(self.specs):
            directory = self.root / "episodes" / spec["episode_key"] / "attempt_001"
            video = directory / "frames/native/rollout.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"Synthetic source: encoding is tested against real retained recordings.")
            self.attempts.append(directory)
            instruction = f"  Pick up object {index}.\n"
            ih = hashlib.sha256(instruction.encode()).hexdigest()
            success, score = index < 6, 1.0 if index < 6 else 0.15
            status = "success" if success else "failure"
            native = {"steps": 30, "score": score, "success": success, "instruction_sha256": ih}
            put(video.with_name("instruction.json"), {"instruction": instruction, "sha256": ih, "augmented": False})
            put(video.with_name("native_state.json"), native)
            env = {**native, "manifest_sha256": mh, "episode_key": spec["episode_key"], "policy_ready": True,
                   "seed": 0, "layout_id": 0, "native_state_sha256": exporter.sha256(video.with_name("native_state.json")),
                   "video": {"path": str(video), "closed": True, "fps": 25, "width": 1920, "height": 480,
                             "frames": 31, "cameras_left_to_right": exporter.CAMERAS}}
            result = {"manifest_sha256": mh, "episode_key": spec["episode_key"], "status": status,
                      "success": success, "steps": 30, "environment": env, "wall_seconds": 100.5,
                      "reason": "robodojo_success" if success else "agent_finished",
                      "audit": {"stream_complete": True, "instruction_sha256": ih, "mcp_calls": 2},
                      "credentials": "private fixture field must not be exported",
                      "reasoning": "private fixture field must not be exported"}
            put(directory / "env_result.json", env)
            put(directory / "result.json", result)
            (directory / "codex_events.jsonl").write_text('{"fixture": true}\n')
            audit_rows.append({"task_name": spec["task_name"], "passed": True, "status": status,
                               "score": score, "steps": 30, "video": str(video), "decoded_frames": 31,
                               "instruction_sha256": ih})
            boundary_rows.append({"task_name": spec["task_name"], "passed": True,
                                  "result_sha256": exporter.sha256(directory / "result.json"),
                                  "event_log_sha256": exporter.sha256(directory / "codex_events.jsonl"),
                                  "result_status": status, "instruction_sha256": ih})
            summary_rows.append({"task_name": spec["task_name"], "status": status, "native_score": score, "steps": 30})
        put(self.root / "reports/final_audit.json", {
            "passed": True, "scope": "all_42_basic_tasks", "audited_episodes": 42, "videos_decoded": True,
            "maximum_simultaneous_policy_episodes": 8, "issues": [], "manifest_sha256": mh, "episodes": audit_rows})
        put(self.root / "reports/final_policy_boundary_review.json", {
            "passed": True, "full_scope_complete": True, "scope": "all_42_terminal_episodes",
            "terminal_episodes_reviewed": 42, "issues": [], "manifest_sha256": mh, "episodes": boundary_rows})
        put(self.root / "reports/summary.json", {"manifest_sha256": mh, "episodes": summary_rows,
                                                "overall": {"valid": 42, "total_attempts": 42, "retries": 0, "errors": 0}})

    def load(self):
        return exporter.load_audited_robodojo(self.root, self.output)

    def test_complete_selection_preserves_instruction_and_partial_native_score(self):
        benchmark, jobs, provenance, reads = self.load()
        self.assertEqual((len(jobs), benchmark["summary"]["successes"], benchmark["summary"]["failures"]), (42, 6, 36))
        self.assertEqual(benchmark["tasks"][0]["instruction"], "  Pick up object 0.\n")
        self.assertEqual(benchmark["tasks"][6]["episodes"][0]["nativeScore"], 0.15)
        self.assertFalse(provenance["attemptSelection"][6]["nativeSuccess"])
        self.assertIn("robodojo_long_horizon", {s["id"] for s in benchmark["suites"]})
        self.assertTrue(reads)

    def test_public_output_never_copies_private_result_fields_or_paths(self):
        benchmark, _, provenance, _ = self.load()
        text = json.dumps([benchmark, provenance])
        self.assertNotIn("private fixture field", text)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn('"reasoning"', text)
        self.assertNotIn('"credentials"', text)

    def test_partial_audit_is_rejected(self):
        path = self.root / "reports/final_audit.json"
        value = exporter.read_json(path)
        value["audited_episodes"] = 41
        put(path, value)
        with self.assertRaisesRegex(ValueError, "complete successful 42-task"):
            self.load()

    def test_changed_result_after_boundary_audit_is_rejected(self):
        path = self.attempts[0] / "result.json"
        value = exporter.read_json(path)
        value["wall_seconds"] = 10
        put(path, value)
        with self.assertRaisesRegex(ValueError, "Result changed"):
            self.load()

    def test_changed_native_checkpoint_is_rejected_even_with_same_score(self):
        path = self.attempts[0] / "frames/native/native_state.json"
        value = exporter.read_json(path)
        value["extra_native_field"] = "changed"
        put(path, value)
        with self.assertRaisesRegex(ValueError, "Native checkpoint changed"):
            self.load()

    def test_policy_event_drift_is_rejected(self):
        (self.attempts[0] / "codex_events.jsonl").write_text("{}\n")
        with self.assertRaisesRegex(ValueError, "Policy evidence changed"):
            self.load()

    def test_retries_are_rejected(self):
        (self.attempts[0].parent / "attempt_002").mkdir()
        with self.assertRaisesRegex(ValueError, "Exactly one attempt"):
            self.load()

    def test_augmented_instruction_is_rejected(self):
        path = self.attempts[0] / "frames/native/instruction.json"
        value = exporter.read_json(path)
        value["augmented"] = True
        put(path, value)
        with self.assertRaisesRegex(ValueError, "Native instruction parity"):
            self.load()

    def test_frozen_source_drift_is_rejected(self):
        (self.root / "source_snapshot/robot_agent/robodojo/backend.py").write_text("changed\n")
        with self.assertRaisesRegex(ValueError, "Frozen source snapshot"):
            self.load()


if __name__ == "__main__":
    unittest.main()
