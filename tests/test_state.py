import pathlib
import tempfile
import unittest


from oml_mcp.errors import OMLError
from oml_mcp.state import StateStore


PLAN = {
    "plan_id": "plan-0123456789abcdef",
    "digest": "a" * 64,
    "source_digest": "b" * 64,
    "source_path": "/approved/source",
    "profile_id": "pinned-stack",
    "route": "periodic_gw",
    "stages": ["scf", "pyatb", "nscf", "preprocess", "librpa"],
    "options": {"task": "gw", "system_type": "solid"},
    "source_manifest": [{"path": "STRU", "size": 4, "sha256": "c" * 64}],
}


class StateStoreTest(unittest.TestCase):
    def make_store(self, root: pathlib.Path) -> StateStore:
        return StateStore(root / "state" / "oml.sqlite3")

    def test_plan_is_idempotent_but_immutable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self.make_store(pathlib.Path(tmpdir))
            store.register_plan(PLAN)
            store.register_plan(PLAN)

            changed = {**PLAN, "digest": "d" * 64}
            with self.assertRaisesRegex(OMLError, "PLAN_CONFLICT"):
                store.register_plan(changed)

            stored = store.get_plan(PLAN["plan_id"])

        self.assertEqual(stored["digest"], PLAN["digest"])
        self.assertEqual(stored["stages"], PLAN["stages"])

    def test_submission_authorization_enforces_order_and_duplicate_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = self.make_store(root)
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-001",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "runs" / "run-001"),
                remote_run_dir=None,
                manifest_digest="e" * 64,
            )

            with self.assertRaisesRegex(OMLError, "STATE_TRANSITION_DENIED"):
                store.authorize_submission("run-001", "pyatb", PLAN["digest"])

            first = store.authorize_submission("run-001", "scf", PLAN["digest"])
            with self.assertRaisesRegex(OMLError, "DUPLICATE_JOB"):
                store.authorize_submission("run-001", "scf", PLAN["digest"])

            store.mark_attempt_submitted(first["attempt_id"], "31415")
            with self.assertRaisesRegex(OMLError, "DUPLICATE_JOB"):
                store.authorize_submission("run-001", "scf", PLAN["digest"])

            store.record_attempt_status(first["attempt_id"], "PASSED")
            second = store.authorize_submission("run-001", "pyatb", PLAN["digest"])

        self.assertEqual(first["status"], "SUBMITTING")
        self.assertEqual(second["stage"], "pyatb")

    def test_stale_plan_and_unknown_stage_are_denied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = self.make_store(root)
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-002",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "runs" / "run-002"),
                remote_run_dir=None,
                manifest_digest="e" * 64,
            )

            with self.assertRaisesRegex(OMLError, "STALE_PLAN"):
                store.authorize_submission("run-002", "scf", "f" * 64)
            with self.assertRaisesRegex(OMLError, "STATE_TRANSITION_DENIED"):
                store.authorize_submission("run-002", "cleanup", PLAN["digest"])

    def test_observation_keeps_timestamp_and_normalized_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = self.make_store(root)
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-003",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "runs" / "run-003"),
                remote_run_dir=None,
                manifest_digest="e" * 64,
            )
            attempt = store.authorize_submission("run-003", "scf", PLAN["digest"])
            store.mark_attempt_submitted(attempt["attempt_id"], "27182")
            store.record_observation(
                attempt["attempt_id"],
                normalized_state="RUNNING",
                raw_state="R",
                source="squeue",
            )
            latest = store.latest_observation(attempt["attempt_id"])

        self.assertEqual(latest["normalized_state"], "RUNNING")
        self.assertEqual(latest["raw_state"], "R")
        self.assertTrue(latest["observed_at"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
