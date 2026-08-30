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
        self.assertEqual(
            self.data["host"]["remote_root"],
            "/home/ghj/oml-admission/20260831-v3",
        )
        self.assertTrue(self.data["builds"]["abacus"]["source_worktree_clean"])
        self.assertEqual(
            self.data["builds"]["abacus"]["source_checkout"],
            "/home/ghj/oml-admission/20260831-v3/src/abacus",
        )
        self.assertEqual(
            self.data["builds"]["abacus"]["executable_sha256"],
            "21e5ad5d8b073e36dc58408e8a37202c28340ea45107ed11b0a4ae25655f32fa",
        )
        self.assertEqual(self.data["builds"]["abacus"]["unit_tests_passed"], 27)

    def test_solid_handoff_removes_the_catastrophic_trace_log(self):
        solid = self.data["cases"]["solid_delta_st_rpa"]
        self.assertEqual(
            solid["producer"]["path"],
            "/home/ghj/oml-admission/20260831-v3/runs/si-q21-clean-v3",
        )
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
            8.902070315527028e-16,
        )
        self.assertAlmostEqual(
            solid["same_state"]["delta_trace_log"],
            -3.1041485714280883,
        )
        self.assertAlmostEqual(
            solid["librpa"]["trace_log"],
            -3.104148571418,
        )
        self.assertAlmostEqual(
            solid["librpa"]["weighted_ec_rpa_ha"],
            -0.007719384206762,
        )
        reproducibility = solid["clean_rebuild_comparison"]
        self.assertTrue(reproducibility["metric_byte_identical"])
        self.assertLess(reproducibility["response_relative_frobenius_difference"], 1.0e-10)
        self.assertLess(reproducibility["trace_log_absolute_difference"], 1.0e-10)
        self.assertLess(reproducibility["weighted_ec_rpa_absolute_difference_ha"], 1.0e-12)

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
        wrapper = molecule["producer"]["wrapper_observation"]
        self.assertEqual(wrapper["caller_exit_code"], 1)
        self.assertEqual(wrapper["producer_exit_code"], 0)
        self.assertEqual(wrapper["decision"], "PASS_PRODUCER_WRAPPER_MISMATCH")
        attempts = molecule["librpa"]["attempts"]
        self.assertEqual(attempts[0]["classification"], "PRE_EXECUTION_ENVIRONMENT_FAILURE")
        self.assertFalse(attempts[0]["physics_started"])
        self.assertEqual(attempts[1]["classification"], "PASS")
        reproducibility = molecule["clean_rebuild_comparison"]
        self.assertTrue(reproducibility["metric_byte_identical"])
        self.assertFalse(reproducibility["response_byte_identical"])
        self.assertLess(reproducibility["response_maximum_absolute_difference"], 2.0e-13)
        self.assertLess(reproducibility["response_relative_frobenius_difference"], 5.0e-14)
        self.assertEqual(reproducibility["ec_rpa_real_absolute_difference_ha"], 0.0)
        self.assertLess(reproducibility["ec_rpa_imaginary_absolute_ha"], 1.0e-20)

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
            "-3.104148571418",
            "-0.01100066029904 Ha",
            "NOT_EVALUATED",
            "complete q/frequency integration",
        ):
            self.assertIn(phrase, report)


if __name__ == "__main__":
    unittest.main()
