import json
import pathlib
import shutil
import tempfile
import unittest

from oml_mcp.evolution import EvolutionBudget
from oml_mcp.evolution_runner import (
    DEFAULT_UPSTREAM_ROOT,
    load_reference_texts,
    prescription_definition,
    run_evolution,
    stage_check,
)
from oml_mcp.fast_benchmark import load_fast_case
from oml_mcp.self_iteration import SelfIterationError


UPSTREAM_ROOT = DEFAULT_UPSTREAM_ROOT


def _upstream_available(case_id: str) -> bool:
    case = load_fast_case(case_id)
    if case.upstream_directory is None:
        return False
    return (UPSTREAM_ROOT / case.upstream_directory).is_dir()


class PrescriptionBaselineTest(unittest.TestCase):
    def test_baseline_is_a_flat_definition_with_prescription_values(self):
        baseline = prescription_definition("bn-3d-sym-shrink-g0w0")

        self.assertIsInstance(baseline, dict)
        # The heavy-element rule pins an explicit exx threshold; the BN family
        # does not, so it falls back to the default.
        self.assertIn("nfreq", baseline)
        for name, value in baseline.items():
            self.assertNotIsInstance(value, dict, f"{name} must be flat")

    def test_propose_only_loop_never_executes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = run_evolution(
                case_id="bn-3d-sym-shrink-g0w0",
                axis_values={"nfreq": (16, 24)},
                allowed_axes=("nfreq",),
                budget=EvolutionBudget(
                    cpu_hours=1.0,
                    wall_seconds=600,
                    disk_bytes=10**9,
                    max_candidates=2,
                ),
                execute=False,
                staging_root=tmpdir,
            )

        self.assertEqual(report["mode"], "propose_only")
        self.assertFalse(report["executed"])
        self.assertGreaterEqual(len(report["ledger"]), 1)
        for record in report["ledger"]:
            self.assertEqual(record["outcome"], "NOT_EVALUATED")
            self.assertIn("execute=True", record["lesson"])

    def test_execute_requires_profile_and_staging_root(self):
        with self.assertRaises(SelfIterationError):
            run_evolution(
                case_id="bn-3d-sym-shrink-g0w0",
                axis_values={"nfreq": (16,)},
                allowed_axes=("nfreq",),
                budget=EvolutionBudget(
                    cpu_hours=1.0, wall_seconds=60, disk_bytes=10**9, max_candidates=1
                ),
                execute=True,
            )


class StageCheckTest(unittest.TestCase):
    def setUp(self):
        if not _upstream_available("bn-3d-sym-shrink-g0w0"):
            self.skipTest("upstream LibRPA regression suite not available")

    def tearDown(self):
        bundle = pathlib.Path(tempfile.gettempdir()) / "stagecheck-bn-3d-sym-shrink-g0w0"
        shutil.rmtree(bundle, ignore_errors=True)

    def test_stage_check_reports_applied_parameters_and_reference_gap(self):
        candidate = prescription_definition("bn-3d-sym-shrink-g0w0")
        candidate["nfreq"] = 16

        with tempfile.TemporaryDirectory() as tmpdir:
            report = stage_check(
                "bn-3d-sym-shrink-g0w0", UPSTREAM_ROOT, candidate, staging_root=tmpdir
            )
            self.assertTrue(pathlib.Path(report["bundle"]).is_dir())

        self.assertEqual(report["case_id"], "bn-3d-sym-shrink-g0w0")
        self.assertIn("nfreq", report["applied"])
        self.assertEqual(report["applied"]["nfreq"], 16)
        # The frozen reference outputs must be found upstream, or honestly
        # reported as missing; either way the report names them.
        self.assertTrue(
            report["reference_files_found"] or report["reference_files_missing"]
        )

    def test_reference_loader_reads_frozen_outputs(self):
        case = load_fast_case("bn-3d-sym-shrink-g0w0")

        reference = load_reference_texts("bn-3d-sym-shrink-g0w0", UPSTREAM_ROOT)

        found = sorted(reference)
        missing = sorted(set(case.output_files) - set(reference))
        # Either every declared output exists upstream or the missing ones are
        # exactly the difference; the loader never invents content.
        self.assertEqual(sorted(set(found) | set(missing)), sorted(case.output_files))


if __name__ == "__main__":
    unittest.main()
