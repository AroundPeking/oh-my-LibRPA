import unittest

import numpy as np

from oml_mcp.coulomb_gate import (
    CoulombGateError,
    check_hermitian,
    check_positive_semidefinite,
    compare_constructions,
    coulomb_health,
    hermitian_residual,
)


class CoulombGateTest(unittest.TestCase):
    def test_hermitian_psd_matrix_passes(self):
        matrix = np.array([[2.0, 0.5], [0.5, 1.0]], dtype=complex)
        report = coulomb_health(matrix)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual(report["findings"], [])
        self.assertTrue(report["hermitian"]["pass"])
        self.assertTrue(report["psd"]["pass"])

    def test_non_hermitian_matrix_fails(self):
        matrix = np.array([[1.0, 2.0], [0.0, 1.0]], dtype=complex)
        self.assertGreater(hermitian_residual(matrix), 0)
        report = coulomb_health(matrix)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertIn("not Hermitian", " ".join(report["findings"]))

    def test_small_negative_count_is_tolerated(self):
        matrix = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=complex)
        report = check_positive_semidefinite(matrix)
        self.assertTrue(report["pass"])
        self.assertEqual(report["negative_count"], 1)
        self.assertEqual(report["tolerated_negative_count"], 1)
        self.assertEqual(coulomb_health(matrix)["verdict"], "PASS")

    def test_too_many_negative_eigenvalues_fail(self):
        matrix = np.diag([1.0] + [-1.0] * 11).astype(complex)
        report = check_positive_semidefinite(matrix)
        self.assertFalse(report["pass"])
        self.assertEqual(report["negative_count"], 11)
        self.assertEqual(coulomb_health(matrix)["verdict"], "FAIL")

    def test_cross_construction_agreement(self):
        left = np.eye(3, dtype=complex)
        self.assertTrue(compare_constructions(left, left)["agree"])
        right = np.eye(3, dtype=complex)
        right[1, 1] = 1.5
        report = coulomb_health(left, other_construction=right)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertIn("disagree", " ".join(report["findings"]))

    def test_shape_mismatch_is_rejected(self):
        with self.assertRaises(CoulombGateError):
            compare_constructions(np.eye(2), np.eye(3))
        with self.assertRaises(CoulombGateError):
            check_hermitian([1.0, 2.0])


if __name__ == "__main__":
    unittest.main()


class CutCoulombCholeskyTest(unittest.TestCase):
    """The Wc Cholesky switch must follow the actual cut-Coulomb definiteness."""

    def _write_block(self, directory, values):
        import struct
        from pathlib import Path

        matrix = np.asarray(values, dtype=np.float64)
        naux = matrix.shape[0]
        header = struct.pack("=6i", -20129433, 1, naux, 0, 1, 1)
        atom_naux = struct.pack("=1i", naux)
        offset = len(header) + len(atom_naux) + 8
        records = struct.pack("=2i", 0, offset)
        path = Path(directory) / "v1_coulomb_cut_iq_1_rank0.dat"
        path.write_bytes(header + atom_naux + records + matrix.tobytes())
        return path

    def test_decision_table(self):
        from oml_mcp.coulomb_diagnostics import cut_cholesky_decision

        self.assertEqual(
            cut_cholesky_decision(positive_definite=False, use_cholesky=True)[0], "FAIL"
        )
        self.assertEqual(
            cut_cholesky_decision(positive_definite=False, use_cholesky=False)[0], "PASS"
        )
        self.assertEqual(
            cut_cholesky_decision(positive_definite=False, use_cholesky=None)[0], "WARN"
        )
        self.assertEqual(
            cut_cholesky_decision(positive_definite=True, use_cholesky=True)[0], "PASS"
        )
        self.assertEqual(
            cut_cholesky_decision(positive_definite=True, use_cholesky=False)[0], "WARN"
        )
        self.assertEqual(
            cut_cholesky_decision(positive_definite=True, use_cholesky=None)[0], "PASS"
        )

    def test_non_pd_cut_coulomb_requires_cholesky_off(self):
        import tempfile
        from pathlib import Path
        from oml_mcp.coulomb_diagnostics import inspect_cut_coulomb_cholesky

        with tempfile.TemporaryDirectory() as tmp:
            self._write_block(tmp, [[1.0, 0.0], [0.0, -1.0]])
            (Path(tmp) / "librpa.in").write_text("use_cholesky_gw_wc = t\n", encoding="utf-8")
            gate = inspect_cut_coulomb_cholesky(tmp, use_cholesky=True)
            self.assertEqual(gate.status, "FAIL")
            self.assertIn("use_cholesky_gw_wc = f", gate.repair)
            gate = inspect_cut_coulomb_cholesky(tmp, use_cholesky=False)
            self.assertEqual(gate.status, "PASS")
            (Path(tmp) / "librpa.in").unlink()
            gate = inspect_cut_coulomb_cholesky(tmp, use_cholesky=None)
            self.assertEqual(gate.status, "WARN")

    def test_pd_cut_coulomb_can_enable_cholesky(self):
        import tempfile
        from oml_mcp.coulomb_diagnostics import inspect_cut_coulomb_cholesky

        with tempfile.TemporaryDirectory() as tmp:
            self._write_block(tmp, [[2.0, 0.0], [0.0, 1.0]])
            self.assertEqual(
                inspect_cut_coulomb_cholesky(tmp, use_cholesky=True).status, "PASS"
            )
            self.assertEqual(
                inspect_cut_coulomb_cholesky(tmp, use_cholesky=False).status, "WARN"
            )

    def test_missing_cut_family_is_skip(self):
        import tempfile
        from oml_mcp.coulomb_diagnostics import inspect_cut_coulomb_cholesky

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(inspect_cut_coulomb_cholesky(tmp).status, "SKIP")
