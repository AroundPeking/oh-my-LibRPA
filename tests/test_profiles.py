import json
import pathlib
import tempfile
import unittest


from oml_mcp.profiles import ProfileError, list_profiles, load_profile


REPOSITORY_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "profiles" / "abacus-librpa-pyatb-2026-08.json"
PACKAGED_PROFILE = pathlib.Path(__file__).resolve().parents[1] / "oml_mcp" / "profiles" / "abacus-librpa-pyatb-2026-08.json"
V2_PROFILE_ID = "abacus-librpa-2026-08-30-v2"
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


class CompatibilityProfileTest(unittest.TestCase):
    def test_packaged_profile_matches_repository_audit_copy(self):
        repository = json.loads(REPOSITORY_PROFILE.read_text(encoding="utf-8"))
        packaged = json.loads(PACKAGED_PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(packaged, repository)

    def test_pinned_component_revisions_match_the_approved_baseline(self):
        profile = load_profile()

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
        profile = load_profile()
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
        profile = load_profile()
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
        profile = load_profile()

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
        profile = load_profile()

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
        profile = load_profile()
        del profile["components"]["pyatb"]["revision"]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "pyatb.*revision"):
                load_profile(path)

    def test_profile_validation_rejects_missing_frequency_grid_contract(self):
        profile = load_profile()
        del profile["contract"]["librpa"]["frequency_grids"]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "frequency_grids"):
                load_profile(path)

    def test_profile_validation_rejects_a_2d_block_for_another_librpa_revision(self):
        profile = load_profile()
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

    def test_unknown_profile_id_is_rejected(self):
        with self.assertRaisesRegex(ProfileError, "unknown profile_id"):
            load_profile(profile_id="missing-profile")


if __name__ == "__main__":
    unittest.main()
