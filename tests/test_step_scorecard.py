import pathlib
import tempfile
import unittest

import numpy as np

from oml_mcp.step_scorecard import STEP_WEIGHTS, score_run_steps
from tests.test_diagnostic_canary import (
    _write_full_clean_run,
    _write_pyatb_run,
    command_completed,
)


class StepScorecardTest(unittest.TestCase):
    def test_step_weights_sum_to_exactly_100(self):
        self.assertEqual(sum(STEP_WEIGHTS.values()), 100)
        self.assertEqual(set(STEP_WEIGHTS), {
            "scf", "nscf", "pyatb", "coulomb_dataset", "preprocess", "librpa", "handoff",
        })

    def test_empty_run_scores_zero_and_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = score_run_steps(pathlib.Path(tmpdir))

        self.assertEqual(report["status"], "NOT_EVALUATED")
        self.assertEqual(report["total_points"], 0)
        self.assertEqual(report["promotion_eligibility"], "BLOCKED")
        for step in report["steps"]:
            self.assertEqual(step["points"], 0)
            self.assertEqual(step["status"], "NOT_EVALUATED")

    def test_clean_full_run_earns_all_100_points_step_by_step(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_full_clean_run(root)

            report = score_run_steps(root)

        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["total_points"], 100)
        self.assertEqual(report["promotion_eligibility"], "ENABLED")
        by_step = {step["step"]: step for step in report["steps"]}
        for step, data in by_step.items():
            self.assertEqual(data["status"], "PASS", step)
            self.assertEqual(data["points"], data["weight"], step)
        # The state-space contract must be attributed to the handoff step.
        self.assertIn(
            "stage.state_space.nbands_vs_nbasis", by_step["handoff"]["gate_ids"]
        )
        # The Coulomb PSD gate must be attributed to the Coulomb step.
        self.assertTrue(
            any(g.startswith("coulomb.") for g in by_step["coulomb_dataset"]["gate_ids"])
        )

    def test_indefinite_coulomb_zeroes_only_the_coulomb_step(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_full_clean_run(root)
            # Overwrite the pyatb-stage full-Coulomb block with an indefinite one.
            from tests.test_stage_inspection import write_coulomb_block

            write_coulomb_block(
                root / "v1_coulomb_full_iq_1_rank0.dat",
                np.diag([4.0, -641.0]).astype(np.complex128),
            )

            report = score_run_steps(root)

        by_step = {step["step"]: step for step in report["steps"]}
        self.assertEqual(by_step["coulomb_dataset"]["status"], "FAIL")
        self.assertEqual(by_step["coulomb_dataset"]["points"], 0)
        self.assertEqual(report["status"], "FAIL")
        self.assertLessEqual(report["total_points"], 85)
        # The untouched steps keep their full points.
        self.assertEqual(by_step["scf"]["points"], STEP_WEIGHTS["scf"])
        self.assertEqual(by_step["librpa"]["points"], STEP_WEIGHTS["librpa"])

    def test_partially_attempted_run_is_not_evaluated_never_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            command_completed(root, "scf")
            output = root / "OUT.ABACUS"
            output.mkdir()
            (output / "running_scf.log").write_text(
                "#SCF IS CONVERGED#\nFinish Time\nTotal  Time\n", encoding="utf-8"
            )
            (output / "ABACUS-CHARGE-DENSITY.restart").write_text("charge\n")
            (root / "vxc_out").write_text("vxc\n")
            (root / "stru_out").write_text("structure\n")

            report = score_run_steps(root)

        by_step = {step["step"]: step for step in report["steps"]}
        self.assertEqual(by_step["scf"]["status"], "PASS")
        self.assertEqual(by_step["scf"]["points"], STEP_WEIGHTS["scf"])
        self.assertEqual(report["status"], "NOT_EVALUATED")
        self.assertEqual(report["promotion_eligibility"], "BLOCKED")
        self.assertEqual(report["total_points"], STEP_WEIGHTS["scf"])


if __name__ == "__main__":
    unittest.main()
