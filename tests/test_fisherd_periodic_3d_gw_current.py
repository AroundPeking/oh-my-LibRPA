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
            self.data["profile_id"],
            "abacus-librpa-2026-09-03-v4",
        )
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

    def test_current_k444_frequency_ladder_pins_continuation_and_passes_only_fine_pair(self):
        followup = self.data["current_scientific_followup"]
        self.assertEqual(followup["screening_kgrid"], [4, 4, 4])
        self.assertEqual(followup["irreducible_kpoints"], 8)
        self.assertEqual(followup["legacy_symmetry_sidecars_in_dataset"], [])
        self.assertEqual(
            followup["continuation_contract"],
            {
                "tfgrids_type": "minimax",
                "n_params_anacon": 6,
                "option_qpe_solver": 0,
                "use_qpe_adaptive_damp": False,
            },
        )

        ladder = followup["frequency_ladder"]
        self.assertEqual([item["nfreq"] for item in ladder], [16, 24, 32])
        self.assertEqual(ladder[0]["to_next_status"], "FAIL")
        self.assertEqual(ladder[1]["to_next_status"], "PASS")
        self.assertAlmostEqual(ladder[0]["to_next_max_window_change_ev"], 0.51179)
        self.assertAlmostEqual(ladder[1]["to_next_max_window_change_ev"], 0.04440)
        self.assertAlmostEqual(ladder[1]["to_next_gap_change_ev"], 0.00021)
        self.assertEqual(followup["frequency_axis"]["status"], "PASS")

    def test_continuation_and_coarse_kgrid_negative_controls_remain_failures(self):
        followup = self.data["current_scientific_followup"]
        controls = {
            item["control_id"]: item
            for item in followup["continuation_negative_controls"]
        }
        self.assertEqual(controls["all-points-self-consistent"]["status"], "FAIL")
        self.assertAlmostEqual(
            controls["all-points-self-consistent"]["max_window_change_ev"],
            0.35045,
        )
        self.assertEqual(controls["pade-12-self-consistent"]["status"], "FAIL")
        self.assertGreater(
            controls["pade-12-self-consistent"]["nonfinite_high_state_count"],
            0,
        )
        self.assertEqual(controls["all-points-perturbative"]["status"], "FAIL")

        kgrid = followup["screening_kgrid_axis"]
        self.assertEqual(kgrid["status"], "FAIL")
        self.assertAlmostEqual(kgrid["coarse_gap_ev"], -132.38050)
        self.assertAlmostEqual(kgrid["fine_gap_ev"], 6.27089)
        self.assertAlmostEqual(kgrid["max_window_change_ev"], 139.78139)
        self.assertEqual(kgrid["worst_state"]["band"], 5)

        high = followup["high_unoccupied_report"]
        self.assertFalse(high["part_of_low_energy_gate"])
        self.assertAlmostEqual(high["max_abs_change_ev"], 1.44653)

    def test_current_screening_grid_ladder_preserves_failures_and_accepts_fine_pair(self):
        campaign = self.data["current_scientific_followup"][
            "screening_kgrid_campaign"
        ]

        self.assertEqual(
            campaign["harness_commit"],
            "814169d54941170f105c55fe9c5601bc8653dfe4",
        )
        self.assertEqual(
            [item["grid"] for item in campaign["meshes"]],
            [
                [4, 4, 4],
                [6, 6, 6],
                [8, 8, 8],
                [10, 10, 10],
                [12, 12, 12],
                [14, 14, 14],
            ],
        )
        self.assertEqual(
            [item["irreducible_kpoints"] for item in campaign["meshes"]],
            [8, 16, 29, 47, 72, 104],
        )
        self.assertTrue(
            all(item["application_exit_code"] == 0 for item in campaign["meshes"])
        )
        self.assertTrue(
            all(item["qpe_failure_count"] == 0 for item in campaign["meshes"])
        )

        comparisons = campaign["adjacent_comparisons"]
        self.assertEqual(
            [(item["coarse_grid"][0], item["fine_grid"][0]) for item in comparisons],
            [(4, 6), (6, 8), (8, 10), (10, 12), (12, 14)],
        )
        self.assertEqual(
            [item["status"] for item in comparisons],
            ["FAIL", "FAIL", "FAIL", "FAIL", "PASS"],
        )
        self.assertAlmostEqual(comparisons[-1]["max_window_change_ev"], 0.03279)
        self.assertAlmostEqual(comparisons[-1]["gap_change_ev"], 0.02590)
        self.assertEqual(
            comparisons[-1]["worst_state"],
            {"spin": 1, "kpoint": [0.25, 0.0, 0.25], "band": 1},
        )

        latest = campaign["meshes"][-1]
        self.assertAlmostEqual(latest["gap_ev"], 5.86474)
        self.assertEqual(latest["reader_v1_coulomb_file_pairs"], 104)
        self.assertEqual(
            latest["validation_counts"],
            {"PASS": 33, "WARN": 0, "FAIL": 0, "SKIP": 3},
        )
        self.assertEqual(
            latest["scientific_result_sha256"],
            "fc02cf21ee12736dbd840a33d76a8e63fb3c5db2b405aa213e53082a822b74e4",
        )

        provenance = campaign["screening_grid_provenance_gate"]
        self.assertEqual(provenance["status"], "PASS")
        self.assertEqual(provenance["gate_id"], "dataset.screening_grid")
        self.assertFalse(provenance["numerical_outputs_modified"])
        self.assertEqual(campaign["current_endpoint"], [14, 14, 14])
        self.assertEqual(campaign["accepted_pair"], [[12, 12, 12], [14, 14, 14]])
        self.assertEqual(campaign["status"], "PASS")
        incidents = campaign["preserved_prelaunch_incidents"]
        self.assertEqual(len(incidents), 3)
        self.assertIn("without rerun", incidents[0]["resolution"])
        self.assertIn("vxc_out.dat", incidents[1]["symptom"])
        self.assertIn("pgrep -x", incidents[2]["resolution"])
        self.assertEqual(self.data["status"]["current_screening_kgrid_axis"], "PASS")
        self.assertEqual(self.data["status"]["scientific_convergence"], "NOT_EVALUATED")

    def test_current_symmetry_fullq_control_is_linked_without_scientific_promotion(self):
        control = self.data["current_scientific_followup"][
            "symmetry_fullq_control"
        ]

        self.assertEqual(
            control["benchmark_id"],
            "fisherd-bn-k444-symmetry-fullq-20260906",
        )
        self.assertEqual(control["profile_id"], "abacus-librpa-2026-09-06-v6")
        self.assertEqual(control["qpoint_pair"], [8, 64])
        self.assertEqual(control["low_energy_max_change_ev"], 0.0)
        self.assertEqual(control["complete_basis_max_change_ev"], 0.00001)
        self.assertEqual(control["status"], "PASS_REFERENCE_BOUNDED")
        self.assertEqual(
            self.data["status"]["current_symmetry_fullq_control"],
            "PASS_REFERENCE_BOUNDED",
        )
        self.assertEqual(self.data["status"]["scientific_convergence"], "NOT_EVALUATED")

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
            "0.04440 eV",
            "139.78139 eV",
            "0.06091 eV",
            "10x10x10 -> 12x12x12",
            "0.03279 eV",
            "12x12x12 -> 14x14x14",
            "n_params_anacon = 6",
        ):
            self.assertIn(phrase, report)
        self.assertIn("PARTIAL_REFERENCE", matrix)
        self.assertIn("BLOCKED_DEGENERATE_GAUGE_MISMATCH", matrix)
        self.assertIn("10x10x10 -> 12x12x12", matrix)
        self.assertIn("0.06091 eV", matrix)
        self.assertIn("12x12x12 -> 14x14x14", matrix)
        self.assertIn("0.03279 eV", matrix)
        self.assertIn("abacus-librpa-2026-09-06-v5", matrix)
        self.assertIn("abacus-librpa-2026-09-06-v6", matrix)
        self.assertIn("degenerate gauge", route_guide)
        self.assertIn("must not promote", route_guide)
        self.assertIn("n_params_anacon = 6", route_guide)
        self.assertIn("Padé", route_guide)


if __name__ == "__main__":
    unittest.main()
