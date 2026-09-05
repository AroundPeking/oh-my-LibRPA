import json
import pathlib
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = (
    REPOSITORY
    / "benchmarks"
    / "live"
    / "fisherd-periodic-3d-gw-symmetry-fullq-2026-09-06.json"
)


class FisherdPeriodic3dGwSymmetryTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_stack_and_single_axis_definition_are_frozen(self):
        self.assertEqual(self.data["schema"], "oml.periodic-gw-symmetry-fullq.v1")
        self.assertEqual(self.data["base_profile_id"], "abacus-librpa-2026-09-06-v5")
        self.assertEqual(self.data["promoted_profile_id"], "abacus-librpa-2026-09-06-v6")
        self.assertEqual(
            self.data["software"]["revisions"],
            {
                "abacus": "1648a8a344427ae1b6394912bf677c4a20e053f2",
                "librpa": "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
                "pyatb": "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
            },
        )
        fields = [
            item["field"] for item in self.data["definition_comparison"]["differences"]
        ]
        self.assertEqual(
            fields,
            [
                "abacus.scf_symmetry",
                "librpa.use_symmetry_exx",
                "librpa.use_symmetry_gw",
                "route",
                "symmetry",
            ],
        )
        self.assertEqual(self.data["definition_comparison"]["status"], "PASS")

    def test_both_immutable_runs_and_all_stages_pass(self):
        symmetry = self.data["runs"]["symmetry"]
        full_q = self.data["runs"]["full_q"]
        self.assertEqual(symmetry["irreducible_qpoints"], 8)
        self.assertEqual(full_q["irreducible_qpoints"], 64)
        self.assertEqual(symmetry["full_grid_qpoints"], 64)
        self.assertEqual(full_q["full_grid_qpoints"], 64)
        self.assertEqual(symmetry["legacy_symmetry_sidecars"], [])
        self.assertEqual(full_q["legacy_symmetry_sidecars"], [])
        for run in (symmetry, full_q):
            self.assertEqual(
                [stage["stage"] for stage in run["stages"]],
                ["scf", "nscf", "preprocess", "librpa"],
            )
            self.assertTrue(all(stage["status"] == "PASSED" for stage in run["stages"]))
            self.assertEqual(run["input_validation_counts"]["FAIL"], 0)
            self.assertEqual(run["pre_librpa_validation_counts"]["FAIL"], 0)

    def test_mcp_low_energy_gate_and_complete_basis_audit_pass(self):
        report = self.data["mcp_scientific_report"]
        axis = report["symmetry_axis"]
        self.assertEqual(report["evaluator_version"], 9)
        self.assertEqual(report["report_id"], "science-11dcdb0dedee4b90ffee")
        self.assertEqual(
            report["report_sha256"],
            "35b2faa5dc874359c64ed2cf8300a9135a68eabf5ceb062fbc56a69f83e7a714",
        )
        self.assertEqual(axis["status"], "PASS")
        self.assertEqual(axis["tolerance_ev"], 0.0001)
        self.assertEqual(axis["state_count"], 24)
        self.assertEqual(axis["gap_change_ev"], 0.0)
        self.assertTrue(
            all(item["max_abs_change_ev"] == 0.0 for item in axis["quantities"].values())
        )
        self.assertEqual(report["scientific_status"], "NOT_EVALUATED")
        self.assertEqual(
            report["missing_axes"], ["nfreq", "empty_states", "screening_kgrid"]
        )

        complete = self.data["complete_basis_audit"]
        self.assertEqual(complete["state_count"], 78)
        self.assertTrue(complete["state_sets_equal"])
        self.assertEqual(complete["occupation_max_abs_change"], 0.0)
        self.assertLessEqual(
            max(
                item["max_abs_change_ev"]
                for item in complete["quantities"].values()
            ),
            complete["tolerance_ev"],
        )
        self.assertEqual(complete["status"], "PASS")

    def test_claim_boundary_forbids_overpromotion(self):
        boundary = self.data["claim_boundary"]
        self.assertTrue(boundary["bn_k444_no_headwing_symmetry_equivalence"])
        for unsupported in (
            "physical_reference",
            "material_transfer",
            "nao_convergence",
            "abfs_convergence",
            "strict_2d_gw",
        ):
            self.assertFalse(boundary[unsupported])
        self.assertEqual(self.data["status"], "PASS_REFERENCE_BOUNDED")
        self.assertFalse(self.data["automatic_promotion"])
        prepare_incident = self.data["preserved_setup_incidents"][1]
        self.assertEqual(prepare_incident["recorded_run_status"], "PREPARE_FAILED")
        self.assertFalse(prepare_incident["scheduler_job_created"])

    def test_documentation_preserves_the_same_boundary(self):
        report = (
            REPOSITORY
            / "docs"
            / "live-benchmarks"
            / "2026-09-03-fisherd-periodic-3d-gw-current.md"
        ).read_text(encoding="utf-8")
        matrix = (
            REPOSITORY / "docs" / "benchmarks" / "benchmark-matrix-v1.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "8-q symmetry -> 64-q full-q",
            "1e-5 eV",
            "PASS_REFERENCE_BOUNDED",
            "NOT_EVALUATED",
        ):
            self.assertIn(phrase, report)
        self.assertIn("8-q symmetry -> 64-q full-q", matrix)
        self.assertIn("abacus-librpa-2026-09-06-v6", matrix)


if __name__ == "__main__":
    unittest.main()
