import pathlib
import struct
import tempfile
import unittest

import numpy as np

from oml_mcp.sternheimer_diagnostics import (
    inspect_grid_coulomb_consistency,
    inspect_sternheimer_comparison,
)


COULOMB_MARKER = -20129433
CHI0_MARKER = -41073291


def write_coulomb(path: pathlib.Path, matrix: np.ndarray, *, iq: int = 21) -> None:
    naux = matrix.shape[0]
    header_bytes = 24 + 4 + 12
    data = struct.pack("=6i", COULOMB_MARKER, iq, naux, 1, 1, 1)
    data += struct.pack("=i", naux)
    data += struct.pack("=iq", 0, header_bytes)
    data += np.asarray(matrix, dtype=np.complex128).tobytes(order="C")
    path.write_bytes(data)


def write_response(
    path: pathlib.Path,
    matrix: np.ndarray,
    *,
    iq: int = 21,
    ifreq: int = 1,
    omega: float = 0.25,
    weight: float = 1.0,
) -> None:
    naux = matrix.shape[0]
    header_bytes = 24 + 16 + 4 + 4 + 12
    data = struct.pack("=6i", CHI0_MARKER, iq, ifreq, naux, 1, 1)
    data += struct.pack("=2d", omega, weight)
    data += struct.pack("=i", 1)
    data += struct.pack("=i", naux)
    data += struct.pack("=iq", 0, header_bytes)
    data += np.asarray(matrix, dtype=np.complex128).tobytes(order="C")
    path.write_bytes(data)


def write_comparison_fixture(root: pathlib.Path) -> None:
    coulomb = np.diag([4.0, 9.0]).astype(np.complex128)
    in_sos = np.diag([-0.30, -0.50]).astype(np.complex128)
    in_pulay = np.diag([-0.10, -0.20]).astype(np.complex128)
    out_grid = np.diag([0.00, -0.20]).astype(np.complex128)
    total = in_sos + in_pulay + out_grid

    write_coulomb(root / "v1_coulomb_full_iq_21_rank0.dat", coulomb)
    write_response(root / "v1_sternheimer_chi0_iq_21_ifreq_1_rank0.dat", total)
    write_response(root / "v1_sternheimer_lcao_sos_iq_21_ifreq_1_rank0.dat", total)
    write_response(root / "v1_sternheimer_delta_in_sos_iq_21_ifreq_1_rank0.dat", in_sos)
    write_response(root / "v1_sternheimer_delta_in_pulay_iq_21_ifreq_1_rank0.dat", in_pulay)
    write_response(root / "v1_sternheimer_delta_out_grid_iq_21_ifreq_1_rank0.dat", out_grid)


