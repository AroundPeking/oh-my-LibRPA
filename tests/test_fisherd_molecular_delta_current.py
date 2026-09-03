import json
import pathlib
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = (
    REPOSITORY
    / "benchmarks"
    / "live"
    / "fisherd-molecular-delta-current-2026-09-03.json"
)


class FisherdMolecularDeltaCurrentTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_current_stack_build_and_focused_tests_are_recorded(self):
        self.assertEqual(
            self.data["pinned_revisions"],
            {
                "abacus": "1648a8a344427ae1b6394912bf677c4a20e053f2",
                "librpa": "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
                "pyatb": "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
            },
        )
        build = self.data["builds"]["abacus"]
        self.assertTrue(build["source_worktree_clean"])
        self.assertEqual(build["source_tree_oid"], "a03daee0a17479851e5f5a33baa25c8db6ff61c4")
        self.assertEqual(
            build["executable_sha256"],
            "7aba04e711e68bc654dc737ed5c1a330ddfe62a7ea2305c4d78b6edad5347b5a",
        )
        self.assertEqual(build["focused_tests_passed"], 7)
        self.assertEqual(build["focused_tests_total"], 7)

    def test_current_producer_passes_without_overstating_the_handoff(self):
        case = self.data["case"]
        producer = case["producer"]
        self.assertEqual(case["status"]["producer"], "PASS")
        self.assertEqual(producer["exit_code"], 0)
        self.assertEqual(producer["grid"], [50, 50, 50])
        self.assertEqual(producer["frequency_count"], 1)
        self.assertEqual(producer["fd_order"], 8)
        self.assertEqual(producer["virtual_source"], "ks_bands")
        self.assertEqual(producer["equations"], 30)
        self.assertEqual(producer["failed_equations"], 0)
        self.assertTrue(producer["all_converged"])
        self.assertLess(producer["max_solver_relative_residual"], 1.0e-6)
        self.assertEqual(producer["reader_format"], "v1")

    def test_missing_dedicated_metric_is_a_hard_handoff_block(self):
        case = self.data["case"]
        metric = case["metric_contract"]
        self.assertEqual(case["status"]["handoff"], "BLOCKED_MISSING_RESPONSE_COULOMB")
        self.assertFalse(metric["dedicated_response_metric_present"])
        self.assertTrue(metric["ordinary_reader_metric_present"])
        self.assertEqual(metric["ordinary_reader_role"], "diagnostic_only")
        self.assertEqual(
            metric["required_prefix"],
            "v1_sternheimer_coulomb_iq_",
        )
        self.assertEqual(
            metric["ordinary_reader_sha256"],
            metric["historical_ordinary_reader_sha256"],
        )
        self.assertAlmostEqual(
            metric["relative_frobenius_difference_from_validated_dedicated_metric"],
            0.0037011365142878075,
        )
        self.assertGreater(metric["maximum_absolute_difference"], 0.28)

    def test_ordinary_metric_run_is_diagnostic_not_a_false_pass(self):
        case = self.data["case"]
        diagnostic = case["ordinary_metric_diagnostic"]
        self.assertEqual(case["status"]["librpa_production"], "NOT_RUN_HANDOFF_BLOCKED")
        self.assertEqual(diagnostic["classification"], "DIAGNOSTIC_ONLY")
        self.assertEqual(diagnostic["exit_code"], 0)
        self.assertTrue(diagnostic["finished_successfully"])
        self.assertAlmostEqual(diagnostic["ec_rpa_hartree"], -0.01109259015020)
        self.assertAlmostEqual(
            diagnostic["validated_dedicated_metric_ec_rpa_hartree"],
            -0.01100066029904,
        )
        self.assertAlmostEqual(diagnostic["absolute_energy_difference_hartree"], 0.00009192985116)
        self.assertAlmostEqual(diagnostic["absolute_energy_difference_kcal_mol"], 0.057686852552)

    def test_scientific_reference_and_promotion_remain_blocked(self):
        status = self.data["case"]["status"]
        self.assertEqual(status["scientific"], "NOT_EVALUATED")
        self.assertEqual(status["promotion"], "BLOCKED")
        self.assertEqual(self.data["result"]["compatibility"], "BLOCKED")
        self.assertFalse(self.data["result"]["automatic_promotion"])
        next_work = " ".join(self.data["next_required_work"])
        self.assertIn("restore the dedicated response Coulomb output", next_work)
        self.assertIn("molecule and atom absolute Ec", next_work)

    def test_report_matrix_and_active_skill_preserve_the_same_boundary(self):
        report = (
            REPOSITORY
            / "docs"
            / "live-benchmarks"
            / "2026-09-03-fisherd-molecular-delta-current.md"
        ).read_text(encoding="utf-8")
        matrix = (
            REPOSITORY / "docs" / "benchmarks" / "benchmark-matrix-v1.md"
        ).read_text(encoding="utf-8")
        route_guide = (
            REPOSITORY
            / "skills"
            / "oh-my-librpa"
            / "references"
            / "delta-st-route.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "1648a8a344427ae1b6394912bf677c4a20e053f2",
            "BLOCKED_MISSING_RESPONSE_COULOMB",
            "v1_sternheimer_coulomb_iq_",
            "-0.01109259015020 Ha",
            "NOT_EVALUATED",
        ):
            self.assertIn(phrase, report)
        self.assertIn("REFERENCE_PENDING", matrix)
        self.assertIn("BLOCKED_MISSING_RESPONSE_COULOMB", matrix)
        self.assertIn("1648a8a344427ae1b6394912bf677c4a20e053f2", route_guide)
        self.assertIn("must not substitute", route_guide)


if __name__ == "__main__":
    unittest.main()
