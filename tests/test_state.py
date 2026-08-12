import pathlib
import sqlite3
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

    def test_terminal_attempt_status_cannot_regress(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = self.make_store(root)
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-004",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "runs" / "run-004"),
                remote_run_dir=None,
                manifest_digest="e" * 64,
            )
            attempt = store.authorize_submission("run-004", "scf", PLAN["digest"])
            store.mark_attempt_submitted(attempt["attempt_id"], "16180")
            store.record_attempt_status(attempt["attempt_id"], "PASSED")

            with self.assertRaisesRegex(OMLError, "STATE_TRANSITION_DENIED"):
                store.record_attempt_status(attempt["attempt_id"], "RUNNING")

            final = store.get_attempt(attempt["attempt_id"])

        self.assertEqual(final["status"], "PASSED")

    def test_stage_inspection_is_immutable_and_finalizes_attempt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = self.make_store(root)
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-005",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "runs" / "run-005"),
                remote_run_dir=None,
                manifest_digest="f" * 64,
            )
            preflight = {"version_evidence": {"verdict": "match"}, "remote_bundle": {"verdict": "match"}}
            attempt = store.authorize_submission(
                "run-005", "scf", PLAN["digest"], preflight=preflight
            )
            store.mark_attempt_submitted(attempt["attempt_id"], "16181")
            report = {"stage": "scf", "accepted": True, "gates": []}

            receipt = store.finalize_inspection(attempt["attempt_id"], report)
            same = store.finalize_inspection(attempt["attempt_id"], report)
            with self.assertRaisesRegex(OMLError, "INSPECTION_CONFLICT"):
                store.finalize_inspection(
                    attempt["attempt_id"],
                    {"stage": "scf", "accepted": False, "gates": []},
                )

        self.assertEqual(receipt["report"], report)
        self.assertEqual(same["attempt_status"], "PASSED")
        self.assertEqual(attempt["preflight"], preflight)

    def test_existing_phase_two_database_adds_preflight_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "legacy.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    """
                    CREATE TABLE stage_attempts (
                        attempt_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        attempt_number INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        scheduler_id TEXT,
                        submitted_at TEXT,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
            StateStore(path)
            with sqlite3.connect(path) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(stage_attempts)")
                }

        self.assertIn("preflight_json", columns)


if __name__ == "__main__":
    unittest.main()
