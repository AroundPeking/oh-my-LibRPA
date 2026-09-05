import hashlib
import json
import pathlib
import tempfile
import unittest


from oml_mcp.profiles import (
    DEFAULT_PROFILE_ID,
    LEGACY_PROFILE_ID,
    V4_PROFILE_ID,
    V5_PROFILE_ID,
    V6_PROFILE_ID,
    ProfileError,
    list_profiles,
    load_profile,
)


REPOSITORY_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "profiles" / "abacus-librpa-pyatb-2026-08.json"
PACKAGED_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "oml_mcp" / "profiles" / "abacus-librpa-pyatb-2026-08.json"
V2_PROFILE_ID = "abacus-librpa-2026-08-30-v2"
V3_PROFILE_ID = "abacus-librpa-2026-08-30-v3"
V4_PROFILE_NAME = "abacus-librpa-pyatb-2026-09-v4.json"
V5_PROFILE_NAME = "abacus-librpa-pyatb-2026-09-v5.json"
V6_PROFILE_NAME = "abacus-librpa-pyatb-2026-09-v6.json"
V2_REPOSITORY_PROFILE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "profiles"
    / "abacus-librpa-pyatb-2026-08-v2.json"
)
V2_PACKAGED_PROFILE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "oml_mcp"
    / "profiles"
    / "abacus-librpa-pyatb-2026-08-v2.json"
)
V3_REPOSITORY_PROFILE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "profiles"
    / "abacus-librpa-pyatb-2026-08-v3.json"
)
V3_PACKAGED_PROFILE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "oml_mcp"
    / "profiles"
    / "abacus-librpa-pyatb-2026-08-v3.json"
)
V4_REPOSITORY_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "profiles" / V4_PROFILE_NAME
V4_PACKAGED_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "oml_mcp" / "profiles" / V4_PROFILE_NAME
V5_REPOSITORY_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "profiles" / V5_PROFILE_NAME
V5_PACKAGED_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "oml_mcp" / "profiles" / V5_PROFILE_NAME
V6_REPOSITORY_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "profiles" / V6_PROFILE_NAME
V6_PACKAGED_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "oml_mcp" / "profiles" / V6_PROFILE_NAME


