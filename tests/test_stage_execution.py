import pathlib
import tempfile
import unittest

from oml_mcp.stage_execution import (
    LIBRPA_FAILURE_MARKERS,
    STAGE_EXECUTION_MODES,
    LibrpaMonitorVerdict,
    LoginNodePolicy,
    StageExecutionError,
    monitor_librpa,
    monitor_librpa_until_settled,
    plan_stage_placement,
    preflight_librpa_input,
    render_login_node_script,
    run_login_node_stage,
)
from oml_mcp.stage_templates import CONTROLLED_PERIODIC_STAGES


RUNTIME = {
    "python": "/usr/bin/python3",
    "mpi_launcher": "/usr/bin/mpirun",
    "abacus": "/opt/abacus",
    "librpa": "/opt/chi0_main.exe",
    "mpi_ranks": 4,
    "pyatb_mpi_ranks": 1,
    "omp_threads": 4,
}


class PlacementTest(unittest.TestCase):
    def test_every_controlled_stage_has_a_mode(self):
        for stage in CONTROLLED_PERIODIC_STAGES:
            self.assertIn(stage, STAGE_EXECUTION_MODES)

    def test_fast_stages_are_eligible_for_the_login_node(self):
        # nscf/pyatb/preprocess are seconds-scale; scf/librpa are not.
        self.assertEqual(STAGE_EXECUTION_MODES["nscf"], "login_node")
        self.assertEqual(STAGE_EXECUTION_MODES["pyatb"], "login_node")
        self.assertEqual(STAGE_EXECUTION_MODES["preprocess"], "login_node")
        self.assertEqual(STAGE_EXECUTION_MODES["scf"], "scheduler")
        self.assertEqual(STAGE_EXECUTION_MODES["librpa"], "scheduler")

    def test_heavy_stages_never_move_to_the_login_node(self):
        policy = LoginNodePolicy(
            enabled=True,
            allowed_stages=("pyatb", "nscf", "preprocess"),
            ssh_host="df",
        )

        placements = {p.stage: p for p in plan_stage_placement(CONTROLLED_PERIODIC_STAGES, login_node=policy)}

        self.assertEqual(placements["scf"].mode, "scheduler")
        self.assertEqual(placements["librpa"].mode, "scheduler")
        self.assertEqual(placements["nscf"].mode, "login_node")

    def test_disabled_policy_sends_everything_to_the_scheduler(self):
        policy = LoginNodePolicy(enabled=False, ssh_host=None)

        placements = plan_stage_placement(CONTROLLED_PERIODIC_STAGES, login_node=policy)

        self.assertTrue(all(p.mode == "scheduler" for p in placements))

    def test_policy_requires_a_host_when_enabled(self):
        with self.assertRaisesRegex(StageExecutionError, "ssh_host"):
            LoginNodePolicy(enabled=True, ssh_host=None)

    def test_policy_rejects_ineligible_stage_in_allow_list(self):
        with self.assertRaisesRegex(StageExecutionError, "not eligible"):
            LoginNodePolicy(enabled=True, allowed_stages=("librpa",), ssh_host="df")

    def test_placements_carry_a_reason(self):
        policy = LoginNodePolicy(enabled=True, ssh_host="df")

        placements = plan_stage_placement(("nscf", "librpa"), login_node=policy)

        for placement in placements:
            self.assertTrue(placement.reason)


class LoginNodeScriptTest(unittest.TestCase):
    def test_script_writes_the_standard_command_receipt(self):
        script = render_login_node_script(
            "nscf", runtime=RUNTIME, run_id="run-1", attempt_id="attempt-1"
        )

        # The same receipt format the scheduled path writes, so the existing
        # stage-inspection gates apply unchanged.
        self.assertIn(".oml/stage-results/nscf.status", script)
        self.assertIn("COMMAND_COMPLETED:attempt-1", script)
        self.assertIn("#OML_LOGIN_NODE=1", script)

    def test_script_uses_the_shared_stage_body(self):
        from oml_mcp.stage_templates import stage_body

        script = render_login_node_script(
            "nscf", runtime=RUNTIME, run_id="run-1", attempt_id="a"
        )

        self.assertIn(stage_body("nscf").strip().splitlines()[0], script)

    def test_heavy_stage_cannot_be_rendered_for_the_login_node(self):
        with self.assertRaisesRegex(StageExecutionError, "not eligible"):
            render_login_node_script(
                "librpa", runtime=RUNTIME, run_id="run-1", attempt_id="a"
            )


