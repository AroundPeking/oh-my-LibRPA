import pathlib
import tempfile
import unittest

import numpy as np

from oml_mcp.diagnostic_canary import (
    run_diagnostic_battery,
    score_diagnostic_battery,
)
from tests.test_artifacts import (
    write_eigenvector_v1,
    write_headwing_metadata,
    write_velocity_v1,
)
from tests.test_known_issues import _coulomb_bytes
from tests.test_stage_inspection import command_completed, write_coulomb_block


def _write_scf_run(root: pathlib.Path) -> None:
    command_completed(root, "scf")
    output = root / "OUT.ABACUS"
    output.mkdir(exist_ok=True)
    (output / "running_scf.log").write_text(
        "#SCF IS CONVERGED#\nFinish Time\nTotal  Time\n", encoding="utf-8"
    )
    (output / "ABACUS-CHARGE-DENSITY.restart").write_text("charge\n")
    (root / "vxc_out").write_text("vxc\n")
    (root / "stru_out").write_text("structure\n")


def _write_pyatb_run(root: pathlib.Path, coulomb_matrix: np.ndarray) -> None:
    """Write a fully-clean pyatb stage fixture with a real reader-v1 Coulomb block."""
    command_completed(root, "pyatb")
    headwing = root / "pyatb_librpa_df"
    headwing.mkdir(exist_ok=True)
    write_headwing_metadata(headwing)
    write_eigenvector_v1(headwing / "KS_eigenvector_0.dat")
    write_velocity_v1(headwing / "velocity_matrix")
    # Root-level reader-v1 dataset for the state-space and dataset gates.
    (root / "band_out").write_text("1 1 2 2\n0.0\n", encoding="utf-8")
    for name in ("basis_wfc_out", "basis_aux_out"):
        (root / name).write_text("data\n")
    (root / "KS_eigenvector_0.dat").write_bytes(b"data")
    (root / "v1_Cs_data_0.dat").write_bytes(b"data")
    write_coulomb_block(
        root / "v1_coulomb_full_iq_1_rank0.dat",
        np.asarray(coulomb_matrix, dtype=np.complex128),
    )
    write_coulomb_block(
        root / "v1_coulomb_cut_iq_1_rank0.dat",
        np.asarray(coulomb_matrix, dtype=np.complex128),
    )


def _write_nscf_run(root: pathlib.Path) -> None:
    command_completed(root, "nscf")
    eig = root / "OUT.ABACUS"
    eig.mkdir(exist_ok=True)
    (eig / "running_nscf.log").write_text("Finish Time\nTotal  Time\n", encoding="utf-8")
    (eig / "eig.txt").write_text("0.1\n0.2\n", encoding="utf-8")


def _write_preprocess_run(root: pathlib.Path) -> None:
    command_completed(root, "preprocess")
    (root / "band_kpath_info").write_text("2 3 1 1\n0 0 0\n", encoding="utf-8")
    (root / "band_KS_eigenvalue_k_00001.txt").write_text("0.1 0.2\n", encoding="utf-8")
    (root / "band_KS_eigenvector_k_00001.txt").write_text("1.0 0.0\n", encoding="utf-8")
    (root / "band_vxc_k_00001.txt").write_text("0.0 0.0\n", encoding="utf-8")


def _write_librpa_run(root: pathlib.Path) -> None:
    command_completed(root, "librpa")
    (root / "LibRPA.123.out").write_text("Timer stop:  total.\n", encoding="utf-8")
    (root / "band_kpath_info").write_text("2 2 1 1\n0 0 0\n", encoding="utf-8")
    (root / "GW_band_spin_1.dat").write_text("1 0 0 0 0.0 5.0 0.0 6.0\n", encoding="utf-8")


def _write_full_clean_run(root: pathlib.Path) -> None:
    _write_scf_run(root)
    _write_pyatb_run(root, np.diag([4.0, 9.0]))
    _write_nscf_run(root)
    _write_preprocess_run(root)
    _write_librpa_run(root)


class DiagnosticBatteryTest(unittest.TestCase):
    def test_empty_run_is_not_evaluated_never_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)

            report = run_diagnostic_battery(root)

        # No stage was attempted: the battery must not false-pass.
        self.assertEqual(report["status"], "NOT_EVALUATED")
        self.assertFalse(report["accepted"])
        self.assertEqual(report["promotion_eligibility"], "BLOCKED")
        for stage in ("scf", "pyatb", "nscf", "preprocess", "librpa"):
            self.assertEqual(report["stage_statuses"][stage], "NOT_EVALUATED")

    def test_partial_run_is_not_evaluated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_scf_run(root)
            # Only scf was attempted; pyatb/nscf/preprocess/librpa were not.

            report = run_diagnostic_battery(root)

        self.assertEqual(report["stage_statuses"]["scf"], "PASS")
        self.assertEqual(report["stage_statuses"]["pyatb"], "NOT_EVALUATED")
        self.assertEqual(report["status"], "NOT_EVALUATED")

    def test_full_clean_battery_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_full_clean_run(root)

            report = run_diagnostic_battery(root)

        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["accepted"])
        self.assertEqual(report["promotion_eligibility"], "ENABLED")
        self.assertEqual(
            report["stage_statuses"],
            {"scf": "PASS", "pyatb": "PASS", "nscf": "PASS", "preprocess": "PASS", "librpa": "PASS"},
        )

    def test_indefinite_coulomb_fails_battery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_scf_run(root)
            # Indefinite Coulomb matrix: eigenvalues [4.0, -1.0]
            _write_pyatb_run(root, np.diag([4.0, -1.0]))
            _write_nscf_run(root)
            _write_preprocess_run(root)
            _write_librpa_run(root)

            report = run_diagnostic_battery(root)

        self.assertEqual(report["stage_statuses"]["pyatb"], "FAIL")
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["accepted"])
        # Remediation must identify the Coulomb issue as the top match.
        self.assertEqual(report["remediation"]["matches"][0]["issue"]["gate_id"], "coulomb.psd_hermitian")

    def test_unattempted_stage_stays_not_evaluated_even_with_clean_others(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_scf_run(root)
            _write_pyatb_run(root, np.diag([4.0, 9.0]))
            # nscf, preprocess, librpa not attempted.
            report = run_diagnostic_battery(root)

        self.assertEqual(report["stage_statuses"]["scf"], "PASS")
        self.assertEqual(report["stage_statuses"]["pyatb"], "PASS")
        self.assertEqual(report["status"], "NOT_EVALUATED")

    def test_score_battery_blocks_unproven_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_full_clean_run(root)

            report = run_diagnostic_battery(root)
            scored = score_diagnostic_battery(report)

        self.assertEqual(scored["status"], "PASS")
        self.assertEqual(scored["promotion_eligibility"], "ENABLED")
        # The battery proves only internal consistency, not reference accuracy.
        self.assertIn("reference accuracy remains unproven", scored["evidence_note"])

    def test_score_battery_blocks_not_evaluated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_scf_run(root)
            report = run_diagnostic_battery(root)
            scored = score_diagnostic_battery(report)

        self.assertEqual(scored["status"], "NOT_EVALUATED")
        self.assertEqual(scored["promotion_eligibility"], "BLOCKED")
        self.assertIn("pyatb", scored["not_evaluated"])

    def test_invalid_stage_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            with self.assertRaisesRegex(ValueError, "unsupported controlled stage"):
                run_diagnostic_battery(root, stages=("scf", "bogus"))


if __name__ == "__main__":
    unittest.main()
