import json
import pathlib
import tempfile
import unittest


from oml_mcp.profiles import ProfileError, load_profile


class CompatibilityProfileTest(unittest.TestCase):
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

    def test_profile_validation_rejects_an_incomplete_component(self):
        profile = load_profile()
        del profile["components"]["pyatb"]["revision"]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "bad-profile.json"
            path.write_text(json.dumps(profile), encoding="utf-8")

            with self.assertRaisesRegex(ProfileError, "pyatb.*revision"):
                load_profile(path)


if __name__ == "__main__":
    unittest.main()