class CompatibilityProfileTest(unittest.TestCase):
    def test_packaged_profile_matches_repository_audit_copy(self):
        repository = json.loads(REPOSITORY_PROFILE.read_text(encoding="utf-8"))
        packaged = json.loads(PACKAGED_PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(packaged, repository)

    def test_pinned_component_revisions_match_the_approved_baseline(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)

        self.assertEqual(
            profile["components"]["abacus"]["revision"],
            "3efad9ed5ca066aee1d1b2214e43f92a2d2a567e",
        )
        self.assertEqual(
            profile["components"]["librpa"]["revision"],
            "dd169fa11fa920d580d4f39dc11e218a7f17f7b5",
        )
        self.assertEqual(
            profile["components"]["pyatb"]["revision"],
            "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
        )

    def test_reader_v1_is_explicit_in_the_production_contract(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)
        abacus = profile["contract"]["abacus"]
        librpa = profile["contract"]["librpa"]

        self.assertEqual(abacus["source_default"]["out_librpa_reader_version"], 0)
        self.assertEqual(abacus["production"]["out_librpa_reader_version"], 1)
        self.assertEqual(librpa["source_default"]["version_coul_reader"], -1)
        self.assertEqual(librpa["source_default"]["version_lri_reader"], -1)
        self.assertEqual(librpa["production"]["version_coul_reader"], 1)
        self.assertEqual(librpa["production"]["version_lri_reader"], 1)
        self.assertEqual(librpa["production"]["prefix_eigvecs_scf"], "KS_eigenvector")
        self.assertEqual(librpa["production"]["fn_eigocc_scf"], "band_out")
        self.assertEqual(librpa["production"]["fn_vxc_scf"], "vxc_out")

    def test_librpa_070_uses_canonical_symmetry_keys(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)
        librpa = profile["contract"]["librpa"]

        self.assertEqual(
            librpa["canonical_symmetry_keys"],
            ["use_symmetry_exx", "use_symmetry_gw", "use_symmetry_rpa"],
        )
        self.assertEqual(
            librpa["unsupported_oml_keys"]["use_input_exx_symmetry"],
            "use_symmetry_exx",
        )
        self.assertEqual(
            librpa["unsupported_oml_keys"]["use_input_gw_symmetry"],
            "use_symmetry_gw",
        )
        self.assertEqual(
            librpa["frequency_grids"]["minimax_nfreq_supported"],
            list(range(6, 35, 2)),
        )
        self.assertEqual(librpa["frequency_grids"]["default_nfreq"], 6)
        self.assertEqual(librpa["frequency_grids"]["production_types"], ["minimax"])
        self.assertEqual(
            librpa["frequency_grids"]["recognized_types"],
            ["GL", "split-GL", "GC-I", "GL-II", "minimax", "evenspaced", "evenspaced_tf"],
        )

    def test_librpa_070_blocks_strict_2d_until_a_corrected_profile_is_pinned(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)

        self.assertEqual(profile["capabilities"]["periodic_3d_gw"]["status"], "ENABLED")
        blocked = profile["capabilities"]["strict_2d_gw"]
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(blocked["reason_code"], "LIBRPA_070_STRICT_2D_INVALID")
        self.assertEqual(blocked["component"], "librpa")
        self.assertEqual(
            blocked["component_revision"],
            profile["components"]["librpa"]["revision"],
        )
        self.assertGreaterEqual(len(blocked["enablement_requires"]), 4)

    def test_deprecated_task_and_binary_markers_are_recorded(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)

        self.assertEqual(
            profile["contract"]["librpa"]["deprecated_values"]["task"]["g0w0_band"],
            "g0w0",
        )
        self.assertEqual(
            profile["contract"]["pyatb_adapter"]["eigenvector_v1"],
            {"marker": -12345679, "kind": 28},
        )
        self.assertEqual(
            profile["contract"]["pyatb_adapter"]["velocity_v1"],
            {"marker": -12345680, "kind": 29, "nalpha": 3},
        )
        self.assertEqual(
            profile["contract"]["pyatb_adapter"]["location"],
            "input_dir/pyatb_librpa_df",
        )
        self.assertEqual(
            profile["contract"]["pyatb_adapter"]["state_coverage"],
            "pyatb_nstates_equal_abacus_nbands",
        )
        self.assertEqual(
            set(profile["contract"]["workflow_helpers"]),
            {
                "perform.sh",
                "get_diel.py",
                "output_librpa.py",
                "preprocess_abacus_for_librpa_band.py",
            },
        )
        self.assertTrue(
            all(
                len(digest) == 64
                for digest in profile["contract"]["workflow_helpers"].values()
            )
        )

    def test_profile_validation_rejects_an_incomplete_component(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)
        del profile["components"]["pyatb"]["revision"]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "pyatb.*revision"):
                load_profile(path)

    def test_profile_validation_rejects_missing_frequency_grid_contract(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)
        del profile["contract"]["librpa"]["frequency_grids"]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "frequency_grids"):
                load_profile(path)

    def test_profile_validation_rejects_a_2d_block_for_another_librpa_revision(self):
        profile = load_profile(profile_id=LEGACY_PROFILE_ID)
        profile["capabilities"]["strict_2d_gw"]["component_revision"] = "0" * 40

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "strict_2d_gw.*revision"):
                load_profile(path)

    def test_v2_profile_is_registered_and_packaged_once(self):
        self.assertIn(V2_PROFILE_ID, list_profiles())
        repository = json.loads(V2_REPOSITORY_PROFILE.read_text(encoding="utf-8"))
        packaged = json.loads(V2_PACKAGED_PROFILE.read_text(encoding="utf-8"))

        self.assertEqual(packaged, repository)
        self.assertEqual(load_profile(profile_id=V2_PROFILE_ID), repository)

    def test_v2_profile_pins_the_current_stack_as_testable(self):
        profile = load_profile(profile_id=V2_PROFILE_ID)

        self.assertEqual(profile["schema_version"], 2)
        self.assertEqual(
            profile["components"]["abacus"]["revision"],
            "641caa554b44c4db2743603e9c75c96379901d7c",
        )
        self.assertEqual(
            profile["components"]["librpa"]["revision"],
            "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
        )
        self.assertEqual(
            profile["components"]["pyatb"]["revision"],
            "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
        )
        self.assertEqual(
            profile["contract"]["librpa"]["frequency_grids"]["default"],
            "minimax",
        )
        self.assertEqual(
            set(profile["capabilities"]),
            {
                "periodic_3d_gw",
                "strict_2d_gw",
                "molecular_delta_st_rpa",
                "solid_delta_st_rpa",
            },
        )
        self.assertTrue(
            all(item["status"] == "TESTABLE" for item in profile["capabilities"].values())
        )
        self.assertEqual(profile["admission"]["levels"], ["L0", "L1", "L2", "L3", "L4"])

    def test_v2_profile_explicitly_selects_reader_v1_and_stru_out_symmetry(self):
        contract = load_profile(profile_id=V2_PROFILE_ID)["contract"]

        self.assertEqual(contract["abacus"]["source_default"]["out_librpa_reader_version"], 0)
        self.assertEqual(contract["abacus"]["production"]["out_librpa_reader_version"], 1)
        self.assertEqual(contract["librpa"]["source_default"]["version_coul_reader"], -1)
        self.assertEqual(contract["librpa"]["source_default"]["version_lri_reader"], -1)
        self.assertEqual(contract["librpa"]["production"]["version_coul_reader"], 1)
        self.assertEqual(contract["librpa"]["production"]["version_lri_reader"], 1)
        self.assertEqual(contract["symmetry"]["source"], "stru_out")
        self.assertEqual(contract["symmetry"]["rotation_reconstruction"], "librpa")
        self.assertEqual(contract["symmetry"]["copy_legacy_sidecars"], [])
        self.assertNotIn("sternheimer_rpa", contract["librpa"])
        self.assertNotIn("response_coulomb_prefix", contract["abacus"]["sternheimer"])

    def test_v3_profile_adds_the_definition_matched_sternheimer_handoff(self):
        self.assertIn(V3_PROFILE_ID, list_profiles())
        repository = json.loads(V3_REPOSITORY_PROFILE.read_text(encoding="utf-8"))
        packaged = json.loads(V3_PACKAGED_PROFILE.read_text(encoding="utf-8"))
        contract = load_profile(profile_id=V3_PROFILE_ID)["contract"]

        self.assertEqual(packaged, repository)
        self.assertEqual(
            repository["components"]["abacus"]["revision"],
            "81ff5f33995e7a545c2b9cb4f1a74490a74ecb4a",
        )
        self.assertEqual(
            contract["abacus"]["sternheimer"]["response_coulomb_prefix"],
            "v1_sternheimer_coulomb_iq_",
        )
        self.assertEqual(
            contract["librpa"]["sternheimer_rpa"]["prefix_coul_full"],
            "v1_sternheimer_coulomb_iq_",
        )
        self.assertEqual(
            contract["librpa"]["sternheimer_rpa"]["ordinary_reader_coulomb_role"],
            "diagnostic_only",
        )

    def test_v4_current_stack_remains_registered_and_packaged(self):
        self.assertIn(LEGACY_PROFILE_ID, list_profiles())
        self.assertIn(V4_PROFILE_ID, list_profiles())
        repository = json.loads(V4_REPOSITORY_PROFILE.read_text(encoding="utf-8"))
        packaged = json.loads(V4_PACKAGED_PROFILE.read_text(encoding="utf-8"))
        profile = load_profile(profile_id=V4_PROFILE_ID)

        self.assertEqual(packaged, repository)
        self.assertEqual(profile, repository)
        self.assertEqual(profile["profile_id"], V4_PROFILE_ID)
        self.assertEqual(
            profile["components"]["abacus"]["revision"],
            "1648a8a344427ae1b6394912bf677c4a20e053f2",
        )
        self.assertEqual(
            profile["components"]["librpa"]["revision"],
            "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
        )
        self.assertEqual(
            profile["components"]["pyatb"]["revision"],
            "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
        )

    def test_v5_current_stack_remains_registered_and_packaged(self):
        self.assertIn(V5_PROFILE_ID, list_profiles())
        repository = json.loads(V5_REPOSITORY_PROFILE.read_text(encoding="utf-8"))
        packaged = json.loads(V5_PACKAGED_PROFILE.read_text(encoding="utf-8"))
        profile = load_profile(profile_id=V5_PROFILE_ID)

        self.assertEqual(packaged, repository)
        self.assertEqual(profile, repository)
        self.assertEqual(profile["profile_id"], V5_PROFILE_ID)
        baseline = profile["components"]["librpa"]
        self.assertEqual(
            baseline["upstream_baseline_tag_object"],
            "11fbfbda9d5eccf02480f9344aa9f4abe7be01fc",
        )
        self.assertEqual(
            baseline["upstream_baseline_revision"],
            "dd169fa11fa920d580d4f39dc11e218a7f17f7b5",
        )
        contract = profile["contract"]["periodic_3d_gw"]
        self.assertEqual(contract["screening_kgrid_status"], "PASS")
        self.assertEqual(
            contract["accepted_screening_kgrid_pair"],
            [[12, 12, 12], [14, 14, 14]],
        )
        route = profile["capabilities"]["periodic_3d_gw"]
        self.assertEqual(route["status"], "EXPERIMENTAL")
        self.assertEqual(route["admission_level"], "L3")

    def test_v6_current_stack_is_registered_packaged_and_default(self):
        self.assertEqual(DEFAULT_PROFILE_ID, V6_PROFILE_ID)
        self.assertIn(V6_PROFILE_ID, list_profiles())
        repository = json.loads(V6_REPOSITORY_PROFILE.read_text(encoding="utf-8"))
        packaged = json.loads(V6_PACKAGED_PROFILE.read_text(encoding="utf-8"))
        profile = load_profile()

        self.assertEqual(packaged, repository)
        self.assertEqual(profile, repository)
        self.assertEqual(profile["profile_id"], V6_PROFILE_ID)
        contract = profile["contract"]["periodic_3d_gw"]
        self.assertEqual(contract["symmetry_fullq_status"], "PASS")
        self.assertEqual(contract["symmetry_fullq_tolerance_ev"], 0.0001)
        self.assertEqual(
            contract["symmetry_fullq_scope"],
            {
                "material": "bulk BN",
                "screening_kgrid": [4, 4, 4],
                "nbands": 26,
                "basis_dimension": 26,
                "nfreq": 24,
                "tfgrids_type": "minimax",
                "n_params_anacon": 6,
                "option_qpe_solver": 0,
                "use_shrink_abfs": True,
                "headwing": False,
                "reader_format": "v1",
            },
        )
        evidence = contract["symmetry_fullq_evidence"]
        self.assertEqual(
            evidence,
            {
                "benchmark_id": "fisherd-bn-k444-symmetry-fullq-20260906",
                "comparison_sha256": "472582f1dcc359c9d1177e3f161f7405247998a4baac781b35b1312604d95815",
            },
        )
        evidence_path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "benchmarks"
            / "live"
            / "fisherd-periodic-3d-gw-symmetry-fullq-2026-09-06.json"
        )
        self.assertEqual(
            hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            evidence["comparison_sha256"],
        )
        route = profile["capabilities"]["periodic_3d_gw"]
        self.assertEqual(route["status"], "EXPERIMENTAL")
        self.assertEqual(route["admission_level"], "L3")

    def test_v4_records_only_the_accepted_periodic_gw_frequency_contract(self):
        profile = load_profile(profile_id=V4_PROFILE_ID)
        route = profile["capabilities"]["periodic_3d_gw"]
        contract = profile["contract"]["periodic_3d_gw"]

        self.assertEqual(route["status"], "EXPERIMENTAL")
        self.assertEqual(route["admission_level"], "L3")
        self.assertEqual(
            contract["analytic_continuation"],
            {
                "tfgrids_type": "minimax",
                "n_params_anacon": 6,
                "option_qpe_solver": 0,
                "use_qpe_adaptive_damp": False,
            },
        )
        self.assertEqual(contract["accepted_frequency_pair"], [24, 32])
        self.assertEqual(contract["low_energy_window"], "VBM-3_through_CBM+3")
        self.assertEqual(contract["max_state_delta_ev"], 0.05)
        self.assertEqual(contract["high_unoccupied_policy"], "report_separately")
        self.assertEqual(contract["screening_kgrid_status"], "FAIL")

    def test_v4_validation_rejects_drift_in_the_periodic_gw_continuation_contract(self):
        profile = load_profile(profile_id=V4_PROFILE_ID)
        profile["contract"]["periodic_3d_gw"]["analytic_continuation"][
            "n_params_anacon"
        ] = -1

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "periodic 3D GW continuation"):
                load_profile(path)

    def test_v5_validation_rejects_screening_pair_drift(self):
        profile = load_profile(profile_id=V5_PROFILE_ID)
        profile["contract"]["periodic_3d_gw"]["accepted_screening_kgrid_pair"] = [
            [10, 10, 10],
            [12, 12, 12],
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "screening-grid acceptance"):
                load_profile(path)

    def test_v6_validation_rejects_symmetry_fullq_evidence_drift(self):
        profile = load_profile(profile_id=V6_PROFILE_ID)
        profile["contract"]["periodic_3d_gw"]["symmetry_fullq_evidence"][
            "comparison_sha256"
        ] = "0" * 64

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "symmetry/full-q acceptance"):
                load_profile(path)

    def test_unknown_profile_id_is_rejected(self):
        with self.assertRaisesRegex(ProfileError, "unknown profile_id"):
            load_profile(profile_id="missing-profile")


if __name__ == "__main__":
    unittest.main()
