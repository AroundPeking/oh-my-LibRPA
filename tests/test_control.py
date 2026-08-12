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

    def test_submit_timeout_remains_locked_until_reconciled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _, _, plan, service, run = self.prepare(root)

            with patch(
                "oml_mcp.executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired([], 20),
            ):
                with self.assertRaisesRegex(OMLError, "SUBMISSION_AMBIGUOUS"):
                    service.submit_stage(run["run_id"], "scf", plan.digest)
            with self.assertRaisesRegex(OMLError, "DUPLICATE_JOB"):
                service.submit_stage(run["run_id"], "scf", plan.digest)

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
            command_completed(run_dir, "scf")
            output = run_dir / "OUT.ABACUS"
            output.mkdir()
            (output / "running_scf.log").write_text("Finish Time\nTotal Time\n")
            (output / "ABACUS-CHARGE-DENSITY.restart").write_text("charge\n")
            (run_dir / "vxc_out").write_text("vxc\n")
            (run_dir / "stru_out").write_text("structure\n")
            with patch("oml_mcp.executor.subprocess.run") as observe:
                observe.return_value = subprocess.CompletedProcess([], 0, "COMPLETED\n", "")
                service.get_status(run["run_id"], attempt["attempt_id"])

            inspection = service.inspect_stage(run["run_id"], attempt["attempt_id"], plan.digest)

        self.assertTrue(inspection["accepted"])
        self.assertEqual(inspection["attempt_status"], "PASSED")

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
            ):
                inspection = service.inspect_stage(
                    run["run_id"], pyatb["attempt_id"], plan.digest
                )

        self.assertFalse(inspection["accepted"])
        self.assertEqual(inspection["attempt_status"], "FAILED")
        self.assertTrue(any(gate["gate_id"] == "pyatb.alignment" for gate in inspection["gates"]))


if __name__ == "__main__":
    unittest.main()
