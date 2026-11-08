import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from compare_response import compare, to_alpha, validate


class ResponseTest(unittest.TestCase):
    def setUp(self):
        self.w = np.array([0.01, 0.1, 1.0])
        self.a = np.tile([2.0, 0.0, 0.0, 3.0], (3, 1))

    def test_identical_and_ten_percent(self):
        self.assertAlmostEqual(compare(self.w, self.a, self.w, self.a)["relative_l2"], 0)
        r = compare(self.w, self.a, self.w, self.a * 1.1)
        self.assertAlmostEqual(r["relative_l2"], 0.1)
        self.assertAlmostEqual(r["relative_low_max"], 0.1)

    def test_vacuum_invariant(self):
        identity = np.array([1, 0, 0, 1])
        for height in (20, 40):
            np.testing.assert_allclose(to_alpha(identity + 4*np.pi*self.a/height, height), self.a)

    def test_log_interpolation_but_linear_measure(self):
        a = np.ones((3, 4))
        p = a + np.log(self.w[:, None]/self.w[0])
        r = compare(self.w, a, self.w, p)
        expected = np.sqrt(np.trapz(np.sum((p-a)**2, axis=1), self.w)/np.trapz(np.sum(a*a, axis=1), self.w))
        self.assertAlmostEqual(r["relative_l2"], expected)

    def test_undefined_not_zero(self):
        r = compare(self.w, self.a*0, self.w, self.a)
        self.assertIsNone(r["relative_l2"])
        self.assertIsNone(r["relative_low_max"])
        self.assertGreater(r["absolute_max"], 0)

    def test_reject_bad_input(self):
        for w in ([0, 0.1, 1], [0.1, 0.1, 1], [1, 0.1, 0.01]):
            with self.assertRaises(ValueError):
                validate(np.array(w), self.a)
        a = self.a.copy()
        a[0, 0] = np.nan
        with self.assertRaises(ValueError):
            validate(self.w, a)

    def test_no_extrapolation_or_fake_low_frequency(self):
        with self.assertRaises(ValueError):
            compare(self.w, self.a, self.w, self.a, omega_min=0.001)
        with self.assertRaises(ValueError):
            compare(self.w, self.a, self.w, self.a, omega_min=0.2)
        with self.assertRaises(ValueError):
            compare(self.w, self.a, self.w+2, self.a)


if __name__ == "__main__":
    unittest.main()
