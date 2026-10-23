import json
import pathlib
import tempfile
import unittest

from oml_mcp.parameter_knowledge import (
    KNOWLEDGE_SCHEMA,
    ParameterKnowledgeError,
    build_index,
    load_entries,
    lookup,
    parameter_names,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _minimal_parameter() -> dict:
    return {
        "owner": "abacus",
        "stage": "both",
        "default": 1,
        "default_origin": "oml",
        "meaning": "test parameter",
    }


class ParameterKnowledgeTest(unittest.TestCase):
    def test_all_packaged_entries_load_and_validate(self):
        entries = load_entries()
        self.assertGreaterEqual(len(entries), 15)
        ids = [entry["id"] for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))

    def test_index_resolves_every_required_parameter(self):
        names = parameter_names()
        required = (
            "exx_pca_threshold",
            "shrink_abfs_pca_thr",
            "out_librpa_3d_coulomb_method",
            "out_librpa_3d_direct_ecut",
            "out_librpa_2d_coulomb_method",
            "out_librpa_2d_direct_ecut",
            "out_librpa_2d_direct_kz_order",
            "out_librpa_2d_direct_gamma_order",
            "exx_ewald_dimension",
            "exx_ewald_lambda",
            "use_fullcoul_exx",
            "use_fullcoul_wc",
            "libri_chi0_threshold_C",
            "libri_chi0_threshold_G",
            "libri_exx_threshold_V",
            "libri_exx_threshold_C",
            "libri_exx_threshold_D",
            "libri_g0w0_threshold_C",
            "libri_g0w0_threshold_G",
            "libri_g0w0_threshold_Wc",
            "ecutwfc",
            "nbands",
        )
        for name in required:
            with self.subTest(name=name):
                self.assertIn(name, names)
                record = lookup(name)
                self.assertTrue(record["entry_id"])
                self.assertTrue(record["sources"])
                self.assertTrue(record["parameter"]["meaning"])

    def test_locked_oml_defaults(self):
        self.assertIs(lookup("use_fullcoul_exx")["parameter"]["default"], True)
        self.assertEqual(lookup("use_fullcoul_exx")["parameter"]["default_origin"], "oml")
        self.assertIs(lookup("use_fullcoul_wc")["parameter"]["default"], False)

        stage_defaults = lookup("exx_pca_threshold")["parameter"]["stage_defaults"]
        self.assertEqual(stage_defaults["abfs_generation"]["value"], 1e-4)
        self.assertEqual(stage_defaults["production"]["value"], 10.0)

        libri_expected = {
            "libri_chi0_threshold_C": 1e-4,
            "libri_chi0_threshold_G": 1e-5,
            "libri_exx_threshold_V": 1e-1,
            "libri_exx_threshold_C": 1e-4,
            "libri_exx_threshold_D": 1e-4,
            "libri_g0w0_threshold_C": 1e-5,
            "libri_g0w0_threshold_G": 1e-5,
            "libri_g0w0_threshold_Wc": 1e-6,
        }
        for name, value in libri_expected.items():
            with self.subTest(name=name):
                self.assertEqual(lookup(name)["parameter"]["default"], value)

        self.assertEqual(lookup("ecutwfc")["parameter"]["default"], 100.0)
        self.assertEqual(lookup("exx_ewald_dimension")["parameter"]["default"], 3)
        self.assertEqual(lookup("exx_ewald_lambda")["parameter"]["default"], 1.0)
        self.assertEqual(lookup("out_librpa_3d_coulomb_method")["parameter"]["default"], "ewald")
        self.assertEqual(lookup("out_librpa_2d_coulomb_method")["parameter"]["default"], "ewald")
        self.assertEqual(lookup("out_librpa_2d_direct_gamma_order")["parameter"]["default"], 8)

    def test_every_entry_cites_a_dated_source(self):
        for entry in load_entries():
            for source in entry["sources"]:
                with self.subTest(entry=entry["id"]):
                    self.assertTrue(source.get("kind"))
                    self.assertTrue(source.get("ref"))
                    self.assertRegex(str(source.get("accessed")), r"^\d{4}-\d{2}-\d{2}$")

    def test_duplicate_parameter_declaration_is_rejected(self):
        def entry(entry_id: str) -> dict:
            return {
                "id": entry_id,
                "title": entry_id,
                "parameters": {"shared_parameter": _minimal_parameter()},
                "sources": [{"kind": "test", "ref": "test", "accessed": "2026-10-23"}],
            }

        with self.assertRaises(ParameterKnowledgeError):
            build_index((entry("first"), entry("second")))

    def test_malformed_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "bad.json").write_text(
                json.dumps(
                    {
                        "schema_version": KNOWLEDGE_SCHEMA,
                        "id": "Invalid ID",
                        "title": "bad",
                        "parameters": {"x": _minimal_parameter()},
                        "sources": [{"kind": "test", "ref": "test", "accessed": "2026-10-23"}],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ParameterKnowledgeError):
                load_entries(root)

    def test_entry_without_sources_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "no-sources.json").write_text(
                json.dumps(
                    {
                        "schema_version": KNOWLEDGE_SCHEMA,
                        "id": "no-sources",
                        "title": "no sources",
                        "parameters": {"x": _minimal_parameter()},
                        "sources": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ParameterKnowledgeError):
                load_entries(root)

    def test_unknown_parameter_raises(self):
        with self.assertRaises(ParameterKnowledgeError):
            lookup("no_such_parameter")

    def test_entries_live_in_the_packaged_directory(self):
        packaged = ROOT / "oml_mcp" / "parameter_knowledge"
        self.assertTrue(list(packaged.glob("*.json")))


if __name__ == "__main__":
    unittest.main()