def write_grid_coulomb(path: pathlib.Path, matrix: np.ndarray) -> None:
    lines = ["# row col real imag", f"naux {matrix.shape[0]}"]
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            lines.append(f"{row} {column} {value.real:.17g} {value.imag:.17g}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class SternheimerComparisonTest(unittest.TestCase):
    def test_grid_coulomb_consistency_can_run_before_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            coulomb = np.diag([4.0, 9.0]).astype(np.complex128)
            write_coulomb(root / "v1_coulomb_full_iq_21_rank0.dat", coulomb)
            write_grid_coulomb(root / "STERNHEIMER_GRID_COULOMB.dat", coulomb)

            report = inspect_grid_coulomb_consistency(root, iq=21)

        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "EVALUATED")
        self.assertAlmostEqual(report["measurements"]["generalized_eigenvalue_min"], 1.0)
        self.assertAlmostEqual(report["measurements"]["generalized_eigenvalue_max"], 1.0)

    def test_incompatible_grid_coulomb_blocks_response_production(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_coulomb(
                root / "v1_coulomb_full_iq_21_rank0.dat",
                np.diag([4.0, 9.0]).astype(np.complex128),
            )
            write_grid_coulomb(
                root / "STERNHEIMER_GRID_COULOMB.dat",
                np.diag([4.0, 18.0]).astype(np.complex128),
            )

            report = inspect_grid_coulomb_consistency(root, iq=21)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "CONTRACT_FAIL")
        gate = next(
            item for item in report["gates"] if item["gate_id"] == "representation_consistency"
        )
        self.assertEqual(gate["status"], "FAIL")
        self.assertIn("response production", gate["repair"])

    def test_complete_same_state_fixture_reports_reconstruction_and_trace_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_comparison_fixture(root)

            report = inspect_sternheimer_comparison(root, iq=21, ifreq=1)

        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "EVALUATED")
        self.assertEqual({gate["status"] for gate in report["gates"]}, {"PASS"})
        measurements = report["measurements"]
        self.assertLess(measurements["component_reconstruction_relative_error"], 1.0e-14)
        self.assertLess(measurements["delta_vs_lcao_relative_error"], 1.0e-14)
        self.assertEqual(measurements["dominant_delta_component"], "in_sos")
        self.assertIn("in_sos_vs_lcao_relative_error", measurements)
        self.assertEqual(
            set(measurements["component_to_lcao_norm_ratios"]),
            {"in_sos", "in_pulay", "out_grid", "pulay_plus_out_grid"},
        )
        self.assertLess(measurements["trace_log"]["delta"]["integrand_real"], 0.0)
        self.assertEqual(
            len(measurements["trace_log"]["delta"]["most_negative_pi_eigenvalues"]),
            2,
        )
        self.assertGreater(
            measurements["trace_log"]["delta"]["most_negative_mode_coulomb_rayleigh"],
            0.0,
        )
        self.assertEqual(measurements["matrix_dimension"], 2)

    def test_response_metadata_mismatch_is_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_comparison_fixture(root)
            path = root / "v1_sternheimer_lcao_sos_iq_21_ifreq_1_rank0.dat"
            write_response(path, np.diag([-0.4, -0.9]), omega=0.5)

            report = inspect_sternheimer_comparison(root, iq=21, ifreq=1)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "CONTRACT_FAIL")
        self.assertIn("metadata", {gate["gate_id"] for gate in report["gates"] if gate["status"] == "FAIL"})

    def test_optional_grid_coulomb_reports_reader_consistency_and_trace_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_comparison_fixture(root)
            write_grid_coulomb(
                root / "STERNHEIMER_GRID_COULOMB.dat",
                np.diag([4.0, 9.0]).astype(np.complex128),
            )

            report = inspect_sternheimer_comparison(root, iq=21, ifreq=1)

        grid = report["measurements"]["grid_coulomb"]
        self.assertTrue(grid["present"])
        self.assertLess(grid["relative_error_to_reader_v1"], 1.0e-14)
        self.assertAlmostEqual(grid["generalized_eigenvalue_min"], 1.0)
        self.assertAlmostEqual(grid["generalized_eigenvalue_max"], 1.0)
        self.assertLess(grid["maximum_generalized_deviation_from_one"], 1.0e-14)
        self.assertAlmostEqual(
            grid["trace_log"]["delta"]["integrand_real"],
            report["measurements"]["trace_log"]["delta"]["integrand_real"],
        )

    def test_post_response_comparison_also_blocks_incompatible_coulomb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_comparison_fixture(root)
            write_grid_coulomb(
                root / "STERNHEIMER_GRID_COULOMB.dat",
                np.diag([4.0, 18.0]).astype(np.complex128),
            )

            report = inspect_sternheimer_comparison(root, iq=21, ifreq=1)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "CONTRACT_FAIL")
        self.assertIn("measurements", report)
        gate = next(
            item for item in report["gates"] if item["gate_id"] == "representation_consistency"
        )
        self.assertEqual(gate["status"], "FAIL")

    def test_incomplete_grid_coulomb_is_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_comparison_fixture(root)
            (root / "STERNHEIMER_GRID_COULOMB.dat").write_text(
                "naux 2\n0 0 4 0\n",
                encoding="utf-8",
            )

            report = inspect_sternheimer_comparison(root, iq=21, ifreq=1)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "CONTRACT_FAIL")
        self.assertIn("every matrix entry", report["gates"][0]["message"])

    def test_missing_component_is_incomplete_not_a_numerical_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_comparison_fixture(root)
            (root / "v1_sternheimer_delta_out_grid_iq_21_ifreq_1_rank0.dat").unlink()

            report = inspect_sternheimer_comparison(root, iq=21, ifreq=1)

        self.assertFalse(report["ok"])
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertIn("files", {gate["gate_id"] for gate in report["gates"] if gate["status"] == "FAIL"})


if __name__ == "__main__":
    unittest.main()
