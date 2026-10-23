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

    def test_negative_eigenvalue_fails(self):
        matrix = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=complex)
        report = check_positive_semidefinite(matrix)
        self.assertFalse(report["pass"])
        self.assertEqual(report["negative_count"], 1)
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
