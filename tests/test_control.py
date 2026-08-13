import json
import pathlib
import subprocess
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch


from oml_mcp.control import ControlledExecutionService
from oml_mcp.errors import OMLError
from oml_mcp.models import ValidationReport
from oml_mcp.planner import plan_case
from tests.test_materializer import make_periodic_source, make_profile
from tests.test_stage_inspection import command_completed


def synthetic_scientific_result() -> dict:
    return {
        "definition": {"schema_version": 1, "digest": "d" * 64, "profile_id": "test-local"},
        "window": {
            "vbm_band": 1,
            "cbm_band": 2,
            "band_start": 1,
            "band_stop": 2,
            "state_count": 2,
            "states": [],
            "fundamental_gw_gap_ev": 2.0,
        },
        "diagnostics": {"accepted": True, "failure_count": 0, "failures": []},
    }


class ControlledExecutionTest(unittest.TestCase):
    def prepare(self, root: pathlib.Path):
        source_root = root / "sources"
        source = source_root / "si"
        make_periodic_source(source)
        profile = make_profile(root, source_root)
        plan = plan_case(source, task="gw", system_type="solid")
        service = ControlledExecutionService(profile)
        service.executor.verify_versions = lambda: {"verdict": "match", "components": {}}
        run = service.prepare_run(source, plan.digest)
        return source, profile, plan, service, run

    def test_submit_rechecks_manifest_and_records_scheduler_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)

            with patch("oml_mcp.executor.subprocess.run") as execute:
                execute.return_value = subprocess.CompletedProcess([], 0, "12345\n", "")
                attempt = service.submit_stage(run["run_id"], "scf", plan.digest)

            status = service.get_status(run["run_id"], attempt["attempt_id"])

        self.assertEqual(attempt["scheduler_id"], "12345")
        self.assertEqual(attempt["status"], "SUBMITTED")
        self.assertEqual(status["attempt"]["scheduler_id"], "12345")

    def make_passed_run(self, root: pathlib.Path):
        _, _, plan, service, run = self.prepare(root)
        final_attempt = None
        for stage in plan.stages:
            attempt = service.store.authorize_submission(run["run_id"], stage, plan.digest)
            service.store.mark_attempt_submitted(attempt["attempt_id"], str(500 + len(stage)))
            if stage == "librpa":
                service.store.finalize_inspection(
                    attempt["attempt_id"],
                    {"schema_version": 1, "stage": stage, "accepted": True, "gates": []},
                )
            else:
                service.store.record_attempt_status(attempt["attempt_id"], "PASSED")
            final_attempt = attempt
        assert final_attempt is not None
        run_dir = pathlib.Path(run["local_run_dir"])
        snapshot = run_dir / ".oml" / "snapshots" / final_attempt["attempt_id"]
        snapshot.mkdir(parents=True)
        return plan, service, run, final_attempt, snapshot

    def test_finalize_case_persists_not_evaluated_report_and_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            plan, service, run, final_attempt, _ = self.make_passed_run(root)
            with patch.object(
                service, "_load_scientific_result", return_value=synthetic_scientific_result()
            ):
                finalized = service.finalize_case(
                    run["run_id"], plan.digest, "bn-reader-v1-3d-v1"
                )
                same = service.finalize_case(
                    run["run_id"], plan.digest, "bn-reader-v1-3d-v1"
                )
                score = service.score_case(run["run_id"], plan.digest)

            report_path = (
                pathlib.Path(run["local_run_dir"])
                / ".oml"
                / "science"
                / f"{finalized['report_id']}.json"
            )
            report_file_exists = report_path.is_file()

        self.assertEqual(finalized, same)
        self.assertEqual(finalized["scientific_status"], "NOT_EVALUATED")
        self.assertEqual(finalized["regression"]["reason_code"], "REFERENCE_NOT_AVAILABLE")
        self.assertEqual(finalized["final_attempt_id"], final_attempt["attempt_id"])
        self.assertEqual(finalized["evaluator_version"], 4)
        self.assertTrue(report_file_exists)
        dimensions = {item["dimension_id"]: item for item in score["dimensions"]}
        self.assertEqual(dimensions["numerical_scientific_validity"]["status"], "NOT_EVALUATED")

    def test_finalize_case_requires_every_stage_and_untampered_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            with self.assertRaisesRegex(OMLError, "SCIENTIFIC_LINEAGE_INCOMPLETE"):
                service.finalize_case(run["run_id"], plan.digest, "bn-reader-v1-3d-v1")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            plan, service, run, _, _ = self.make_passed_run(root)
            pathlib.Path(run["local_run_dir"], "STRU").write_text("tampered\n")
            with self.assertRaisesRegex(OMLError, "MANIFEST_MISMATCH"):
                service.finalize_case(run["run_id"], plan.digest, "bn-reader-v1-3d-v1")

    def test_tampered_input_or_stage_script_blocks_submission(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            run_dir = pathlib.Path(run["local_run_dir"])
            (run_dir / "STRU").write_text("tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(OMLError, "MANIFEST_MISMATCH"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            run_dir = pathlib.Path(run["local_run_dir"])
            (run_dir / "sitecustomize.py").write_text(
                "raise RuntimeError('injected')\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(OMLError, "MANIFEST_MISMATCH"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            script = pathlib.Path(run["local_run_dir"]) / ".oml" / "stages" / "scf.slurm"
            script.write_text(script.read_text(encoding="utf-8") + "echo tampered\n", encoding="utf-8")

            with self.assertRaisesRegex(OMLError, "MANIFEST_MISMATCH"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

    def test_source_change_after_preparation_blocks_submission(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source, _, plan, service, run = self.prepare(root)
            (source / "KPT_scf").write_text("K_POINTS\n0\nGamma\n4 4 4 0 0 0\n", encoding="utf-8")

            with self.assertRaisesRegex(OMLError, "STALE_PLAN"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

    def test_source_becoming_mixed_returns_a_stable_stale_plan_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source, _, plan, service, run = self.prepare(root)
            (source / "control.in").write_text("xc pbe\n", encoding="utf-8")
            (source / "geometry.in").write_text("atom 0 0 0 Si\n", encoding="utf-8")

            with self.assertRaisesRegex(OMLError, "STALE_PLAN") as raised:
                service.submit_stage(run["run_id"], "scf", plan.digest)

        self.assertEqual(raised.exception.code, "STALE_PLAN")

    def test_submit_timeout_remains_locked_until_reconciled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)

            with patch(
                "oml_mcp.executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired([], 20),
            ) as submit:
                with self.assertRaisesRegex(OMLError, "SUBMISSION_AMBIGUOUS"):
                    service.submit_stage(run["run_id"], "scf", plan.digest)
                self.assertEqual(submit.call_count, 1)
            service.executor.reconcile_submission = lambda *_: (_ for _ in ()).throw(
                OMLError(
                    "SCHEDULER_UNOBSERVABLE",
                    "cannot query scheduler",
                    evidence=(),
                    recovery="restore observation",
                )
            )
            with self.assertRaisesRegex(OMLError, "SCHEDULER_UNOBSERVABLE"):
                service.submit_stage(run["run_id"], "scf", plan.digest)
            self.assertEqual(
                service.store.active_attempt(run["run_id"], "scf")["status"],
                "UNKNOWN",
            )

    def test_absent_ambiguous_submission_requires_a_fresh_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            service.executor.submit = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                OMLError(
                    "SUBMISSION_AMBIGUOUS",
                    "timeout",
                    evidence=(),
                    recovery="reconcile",
                )
            )
            with self.assertRaisesRegex(OMLError, "SUBMISSION_AMBIGUOUS"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

            service.executor.reconcile_submission = lambda *_: {
                "verdict": "absent",
                "normalized_state": "UNKNOWN",
                "raw_state": "NOT_FOUND",
                "source": "squeue+sacct",
                "observed_at": "2026-08-13T00:00:00Z",
            }
            service.executor.submit = lambda *_args, **_kwargs: "98765"
            with self.assertRaisesRegex(OMLError, "SUBMISSION_UNRESOLVED"):
                service.submit_stage(run["run_id"], "scf", plan.digest)
            with service.store._connection() as connection:
                connection.execute(
                    "UPDATE observations SET observed_at = '2000-01-01T00:00:00Z'"
                )
                connection.commit()
            with self.assertRaisesRegex(OMLError, "RETRY_REQUIRES_FRESH_RUN"):
                service.submit_stage(run["run_id"], "scf", plan.digest)
            attempts = service.store.list_attempts(run["run_id"])

        self.assertEqual([item["status"] for item in attempts], ["FAILED"])

    def test_reconciled_existing_job_is_recorded_and_duplicate_stays_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            ambiguous = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.record_attempt_status(ambiguous["attempt_id"], "UNKNOWN")
            service.executor.reconcile_submission = lambda *_: {
                "verdict": "found",
                "scheduler_id": "31415",
                "normalized_state": "RUNNING",
                "raw_state": "RUNNING",
                "source": "squeue",
                "observed_at": "2026-08-13T00:00:00Z",
            }

            with self.assertRaisesRegex(OMLError, "DUPLICATE_JOB"):
                service.submit_stage(run["run_id"], "scf", plan.digest)
            reconciled = service.store.get_attempt(ambiguous["attempt_id"])

        self.assertEqual(reconciled["scheduler_id"], "31415")
        self.assertEqual(reconciled["status"], "RUNNING")

    def test_interrupted_submitting_attempt_enters_the_bounded_reconciliation_loop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            interrupted = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.executor.reconcile_submission = lambda *_: {
                "verdict": "absent",
                "normalized_state": "UNKNOWN",
                "raw_state": "NOT_FOUND",
                "source": "squeue+sacct",
                "observed_at": "2026-08-13T00:00:00Z",
            }
            service.executor.submit = lambda *_args, **_kwargs: "27182"

            with self.assertRaisesRegex(OMLError, "SUBMISSION_UNRESOLVED") as raised:
                service.submit_stage(run["run_id"], "scf", plan.digest)
            first = service.store.get_attempt(interrupted["attempt_id"])

        self.assertEqual(raised.exception.code, "SUBMISSION_UNRESOLVED")
        self.assertEqual(first["status"], "UNKNOWN")

    def test_two_immediate_absence_queries_do_not_unlock_a_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            attempt = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.record_attempt_status(attempt["attempt_id"], "UNKNOWN")
            service.executor.reconcile_submission = lambda *_: {
                "verdict": "absent",
                "normalized_state": "UNKNOWN",
                "raw_state": "NOT_FOUND",
                "source": "squeue+sacct",
                "observed_at": "2026-08-13T00:00:00Z",
            }

            with self.assertRaisesRegex(OMLError, "SUBMISSION_UNRESOLVED"):
                service.submit_stage(run["run_id"], "scf", plan.digest)
            with self.assertRaisesRegex(OMLError, "SUBMISSION_UNRESOLVED"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

            persisted = service.store.get_attempt(attempt["attempt_id"])

        self.assertEqual(persisted["status"], "UNKNOWN")

    def test_terminal_stage_attempt_requires_a_fresh_run_before_retry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            failed = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.record_attempt_status(failed["attempt_id"], "FAILED")

            with self.assertRaisesRegex(OMLError, "RETRY_REQUIRES_FRESH_RUN"):
                service.submit_stage(run["run_id"], "scf", plan.digest)
            attempts = service.store.list_attempts(run["run_id"])

        self.assertEqual(len(attempts), 1)

    def test_concurrent_submit_call_cannot_reconcile_or_replace_live_submission(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.executor.reconcile_submission = lambda *_: (_ for _ in ()).throw(
                AssertionError("live submission must not be reconciled")
            )

            with service.store.submission_lock(run["run_id"], "scf"):
                with self.assertRaisesRegex(OMLError, "DUPLICATE_JOB"):
                    service.submit_stage(run["run_id"], "scf", plan.digest)

    def test_submitted_attempt_stays_duplicate_instead_of_suggesting_a_fresh_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            attempt = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.mark_attempt_submitted(attempt["attempt_id"], "12345")

            with self.assertRaisesRegex(OMLError, "DUPLICATE_JOB") as raised:
                service.submit_stage(run["run_id"], "scf", plan.digest)

        self.assertEqual(raised.exception.code, "DUPLICATE_JOB")

    def test_equivalent_stage_cannot_run_concurrently_in_two_fresh_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source, _, plan, service, first_run = self.prepare(root)
            first = service.store.authorize_submission(
                first_run["run_id"], "scf", plan.digest
            )
            service.store.mark_attempt_submitted(first["attempt_id"], "12345")
            second_run = service.prepare_run(source, plan.digest)
            service.executor.submit = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("duplicate must be rejected before sbatch")
            )

            with self.assertRaisesRegex(OMLError, "DUPLICATE_JOB"):
                service.submit_stage(second_run["run_id"], "scf", plan.digest)

    def test_completed_scheduler_job_does_not_pass_stage_without_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            with patch("oml_mcp.executor.subprocess.run") as execute:
                execute.return_value = subprocess.CompletedProcess([], 0, "12345\n", "")
                attempt = service.submit_stage(run["run_id"], "scf", plan.digest)
            with patch("oml_mcp.executor.subprocess.run") as observe:
                observe.return_value = subprocess.CompletedProcess([], 0, "COMPLETED\n", "")
                status = service.get_status(run["run_id"], attempt["attempt_id"])

        self.assertEqual(status["scheduler"]["normalized_state"], "COMPLETED")
        self.assertNotEqual(status["attempt"]["status"], "PASSED")

    def test_get_status_is_read_only_for_persisted_attempt_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            with patch("oml_mcp.executor.subprocess.run") as execute:
                execute.return_value = subprocess.CompletedProcess([], 0, "12345\n", "")
                attempt = service.submit_stage(run["run_id"], "scf", plan.digest)
            with patch("oml_mcp.executor.subprocess.run") as observe:
                observe.return_value = subprocess.CompletedProcess([], 0, "RUNNING\n", "")
                status = service.get_status(run["run_id"], attempt["attempt_id"])

            persisted = service.store.get_attempt(attempt["attempt_id"])
            observation = service.store.latest_observation(attempt["attempt_id"])

        self.assertEqual(status["scheduler"]["normalized_state"], "RUNNING")
        self.assertEqual(persisted["status"], "SUBMITTED")
        self.assertIsNone(observation)

    def test_status_observation_cannot_regress_a_terminal_attempt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            with patch("oml_mcp.executor.subprocess.run") as execute:
                execute.return_value = subprocess.CompletedProcess([], 0, "12345\n", "")
                attempt = service.submit_stage(run["run_id"], "scf", plan.digest)
            service.store.record_attempt_status(attempt["attempt_id"], "PASSED")

            with patch("oml_mcp.executor.subprocess.run") as observe:
                observe.return_value = subprocess.CompletedProcess([], 0, "RUNNING\n", "")
                status = service.get_status(run["run_id"], attempt["attempt_id"])

        self.assertEqual(status["attempt"]["status"], "PASSED")
        self.assertEqual(status["scheduler"]["normalized_state"], "RUNNING")

    def test_status_rejects_run_owned_by_another_profile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, profile, plan, service, run = self.prepare(root)
            attempt = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.mark_attempt_submitted(attempt["attempt_id"], "12345")
            changed = replace(profile, profile_id="other-profile")
            other = ControlledExecutionService(changed)

            with self.assertRaisesRegex(OMLError, "PROFILE_MISMATCH"):
                other.get_status(run["run_id"], attempt["attempt_id"])

    def test_read_only_service_does_not_create_a_missing_state_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")

            with self.assertRaisesRegex(OMLError, "STATE_NOT_FOUND"):
                ControlledExecutionService(profile, initialize_state=False)

            self.assertFalse(profile.state_db.exists())

    def test_inspect_stage_requires_scheduler_completion_then_finalizes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            with patch("oml_mcp.executor.subprocess.run") as execute:
                execute.return_value = subprocess.CompletedProcess([], 0, "12345\n", "")
                attempt = service.submit_stage(run["run_id"], "scf", plan.digest)

            with self.assertRaisesRegex(OMLError, "STATE_TRANSITION_DENIED"):
                service.inspect_stage(run["run_id"], attempt["attempt_id"], plan.digest)

            run_dir = pathlib.Path(run["local_run_dir"])
            command_completed(run_dir, "scf", attempt["attempt_id"])
            output = run_dir / "OUT.ABACUS"
            output.mkdir()
            (output / "running_scf.log").write_text(
                "#SCF IS CONVERGED#\nFinish Time\nTotal  Time\n"
            )
            (output / "ABACUS-CHARGE-DENSITY.restart").write_text("charge\n")
            (run_dir / "vxc_out").write_text("vxc\n")
            (run_dir / "stru_out").write_text("structure\n")
            with patch("oml_mcp.executor.subprocess.run") as observe:
                observe.return_value = subprocess.CompletedProcess([], 0, "COMPLETED\n", "")
                inspection = service.inspect_stage(
                    run["run_id"], attempt["attempt_id"], plan.digest
                )

        self.assertTrue(inspection["accepted"])
        self.assertEqual(inspection["attempt_status"], "PASSED")

    def test_inspection_rejects_completion_receipt_from_an_older_attempt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            attempt = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.mark_attempt_submitted(attempt["attempt_id"], "12345")
            run_dir = pathlib.Path(run["local_run_dir"])
            command_completed(run_dir, "scf", "attempt-from-old-retry")
            output = run_dir / "OUT.ABACUS"
            output.mkdir()
            (output / "running_scf.log").write_text(
                "#SCF IS CONVERGED#\nFinish Time\nTotal  Time\n"
            )
            (output / "ABACUS-CHARGE-DENSITY.restart").write_text("charge\n")
            (run_dir / "vxc_out").write_text("vxc\n")
            (run_dir / "stru_out").write_text("structure\n")
            service.executor.status = lambda *_: {
                "normalized_state": "COMPLETED",
                "raw_state": "COMPLETED",
                "source": "sacct",
            }

            inspection = service.inspect_stage(
                run["run_id"], attempt["attempt_id"], plan.digest
            )

        self.assertFalse(inspection["accepted"])
        self.assertEqual(inspection["attempt_status"], "FAILED")

    def test_remote_inspection_rechecks_the_immutable_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            base = make_profile(root, source_root)
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            plan = plan_case(source, task="gw", system_type="solid")
            service = ControlledExecutionService(profile)
            service.executor.verify_versions = lambda: {"verdict": "match", "components": {}}
            service.executor.sync_run = lambda *_: None
            run = service.prepare_run(source, plan.digest)
            attempt = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.mark_attempt_submitted(attempt["attempt_id"], "12345")
            service.executor.status = lambda *_: {
                "normalized_state": "COMPLETED",
                "raw_state": "COMPLETED",
                "source": "sacct",
                "observed_at": "2026-08-13T00:00:00Z",
            }
            service.executor.verify_remote_bundle = lambda *_: (_ for _ in ()).throw(
                OMLError(
                    "REMOTE_MANIFEST_MISMATCH",
                    "remote changed",
                    evidence=(),
                    recovery="prepare fresh run",
                )
            )

            with self.assertRaisesRegex(OMLError, "REMOTE_MANIFEST_MISMATCH"):
                service.inspect_stage(run["run_id"], attempt["attempt_id"], plan.digest)

    def test_remote_inspection_links_only_the_previous_passed_stage_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            base = make_profile(root, source_root)
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            plan = plan_case(source, task="gw", system_type="solid")
            service = ControlledExecutionService(profile)
            service.executor.verify_versions = lambda: {"verdict": "match", "components": {}}
            service.executor.sync_run = lambda *_: None
            service.executor.verify_remote_bundle = lambda *_: {"verdict": "match"}
            run = service.prepare_run(source, plan.digest)
            scf = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.mark_attempt_submitted(scf["attempt_id"], "300")
            service.store.record_attempt_status(scf["attempt_id"], "PASSED")
            snapshots = pathlib.Path(run["local_run_dir"]) / ".oml" / "snapshots"
            previous = snapshots / scf["attempt_id"]
            previous.mkdir(parents=True)
            pyatb = service.store.authorize_submission(run["run_id"], "pyatb", plan.digest)
            service.store.mark_attempt_submitted(pyatb["attempt_id"], "301")
            service.executor.status = lambda *_: {
                "normalized_state": "COMPLETED",
                "raw_state": "COMPLETED",
                "source": "sacct",
                "observed_at": "2026-08-13T00:00:00Z",
            }
            base_report = {
                "schema_version": 1,
                "stage": "pyatb",
                "accepted": True,
                "counts": {"PASS": 1, "WARN": 0, "FAIL": 0, "SKIP": 0},
                "gates": [],
            }

            with patch.object(service.executor, "snapshot_run") as snapshot, patch(
                "oml_mcp.control.inspect_stage_outputs", return_value=base_report
            ), patch(
                "oml_mcp.control.validate_case", return_value=ValidationReport("test", ())
            ):
                service.inspect_stage(run["run_id"], pyatb["attempt_id"], plan.digest)

            target = snapshots / pyatb["attempt_id"]

        snapshot.assert_called_once_with(
            run["remote_run_dir"], target, link_dest=previous
        )

    def test_librpa_submission_requires_full_pre_librpa_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            for stage in ("scf", "pyatb", "nscf", "preprocess"):
                attempt = service.store.authorize_submission(run["run_id"], stage, plan.digest)
                service.store.mark_attempt_submitted(attempt["attempt_id"], str(100 + len(stage)))
                service.store.record_attempt_status(attempt["attempt_id"], "PASSED")

            with self.assertRaisesRegex(OMLError, "GATE_FAILED"):
                service.submit_stage(run["run_id"], "librpa", plan.digest)

    def test_changed_execution_profile_blocks_reuse_of_prepared_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, profile, plan, service, run = self.prepare(root)
            changed = replace(profile, resources={**profile.resources, "memory_mb": 32000})
            changed_service = ControlledExecutionService(changed)
            changed_service.executor.verify_versions = lambda: {
                "verdict": "match",
                "components": {},
            }

            with self.assertRaisesRegex(OMLError, "PROFILE_MISMATCH"):
                changed_service.submit_stage(run["run_id"], "scf", plan.digest)

    def test_changed_executable_fingerprint_blocks_submission(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")
            service = ControlledExecutionService(profile)
            prepared = {
                "verdict": "match",
                "components": {},
                "executables": {
                    "abacus": {"sha256": "a" * 64, "size": 100},
                    "librpa": {"sha256": "b" * 64, "size": 200},
                },
            }
            changed = {
                **prepared,
                "executables": {
                    **prepared["executables"],
                    "abacus": {"sha256": "c" * 64, "size": 100},
                },
            }
            service.executor.verify_versions = lambda: prepared
            run = service.prepare_run(source, plan.digest)
            service.executor.verify_versions = lambda: changed

            with self.assertRaisesRegex(OMLError, "BINARY_MISMATCH"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

    def test_remote_librpa_preflight_uses_passed_preprocess_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            base = make_profile(root, source_root)
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            plan = plan_case(source, task="gw", system_type="solid")
            service = ControlledExecutionService(profile)
            service.executor.verify_versions = lambda: {"verdict": "match", "components": {}}
            service.executor.sync_run = lambda *_: None
            service.executor.verify_remote_bundle = lambda *_: {"verdict": "match"}
            service.executor.submit = lambda *_args, **_kwargs: "67890"
            run = service.prepare_run(source, plan.digest)
            preprocess_attempt = None
            for stage in ("scf", "pyatb", "nscf", "preprocess"):
                attempt = service.store.authorize_submission(run["run_id"], stage, plan.digest)
                service.store.mark_attempt_submitted(attempt["attempt_id"], str(200 + len(stage)))
                service.store.record_attempt_status(attempt["attempt_id"], "PASSED")
                if stage == "preprocess":
                    preprocess_attempt = attempt
            assert preprocess_attempt is not None
            snapshot = (
                pathlib.Path(run["local_run_dir"])
                / ".oml"
                / "snapshots"
                / preprocess_attempt["attempt_id"]
            )
            snapshot.mkdir(parents=True)

            with patch("oml_mcp.control.validate_case") as validate:
                validate.return_value = ValidationReport("test", ())
                service.submit_stage(run["run_id"], "librpa", plan.digest)

        self.assertEqual(pathlib.Path(validate.call_args.args[0]), snapshot)

    def test_pyatb_inspection_includes_full_cross_dataset_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)
            scf = service.store.authorize_submission(run["run_id"], "scf", plan.digest)
            service.store.mark_attempt_submitted(scf["attempt_id"], "300")
            service.store.record_attempt_status(scf["attempt_id"], "PASSED")
            pyatb = service.store.authorize_submission(run["run_id"], "pyatb", plan.digest)
            service.store.mark_attempt_submitted(pyatb["attempt_id"], "301")
            service.store.record_observation(
                pyatb["attempt_id"],
                normalized_state="COMPLETED",
                raw_state="COMPLETED",
                source="sacct",
            )
            base_report = {
                "schema_version": 1,
                "stage": "pyatb",
                "accepted": True,
                "counts": {"PASS": 1, "WARN": 0, "FAIL": 0, "SKIP": 0},
                "gates": [],
            }
            cross_report = ValidationReport(
                "test",
                (
                    __import__("oml_mcp.models", fromlist=["GateResult"]).GateResult(
                        "pyatb.alignment",
                        "FAIL",
                        "PyATB grid does not match ABACUS",
                        ("mismatch",),
                        "regenerate PyATB on the full ABACUS grid",
                    ),
                ),
            )

            with patch("oml_mcp.control.inspect_stage_outputs", return_value=base_report), patch(
                "oml_mcp.control.validate_case", return_value=cross_report
            ), patch.object(
                service.executor,
                "status",
                return_value={
                    "normalized_state": "COMPLETED",
                    "raw_state": "COMPLETED",
                    "source": "sacct",
                },
            ):
                inspection = service.inspect_stage(
                    run["run_id"], pyatb["attempt_id"], plan.digest
                )

        self.assertFalse(inspection["accepted"])
        self.assertEqual(inspection["attempt_status"], "FAILED")
        self.assertTrue(any(gate["gate_id"] == "pyatb.alignment" for gate in inspection["gates"]))


if __name__ == "__main__":
    unittest.main()
