import unittest

from oml_mcp.review import settings_review


DEFAULTS = {
    "nfreq": 16,
    "n_params_anacon": 16,
    "use_qpe_adaptive_damp": True,
    "libri_exx_threshold_V": 1e-2,
    "shrink_abfs_pca_thr": 1e-4,
    "scf_kgrid": [8, 8, 8],
    "use_fullcoul_exx": True,
}


class SettingsReviewTest(unittest.TestCase):
    def test_production_defaults_need_no_review(self):
        review = settings_review(DEFAULTS)
        self.assertFalse(review["needs_review"])
        self.assertEqual(review["deviations"], [])
        self.assertTrue(all(row["status"] == "default" for row in review["rows"]))

    def test_nfreq_above_default_is_flagged_with_its_cost(self):
        review = settings_review({**DEFAULTS, "nfreq": 24})
        self.assertTrue(review["needs_review"])
        deviation = review["deviations"][0]
        self.assertEqual(deviation["key"], "nfreq")
        self.assertIn("1.50x", deviation["note"])

    def test_loose_shrink_is_flagged(self):
        review = settings_review({**DEFAULTS, "shrink_abfs_pca_thr": 1e-1})
        self.assertEqual(review["deviations"][0]["key"], "shrink_abfs_pca_thr")

    def test_small_kgrid_is_flagged(self):
        review = settings_review({**DEFAULTS, "scf_kgrid": [4, 4, 4]})
        self.assertEqual(review["deviations"][0]["key"], "scf_kgrid")

    def test_cut_coulomb_is_flagged(self):
        review = settings_review({**DEFAULTS, "use_fullcoul_exx": False})
        self.assertEqual(review["deviations"][0]["key"], "use_fullcoul_exx")

    def test_continuation_deviations_are_flagged(self):
        for key, value in (
            ("n_params_anacon", 6),
            ("use_qpe_adaptive_damp", False),
            ("libri_exx_threshold_V", 1e-1),
        ):
            with self.subTest(key=key):
                review = settings_review({**DEFAULTS, key: value})
                self.assertTrue(review["needs_review"])
                self.assertEqual(review["deviations"][0]["key"], key)

    def test_missing_value_is_reported_but_is_not_a_deviation(self):
        review = settings_review({"nfreq": 16})
        statuses = {row["key"]: row["status"] for row in review["rows"]}
        self.assertEqual(statuses["use_fullcoul_exx"], "missing")
        self.assertFalse(review["needs_review"])

    def test_replay_mode_is_not_applicable(self):
        review = settings_review({**DEFAULTS, "nfreq": 24}, policy_mode="replay")
        self.assertFalse(review["applicable"])
        self.assertFalse(review["needs_review"])


if __name__ == "__main__":
    unittest.main()
