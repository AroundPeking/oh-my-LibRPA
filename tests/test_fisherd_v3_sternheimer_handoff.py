import json
import pathlib
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = (
    REPOSITORY
    / "benchmarks"
    / "live"
    / "fisherd-v3-sternheimer-handoff-2026-08-30.json"
)


class FisherdV3SternheimerHandoffTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_stack_and_contract_are_recorded(self):
        self.assertEqual(self.data["profile_id"], "abacus-librpa-2026-08-30-v3")
        self.assertEqual(
            self.data["pinned_revisions"],
            {
                "abacus": "81ff5f33995e7a545c2b9cb4f1a74490a74ecb4a",
                "librpa": "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
                "pyatb": "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
            },
        )
        self.assertEqual(
            self.data["contract"]["sternheimer_coulomb_prefix"],
            "v1_sternheimer_coulomb_iq_",
        )
        self.assertEqual(
            self.data["contract"]["ordinary_reader_coulomb_role"],
            "diagnostic_only",
        )
        self.assertEqual(self.data["builds"]["abacus"]["unit_tests_passed"], 27)

    def test_solid_handoff_removes_the_catastrophic_trace_log(self):
        solid = self.data["cases"]["solid_delta_st_rpa"]
        self.assertEqual(solid["status"]["producer"], "PASS")
        self.assertEqual(solid["status"]["handoff"], "PASS")
        self.assertEqual(solid["status"]["librpa"], "PASS")
        self.assertEqual(solid["producer"]["equations"], 62464)
        self.assertEqual(solid["producer"]["failed_equations"], 0)
        self.assertAlmostEqual(
            solid["metric"]["relative_difference_from_ordinary_reader"],
            0.8133250803797222,
        )
        self.assertLess(
            solid["metric"]["relative_difference_from_grid_diagnostic"],
            1.0e-15,
        )
        self.assertEqual(solid["metric"]["negative_eigenvalues"], 0)
        self.assertAlmostEqual(
            solid["same_state"]["component_reconstruction_relative_error"],
            9.090450336226364e-16,
        )
        self.assertAlmostEqual(
            solid["same_state"]["delta_trace_log"],
            -3.1041485714755943,
        )
        self.assertAlmostEqual(
            solid["librpa"]["trace_log"],
            -3.104148571459,
        )
        self.assertAlmostEqual(
            solid["librpa"]["weighted_ec_rpa_ha"],
            -0.007719384206866,
        )

    def test_molecular_handoff_is_finite_and_positive_metric(self):
        molecule = self.data["cases"]["molecular_delta_st_rpa"]
        self.assertEqual(molecule["status"]["producer"], "PASS")
        self.assertEqual(molecule["status"]["handoff"], "PASS")
        self.assertEqual(molecule["status"]["librpa"], "PASS")
        self.assertEqual(molecule["producer"]["equations"], 30)
        self.assertEqual(molecule["producer"]["failed_equations"], 0)
        self.assertEqual(molecule["metric"]["negative_eigenvalues"], 0)
        self.assertGreater(molecule["metric"]["eigenvalue_min"], 0.0)
        self.assertAlmostEqual(
            molecule["metric"]["relative_difference_from_ordinary_reader"],
            0.003701136514287809,
        )
        self.assertAlmostEqual(
            molecule["librpa"]["ec_rpa_ha"],
            -0.01100066029904,
        )

    def test_scientific_acceptance_is_not_overclaimed(self):
        for case in self.data["cases"].values():
            self.assertEqual(case["status"]["scientific"], "NOT_EVALUATED")
            self.assertEqual(case["status"]["promotion"], "BLOCKED")
        self.assertIn("complete q/frequency integration", self.data["remaining_gates"])
        self.assertIn("strict-2D route replay", self.data["remaining_gates"])

    def test_human_report_preserves_result_and_remaining_boundaries(self):
        report = (
            REPOSITORY
            / "docs"
            / "live-benchmarks"
            / "2026-08-30-fisherd-v3-sternheimer-handoff.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "81ff5f33995e7a545c2b9cb4f1a74490a74ecb4a",
            "v1_sternheimer_coulomb_iq_",
            "-3.104148571459",
            "-0.01100066029904 Ha",
            "NOT_EVALUATED",
            "complete q/frequency integration",
        ):
            self.assertIn(phrase, report)


if __name__ == "__main__":
    unittest.main()