class LoginNodeRunTest(unittest.TestCase):
    def test_successful_stage_is_completed(self):
        result = run_login_node_stage(
            stage="pyatb",
            run_dir="/remote/run",
            script="echo hi",
            ssh_host="df",
            runner=lambda argv, script, timeout: (0, "ok", ""),
        )

        self.assertEqual(result.status, "COMPLETED")
        self.assertTrue(result.observed)

    def test_nonzero_exit_is_failed(self):
        result = run_login_node_stage(
            stage="pyatb",
            run_dir="/remote/run",
            script="false",
            ssh_host="df",
            runner=lambda argv, script, timeout: (2, "", "boom"),
        )

        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.exit_code, 2)

    def test_timeout_is_unobserved_never_success(self):
        result = run_login_node_stage(
            stage="pyatb",
            run_dir="/remote/run",
            script="sleep 999",
            ssh_host="df",
            runner=lambda argv, script, timeout: (None, "", "timeout"),
        )

        self.assertEqual(result.status, "UNKNOWN")
        self.assertFalse(result.observed)

    def test_ineligible_stage_is_refused(self):
        with self.assertRaisesRegex(StageExecutionError, "not eligible"):
            run_login_node_stage(
                stage="librpa",
                run_dir="/remote/run",
                script="x",
                ssh_host="df",
                runner=lambda a, s, t: (0, "", ""),
            )


class LibrpaMonitorTest(unittest.TestCase):
    def _write(self, root: pathlib.Path, name: str, text: str) -> None:
        (root / name).write_text(text, encoding="utf-8")

    def test_missing_output_is_unobserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            verdict = monitor_librpa(tmpdir)

        self.assertEqual(verdict.state, "UNOBSERVED")

    def test_failure_marker_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(root, "librpa_para_nprocs_4_myid_0.out", "Error on MPI rank 0\n")

            verdict = monitor_librpa(root)

        self.assertEqual(verdict.state, "FAILING")
        self.assertTrue(any("mpi_error" in m for m in verdict.failure_markers))

    def test_nan_in_live_output_is_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(root, "LibRPA.123.out", "Wc(q) = nan\n")

            verdict = monitor_librpa(root)

        self.assertEqual(verdict.state, "FAILING")

    def test_completion_marker_is_finished(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(root, "LibRPA.123.out", "libRPA finished successfully\n")

            verdict = monitor_librpa(root)

        self.assertEqual(verdict.state, "FINISHED")

    def test_growing_output_is_running(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(root, "LibRPA.123.out", "working on q=3\n")

            verdict = monitor_librpa(root, previous_size=1)

        self.assertEqual(verdict.state, "RUNNING")

    def test_static_output_is_stalled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(root, "LibRPA.123.out", "working on q=3\n")
            size = (root / "LibRPA.123.out").stat().st_size

            verdict = monitor_librpa(root, previous_size=size)

        self.assertEqual(verdict.state, "STALLED")
        self.assertTrue(verdict.stalled)

    def test_failure_beats_progress_marker(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(
                root,
                "LibRPA.123.out",
                "libRPA finished successfully\nError on MPI rank 1\n",
            )

            verdict = monitor_librpa(root)

        self.assertEqual(verdict.state, "FAILING")

    def test_until_settled_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(root, "LibRPA.123.out", "Error on MPI rank 0\n")

            verdict = monitor_librpa_until_settled(
                root, poll_seconds=0, max_polls=3, sleep=lambda _: None
            )

        self.assertEqual(verdict.state, "FAILING")

    def test_until_settled_reports_a_wedge_instead_of_waiting(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._write(root, "LibRPA.123.out", "working\n")

            verdict = monitor_librpa_until_settled(
                root, poll_seconds=0, max_polls=6, sleep=lambda _: None
            )

        self.assertEqual(verdict.state, "STALLED")


class PreflightTest(unittest.TestCase):
    def test_missing_inputs_produce_a_failure_report(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = preflight_librpa_input(tmpdir, task="gw", system_type="solid")

        # No INPUT_scf / librpa.in: the preflight must refuse, not pass.
        self.assertFalse(report["accepted"])
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["failed_gates"])

    def test_preflight_has_a_stable_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = preflight_librpa_input(tmpdir)

        self.assertEqual(report["schema"], "oml.librpa-preflight.v1")
        for key in ("accepted", "status", "failed_gates", "warned_gates", "gates"):
            self.assertIn(key, report)


if __name__ == "__main__":
    unittest.main()
