import json
import pathlib
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = (
    REPOSITORY
    / "benchmarks"
    / "live"
    / "fisherd-periodic-3d-gw-current-2026-09-03.json"
)


class FisherdPeriodic3dGwCurrentTest(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    def test_exact_current_stack_and_v1_contract_are_recorded(self):
        self.assertEqual(
            self.data["pinned_revisions"],
            {
                "abacus": "1648a8a344427ae1b6394912bf677c4a20e053f2",
                "librpa": "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
                "pyatb": "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
            },
        )
        contract = self.data["contract"]
        self.assertEqual(contract["route"], "periodic_3d_gw")
        self.assertEqual(contract["reader_format"], "v1")
        self.assertEqual(contract["symmetry_source"], "stru_out")
        self.assertEqual(contract["copy_legacy_symmetry_sidecars"], [])
        self.assertEqual(contract["screening_kgrid"], [2, 2, 2])
        self.assertEqual(contract["nbands"], contract["basis_dimension"])
        self.assertEqual(contract["ecutwfc_rydberg"], 100)
        self.assertEqual(contract["exx_pca_threshold"], 1.0e-3)
        self.assertEqual(contract["shrink_abfs_pca_threshold"], 1.0e-1)
        identity = self.data["case"]["input_identity_sha256"]
        self.assertEqual(len(identity["pseudopotentials"]), 2)
        self.assertEqual(len(identity["orbitals"]), 2)

    def test_current_abacus_producer_and_band_handoff_pass(self):
        producer = self.data["producer"]
        self.assertEqual(producer["scf"]["exit_code"], 0)
        self.assertEqual(producer["nscf"]["exit_code"], 0)
        self.assertEqual(producer["preprocess"]["exit_code"], 0)
        self.assertEqual(producer["scf"]["symmetry_operations_in_stru_out"], 24)
        self.assertEqual(producer["nscf"]["symmetry_setting"], -1)
        self.assertEqual(producer["nscf"]["band_kpoints"], 3)
        self.assertEqual(producer["legacy_symmetry_sidecars_in_dataset"], [])

        ks = producer["v1_headers"]["ks"]
        self.assertEqual(ks["marker"], -12345679)
        self.assertEqual(ks["kind"], 28)
        self.assertEqual(ks["nstates"], 26)
        self.assertEqual(ks["nbasis"], 26)

        coulomb = producer["v1_headers"]["coulomb"]
        self.assertEqual(coulomb["marker"], -20129433)
        self.assertEqual(coulomb["qpoints"], 3)
        self.assertEqual(coulomb["naux"], 34)

    def test_librpa_frozen_input_and_current_parallel_controls_pass(self):
        consumer = self.data["consumer"]
        for layout in ("np1_omp48", "np4_omp1"):
            self.assertEqual(consumer[layout]["exit_code"], 0)
            self.assertTrue(consumer[layout]["finished_successfully"])

        comparisons = self.data["comparisons"]
        grid = comparisons["regular_grid_current_vs_official_reference"]
        self.assertEqual(grid["current_tables"], 8)
        self.assertEqual(grid["current_rows"], 208)
        self.assertTrue(grid["shape_ok"])
        self.assertLessEqual(grid["max_abs_diff_ev"], grid["threshold_ev"])

        parallel_grid = comparisons["regular_grid_np1_omp48_vs_np4_omp1"]
        self.assertEqual(parallel_grid["max_abs_diff_ev"], 0.0)
        for result in comparisons["band_np1_omp48_vs_np4_omp1"].values():
            self.assertTrue(result["shape_ok"])
            self.assertEqual(result["max_abs_diff_ev"], 0.0)

        for result in comparisons[
            "current_librpa_official_frozen_dataset_vs_reference"
        ].values():
            self.assertTrue(result["shape_ok"])
            self.assertEqual(result["max_abs_diff_ev"], 0.0)

    def test_historical_band_reference_is_not_used_as_a_false_end_to_end_gate(self):
        comparison = self.data["comparisons"][
            "current_end_to_end_vs_official_frozen_reference"
        ]
        self.assertEqual(comparison["KS_band_spin_1.dat"]["max_abs_diff_ev"], 0.0)
        self.assertGreater(
            comparison["EXX_band_spin_1.dat"]["max_abs_diff_ev"], 80.0
        )
        self.assertGreater(
            comparison["GW_band_spin_1.dat"]["max_abs_diff_ev"], 120.0
        )
        self.assertEqual(
            self.data["status"]["historical_end_to_end_band_reference"],
            "BLOCKED_DEGENERATE_GAUGE_MISMATCH",
        )

        symmetry = self.data["symmetry_diagnostics"]
        self.assertEqual(symmetry["current_degenerate_group_count"], 20)
        self.assertLessEqual(symmetry["current_exx_max_split_ev"], 1.0e-5)
        self.assertEqual(symmetry["current_gw_max_split_ev"], 0.0)

    def test_interface_pass_does_not_promote_scientific_acceptance(self):
        status = self.data["status"]
        self.assertEqual(status["source_build"], "PASS")
        self.assertEqual(status["producer"], "PASS")
        self.assertEqual(status["reader_v1_handoff"], "PASS")
        self.assertEqual(status["librpa_frozen_input_regression"], "PASS")
        self.assertEqual(status["current_parallel_reproducibility"], "PASS")
        self.assertEqual(status["scientific_convergence"], "NOT_EVALUATED")
        self.assertEqual(status["reference_promotion"], "BLOCKED")
        self.assertEqual(
            self.data["result"]["interface_regression"],
            "PASS_WITH_DEGENERATE_GAUGE_CAVEAT",
        )
        self.assertFalse(self.data["result"]["automatic_promotion"])

    def test_report_matrix_and_route_guide_preserve_the_same_boundary(self):
        report = (
            REPOSITORY
            / "docs"
            / "live-benchmarks"
            / "2026-09-03-fisherd-periodic-3d-gw-current.md"
        ).read_text(encoding="utf-8")
        matrix = (
            REPOSITORY / "docs" / "benchmarks" / "benchmark-matrix-v1.md"
        ).read_text(encoding="utf-8")
        route_guide = (
            REPOSITORY
            / "skills"
            / "oh-my-librpa"
            / "references"
            / "gw-route.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "PASS_WITH_DEGENERATE_GAUGE_CAVEAT",
            "BLOCKED_DEGENERATE_GAUGE_MISMATCH",
            "126.67942 eV",
            "NOT_EVALUATED",
        ):
            self.assertIn(phrase, report)
        self.assertIn("PARTIAL_REFERENCE", matrix)
        self.assertIn("BLOCKED_DEGENERATE_GAUGE_MISMATCH", matrix)
        self.assertIn("degenerate gauge", route_guide)
        self.assertIn("must not promote", route_guide)


if __name__ == "__main__":
    unittest.main()
