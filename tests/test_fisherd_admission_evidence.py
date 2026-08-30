import json
import pathlib
import unittest

from oml_mcp.evals import evaluate_evidence, load_scorecard


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = (
    REPOSITORY / "benchmarks" / "live" / "fisherd-v2-admission-2026-08-30.json"
)


class FisherdAdmissionEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_stack_and_resource_provenance_are_recorded(self):
        self.assertEqual(self.data["profile_id"], "abacus-librpa-2026-08-30-v2")
        self.assertEqual(
            self.data["pinned_revisions"],
            {
                "abacus": "641caa554b44c4db2743603e9c75c96379901d7c",
                "librpa": "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
                "pyatb": "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
            },
        )
        self.assertEqual(self.data["limits"]["compile_jobs_max"], 16)
        self.assertEqual(self.data["limits"]["execution_threads_max"], 48)
        self.assertEqual(self.data["builds"]["abacus"]["production_target"], "PASS")
        self.assertEqual(self.data["builds"]["abacus"]["aggregate_test_build"], "WARN")

    def test_route_statuses_do_not_overclaim_scientific_acceptance(self):
        routes = {route["route_id"]: route for route in self.data["routes"]}
        self.assertEqual(
            set(routes),
            {
                "periodic_3d_gw",
                "strict_2d_gw",
                "molecular_delta_st_rpa",
                "solid_delta_st_rpa",
            },
        )
        for route in routes.values():
            self.assertEqual(route["profile_status"], "TESTABLE")
            self.assertEqual(route["promotion"], "BLOCKED")
            self.assertNotIn(route["profile_status"], {"EXPERIMENTAL", "ENABLED"})

        self.assertEqual(routes["periodic_3d_gw"]["levels"]["L2"], "PASS")
        self.assertEqual(routes["strict_2d_gw"]["levels"]["L3"], "NOT_EVALUATED")
        molecule = routes["molecular_delta_st_rpa"]
        self.assertEqual(molecule["levels"]["L3"], "PASS")
        self.assertEqual(molecule["process_status"], "PASS")
        self.assertEqual(molecule["numerical_status"], "PASS")
        self.assertEqual(molecule["scientific_status"], "NOT_EVALUATED")

        solid = routes["solid_delta_st_rpa"]
        self.assertEqual(solid["levels"]["L3"], "INCOMPLETE")
        self.assertEqual(solid["process_status"], "PASS")
        self.assertEqual(solid["numerical_status"], "WARN")
        self.assertEqual(solid["scientific_status"], "NOT_EVALUATED")
        self.assertEqual(solid["diagnostics"]["threshold_ab"], "NO_CHANGE")

    def test_embedded_v2_score_is_reproducible_and_incomplete(self):
        card = load_scorecard(REPOSITORY / "benchmarks" / "scorecard-v2.json")
        report = evaluate_evidence(self.data["scorecard_evidence"], scorecard=card)

        self.assertEqual(report, self.data["scorecard_result"])
        self.assertEqual(report["verdict"], "INCOMPLETE")
        self.assertIn("scientific_evaluation", report["not_evaluated"])
        self.assertIn("scientific_acceptance", report["not_evaluated"])


if __name__ == "__main__":
    unittest.main()
