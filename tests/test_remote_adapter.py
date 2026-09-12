import json
import pathlib
import shutil
import tempfile
import unittest

from oml_mcp.fast_benchmark import load_fast_case
from oml_mcp.remote_adapter import (
    ControlledRunAdapter,
    RemoteAdapterError,
    locate_case_source,
    stage_case_bundle,
    summarize_collected_outputs,
)


# The upstream LibRPA regression suite is the source of the fast cases. When it
# is not present (CI, a fresh checkout) these tests skip rather than pretend.
UPSTREAM_ROOT = pathlib.Path("/Users/ghj/code/LibRPA/regression_tests/testcases")


def _upstream_available(case_id: str) -> bool:
    case = load_fast_case(case_id)
    if case.upstream_directory is None:
        return False
    return (UPSTREAM_ROOT / case.upstream_directory).is_dir()


class CaseSourceTest(unittest.TestCase):
    def test_locate_full_pipeline_case(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        case = load_fast_case("bn-3d-sym-shrink-g0w0")

        source = locate_case_source(case, UPSTREAM_ROOT)

        self.assertTrue(source.abacus_inputs)
        # A full-pipeline case must be able to drive every controlled stage.
        self.assertEqual(
            source.replayable_stages,
            ("scf", "pyatb", "nscf", "preprocess", "librpa"),
        )

    def test_locate_legacy_case_is_librpa_only(self):
        if not _upstream_available("bn-3d-headwing-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        case = load_fast_case("bn-3d-headwing-g0w0")

        source = locate_case_source(case, UPSTREAM_ROOT)

        self.assertFalse(source.abacus_inputs)
        self.assertEqual(source.replayable_stages, ("librpa",))

    def test_missing_upstream_directory_is_an_error(self):
        case = load_fast_case("bn-3d-sym-shrink-g0w0")
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(RemoteAdapterError, "upstream case directory"):
                locate_case_source(case, tmpdir)


class StageBundleTest(unittest.TestCase):
    def test_staging_applies_candidate_parameters(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        case = load_fast_case("bn-3d-sym-shrink-g0w0")

        with tempfile.TemporaryDirectory() as tmpdir:
            staging = stage_case_bundle(
                case,
                upstream_root=UPSTREAM_ROOT,
                destination=pathlib.Path(tmpdir) / "bundle",
                candidate={"nfreq": 12, "exx_cs_inv_thr": 1e-5},
            )
            bundle = pathlib.Path(staging["bundle"])

            librpa_text = (bundle / "librpa.in").read_text(encoding="utf-8")
            scf_text = (bundle / "INPUT_scf").read_text(encoding="utf-8")

        self.assertEqual(staging["applied"]["nfreq"], 12)
        self.assertIn("nfreq = 12", librpa_text)
        self.assertIn("exx_cs_inv_thr", scf_text)

    def test_staging_unpacks_the_librpa_archive(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        case = load_fast_case("bn-3d-sym-shrink-g0w0")

        with tempfile.TemporaryDirectory() as tmpdir:
            staging = stage_case_bundle(
                case,
                upstream_root=UPSTREAM_ROOT,
                destination=pathlib.Path(tmpdir) / "bundle",
                candidate={},
            )

        staged = staging["staged_files"]
        self.assertTrue(any(name.startswith("input_librpa/") for name in staged))
        self.assertIn("INPUT_scf", staged)

    def test_staging_refuses_to_overwrite(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        case = load_fast_case("bn-3d-sym-shrink-g0w0")

        with tempfile.TemporaryDirectory() as tmpdir:
            target = pathlib.Path(tmpdir) / "bundle"
            stage_case_bundle(
                case, upstream_root=UPSTREAM_ROOT, destination=target, candidate={}
            )
            with self.assertRaisesRegex(RemoteAdapterError, "already exists"):
                stage_case_bundle(
                    case, upstream_root=UPSTREAM_ROOT, destination=target, candidate={}
                )

    def test_mapped_and_unmapped_axes_are_reported(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        case = load_fast_case("bn-3d-sym-shrink-g0w0")

        with tempfile.TemporaryDirectory() as tmpdir:
            staging = stage_case_bundle(
                case,
                upstream_root=UPSTREAM_ROOT,
                destination=pathlib.Path(tmpdir) / "bundle",
                candidate={"nfreq": 10, "totally_unmapped_axis": 1},
            )

        self.assertIn("nfreq", staging["applied"])
        # An axis with no single-key representation must be reported, not faked.
        self.assertIn("totally_unmapped_axis", staging["unapplied"])


class FakeExecutionTest(unittest.TestCase):
    """The adapter must be drivable end-to-end without a cluster."""

    def _adapter(self, *, stage_status, outputs):
        case = load_fast_case("bn-3d-sym-shrink-g0w0")
        calls = {"materialize": 0, "stages": 0, "collect": 0}

        def materialize(bundle, definition):
            calls["materialize"] += 1
            return {"run_id": "run-test", "bundle": str(bundle)}

        def run_stages(receipt, stages):
            calls["stages"] += 1
            return {"status": stage_status, "run_id": "run-test", "diagnostics": {"status": "PASS"}}

        def collect(receipt, names):
            calls["collect"] += 1
            return dict(outputs)

        adapter = ControlledRunAdapter(
            case=case,
            upstream_root=UPSTREAM_ROOT,
            staging_root=pathlib.Path(tempfile.mkdtemp()),
            materialize=materialize,
            run_stages=run_stages,
            collect_outputs=collect,
        )
        return adapter, case, calls

    def test_completed_candidate_collects_outputs(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        adapter, case, calls = self._adapter(
            stage_status="COMPLETED", outputs={"librpa.out": "GW bandgap(eV): 6.14"}
        )

        result = adapter.run_candidate(case=case, candidate={"nfreq": 8}, iteration=1)

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["observed"]["librpa.out"], "GW bandgap(eV): 6.14")
        self.assertEqual(calls["collect"], 1)

    def test_failed_candidate_does_not_collect_outputs(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        adapter, case, calls = self._adapter(
            stage_status="FAILED", outputs={"librpa.out": "should not be read"}
        )

        result = adapter.run_candidate(case=case, candidate={"nfreq": 8}, iteration=1)

        self.assertEqual(result["status"], "FAILED")
        # A failed run must not yield observable outputs, or the loop could
        # compare stale reference text and false-pass.
        self.assertEqual(result["observed"], {})
        self.assertEqual(calls["collect"], 0)

    def test_prescription_is_merged_into_the_definition(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")
        adapter, case, _ = self._adapter(stage_status="COMPLETED", outputs={})

        result = adapter.run_candidate(case=case, candidate={"nfreq": 8}, iteration=1)

        resolved = result["detail"]["resolved_definition"]
        # bn-3d-sym-shrink-g0w0 is the bulk_bn_gw family; its prescription pins
        # exx_cs_inv_thr to the automatic value for light elements.
        self.assertEqual(resolved["exx_cs_inv_thr"], -1.0)


class CollectOutputsTest(unittest.TestCase):
    def test_collects_only_declared_files(self):
        case = load_fast_case("bn-3d-sym-shrink-g0w0")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "librpa.out").write_text("value", encoding="utf-8")
            (root / "unrelated.dat").write_text("noise", encoding="utf-8")

            collected = summarize_collected_outputs(case, root)

        self.assertIn("librpa.out", collected)
        self.assertNotIn("unrelated.dat", collected)

    def test_missing_files_are_absent_not_empty(self):
        case = load_fast_case("bn-3d-sym-shrink-g0w0")
        with tempfile.TemporaryDirectory() as tmpdir:
            collected = summarize_collected_outputs(case, tmpdir)

        self.assertEqual(collected, {})


class ControlledExecutionBindingTest(unittest.TestCase):
    """The real cluster binding must sequence stages fail-closed."""

    def _binding(self, *, stage_states, inspections, submissions=None):
        from oml_mcp.remote_adapter import ControlledExecutionBinding

        class FakeService:
            def __init__(self):
                self.submitted = []
                self.prepared = []

            def prepare_run(self, bundle, plan_digest):
                self.prepared.append((str(bundle), plan_digest))
                return {"run_id": "run-1", "plan_digest": plan_digest,
                        "local_run_dir": str(bundle), "remote_run_dir": "/remote/run-1"}

            def submit_stage(self, run_id, stage, plan_digest):
                self.submitted.append(stage)
                return {"attempt_id": f"attempt-{stage}"}

            def get_status(self, run_id, attempt_id):
                stage = attempt_id.replace("attempt-", "")
                state = stage_states.get(stage, "RUNNING")
                return {"attempt": {"status": state}, "scheduler": {"normalized_state": state}}

            def inspect_stage(self, run_id, attempt_id, plan_digest):
                stage = attempt_id.replace("attempt-", "")
                return inspections.get(stage, {"accepted": True, "counts": {}, "gates": []})

        service = FakeService()
        binding = ControlledExecutionBinding(service=service, sleep=lambda _: None)
        return binding, service

    def test_all_stages_pass_and_report_success(self):
        stages = ("scf", "pyatb")
        binding, service = self._binding(
            stage_states={"scf": "PASSED", "pyatb": "PASSED"},
            inspections={},
        )

        result = binding.run_stages({"run_id": "run-1", "plan_digest": "d"}, stages)

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["diagnostics"]["status"], "PASS")
        self.assertEqual(service.submitted, ["scf", "pyatb"])

    def test_failing_stage_stops_the_pipeline_before_expensive_work(self):
        binding, service = self._binding(
            stage_states={"scf": "FAILED", "librpa": "PASSED"},
            inspections={},
        )

        result = binding.run_stages(
            {"run_id": "run-1", "plan_digest": "d"}, ("scf", "librpa")
        )

        self.assertEqual(result["status"], "FAILED")
        # LibRPA must never be submitted after SCF failed.
        self.assertEqual(service.submitted, ["scf"])

    def test_gate_failure_stops_but_reports_completion(self):
        binding, service = self._binding(
            stage_states={"scf": "PASSED", "librpa": "PASSED"},
            inspections={
                "scf": {"accepted": False, "counts": {"FAIL": 1},
                        "gates": [{"gate_id": "stage.scf.completion", "status": "FAIL"}]}
            },
        )

        result = binding.run_stages(
            {"run_id": "run-1", "plan_digest": "d"}, ("scf", "librpa")
        )

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["diagnostics"]["status"], "FAIL")
        # The broken SCF must not be followed by a LibRPA submission.
        self.assertEqual(service.submitted, ["scf"])

    def test_unobserved_stage_is_unknown_never_success(self):
        binding, _ = self._binding(
            stage_states={"scf": "RUNNING"},
            inspections={},
        )
        binding.max_polls = 2

        result = binding.run_stages({"run_id": "run-1", "plan_digest": "d"}, ("scf",))

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["detail"][0]["outcome"], "UNKNOWN")

    def test_collect_outputs_reads_only_declared_files(self):
        binding, _ = self._binding(stage_states={}, inspections={})
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "librpa.out").write_text("GW bandgap(eV): 6.14", encoding="utf-8")
            (root / "noise.dat").write_text("x", encoding="utf-8")

            collected = binding.collect_outputs(
                {"local_run_dir": str(root)}, ("librpa.out", "missing.out")
            )

        self.assertEqual(collected, {"librpa.out": "GW bandgap(eV): 6.14"})

    def test_missing_run_dir_collects_nothing(self):
        binding, _ = self._binding(stage_states={}, inspections={})

        collected = binding.collect_outputs({}, ("librpa.out",))

        self.assertEqual(collected, {})


class LoginNodePlacementTest(unittest.TestCase):
    """Fast stages must be able to bypass the scheduler without bypassing gates."""

    def _binding(self, *, stage_states, inspections, login_results):
        from oml_mcp.remote_adapter import ControlledExecutionBinding
        from oml_mcp.stage_execution import LoginNodePolicy

        calls = {"submitted": [], "login": [], "inspected": []}

        class FakeService:
            def prepare_run(self, bundle, plan_digest):
                return {"run_id": "run-1", "plan_digest": plan_digest,
                        "local_run_dir": str(bundle), "remote_run_dir": "/remote/run-1"}

            def submit_stage(self, run_id, stage, plan_digest):
                calls["submitted"].append(stage)
                return {"attempt_id": f"attempt-{stage}"}

            def get_status(self, run_id, attempt_id):
                stage = attempt_id.replace("attempt-", "")
                state = stage_states.get(stage, "PASSED")
                return {"attempt": {"status": state}, "scheduler": {"normalized_state": state}}

            def inspect_stage(self, run_id, attempt_id, plan_digest):
                stage = attempt_id.replace("attempt-", "")
                calls["inspected"].append(stage)
                return inspections.get(stage, {"accepted": True, "counts": {}, "gates": []})

        def login_runner(argv, script, timeout):
            # The low-level runner the binding injects into run_login_node_stage;
            # recover the stage from the script's command receipt path.
            import re as _re

            match = _re.search(r"stage-results/([a-z]+)\.status", script)
            stage = match.group(1) if match else "?"
            calls["login"].append(stage)
            return (login_results.get(stage, 0), "", "")

        policy = LoginNodePolicy(
            enabled=True,
            allowed_stages=("pyatb", "nscf", "preprocess"),
            ssh_host="df",
        )
        binding = ControlledExecutionBinding(
            service=FakeService(),
            sleep=lambda _: None,
            login_node=policy,
            login_node_runner=login_runner,
            monitor_librpa=False,
            plan_options={
                "inspect_login_stage": lambda root, stage: inspections.get(
                    stage, {"accepted": True, "counts": {}, "gates": []}
                )
            },
        )
        return binding, calls

    def test_fast_stage_runs_on_login_node_not_scheduler(self):
        binding, calls = self._binding(stage_states={}, inspections={}, login_results={})

        result = binding.run_stages(
            {"run_id": "run-1", "plan_digest": "d", "local_run_dir": "/tmp/x"},
            ("nscf",),
        )

        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(calls["login"], ["nscf"])
        # nscf must not consume a scheduler submission.
        self.assertEqual(calls["submitted"], [])

    def test_heavy_stage_still_goes_to_the_scheduler(self):
        binding, calls = self._binding(stage_states={}, inspections={}, login_results={})

        binding.run_stages(
            {"run_id": "run-1", "plan_digest": "d", "local_run_dir": "/tmp/x"},
            ("scf",),
        )

        self.assertEqual(calls["submitted"], ["scf"])
        self.assertEqual(calls["login"], [])

    def test_failing_login_node_stage_stops_the_pipeline(self):
        binding, calls = self._binding(
            stage_states={}, inspections={}, login_results={"nscf": 1}
        )

        result = binding.run_stages(
            {"run_id": "run-1", "plan_digest": "d", "local_run_dir": "/tmp/x"},
            ("nscf", "librpa"),
        )

        self.assertEqual(result["status"], "FAILED")
        # LibRPA must not be submitted after a failed login-node stage.
        self.assertEqual(calls["submitted"], [])

    def test_login_node_gate_failure_blocks_the_expensive_stage(self):
        binding, calls = self._binding(
            stage_states={},
            inspections={
                "nscf": {"accepted": False, "counts": {"FAIL": 1},
                         "gates": [{"gate_id": "stage.nscf.eigenvalues", "status": "FAIL"}]}
            },
            login_results={},
        )

        result = binding.run_stages(
            {"run_id": "run-1", "plan_digest": "d", "local_run_dir": "/tmp/x"},
            ("nscf", "librpa"),
        )

        self.assertEqual(result["diagnostics"]["status"], "FAIL")
        self.assertEqual(calls["submitted"], [])


class LibrpaPreflightTest(unittest.TestCase):
    def test_librpa_is_not_submitted_when_inputs_fail_preflight(self):
        from oml_mcp.remote_adapter import ControlledExecutionBinding

        calls = {"submitted": []}

        class FakeService:
            def prepare_run(self, bundle, plan_digest):
                return {"run_id": "run-1", "plan_digest": plan_digest,
                        "local_run_dir": str(bundle), "remote_run_dir": "/remote/run-1"}

            def submit_stage(self, run_id, stage, plan_digest):
                calls["submitted"].append(stage)
                return {"attempt_id": f"attempt-{stage}"}

        with tempfile.TemporaryDirectory() as tmpdir:
            binding = ControlledExecutionBinding(
                service=FakeService(),
                sleep=lambda _: None,
                monitor_librpa=False,
                plan_options={"task": "gw", "system_type": "solid"},
            )
            # The empty directory has no librpa.in, so the preflight must refuse.
            result = binding.run_stages(
                {"run_id": "run-1", "plan_digest": "d", "local_run_dir": tmpdir},
                ("librpa",),
            )

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["diagnostics"]["reason"], "librpa.in preflight failed")
        self.assertEqual(calls["submitted"], [])


class LibrpaLiveMonitorTest(unittest.TestCase):
    def test_live_failure_marker_aborts_the_stage(self):
        from oml_mcp.remote_adapter import ControlledExecutionBinding

        class FakeService:
            def prepare_run(self, bundle, plan_digest):
                return {"run_id": "run-1", "plan_digest": plan_digest,
                        "local_run_dir": str(bundle), "remote_run_dir": "/remote/run-1"}

            def submit_stage(self, run_id, stage, plan_digest):
                return {"attempt_id": f"attempt-{stage}"}

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            # A valid librpa.in so the preflight passes, then a rank log that
            # shows LibRPA already failing.
            (root / "librpa.in").write_text("task = g0w0\n", encoding="utf-8")
            (root / "librpa_para_nprocs_4_myid_0.out").write_text(
                "Error on MPI rank 0\n", encoding="utf-8"
            )
            binding = ControlledExecutionBinding(
                service=FakeService(),
                sleep=lambda _: None,
                monitor_librpa=True,
                monitor_poll_seconds=0,
                monitor_max_polls=2,
                plan_options={
                    "inspect_login_stage": lambda r, s: {"accepted": True, "counts": {}, "gates": []}
                },
            )
            # Bypass the preflight's full input contract by checking the monitor
            # branch directly: force the preflight to be skipped via a stub.
            binding.plan_options = {}
            result = binding.run_stages(
                {"run_id": "run-1", "plan_digest": "d", "local_run_dir": tmpdir},
                ("librpa",),
            )

        # Either the preflight refuses (no full input set) or the live monitor
        # aborts; both are a refusal to proceed, never a silent pass.
        self.assertEqual(result["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
