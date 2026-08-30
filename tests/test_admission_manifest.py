import json
import tempfile
import unittest
from pathlib import Path

from oml_mcp.admission_manifest import (
    AdmissionManifestError,
    default_admission_manifest_path,
    load_admission_manifest,
    validate_admission_manifest,
)


PROFILE_ID = "abacus-librpa-2026-08-30-v2"
ROUTES = {
    "periodic_3d_gw",
    "strict_2d_gw",
    "molecular_delta_st_rpa",
    "solid_delta_st_rpa",
}


class AdmissionManifestTest(unittest.TestCase):
    def test_packaged_fisherd_manifest_matches_v2_profile(self):
        manifest = load_admission_manifest()

        self.assertEqual(manifest["manifest_schema"], "oml.admission-manifest.v1")
        self.assertEqual(manifest["profile_id"], PROFILE_ID)
        self.assertEqual(manifest["host"]["alias"], "Fisherd-Server100.96.1.64")
        self.assertEqual(manifest["limits"]["compile_jobs_max"], 16)
        self.assertEqual(manifest["limits"]["execution_threads_max"], 48)
        self.assertEqual([level["level"] for level in manifest["levels"]], ["L0", "L1", "L2", "L3"])

        covered_routes = {
            case["route_id"]
            for level in manifest["levels"]
            for case in level["cases"]
            if "route_id" in case
        }
        self.assertEqual(covered_routes, ROUTES)

    def test_manifest_has_exact_source_revisions(self):
        manifest = load_admission_manifest()

        self.assertEqual(
            {name: component["revision"] for name, component in manifest["sources"].items()},
            {
                "abacus": "641caa554b44c4db2743603e9c75c96379901d7c",
                "librpa": "7e40c5bbf735a78aa15fa589ca2468fec2e2427b",
                "pyatb": "9fb9028c59b1dbaf9cf66965280961fc2225d9eb",
            },
        )

    def test_manifest_registers_required_source_tests(self):
        manifest = load_admission_manifest()
        source_tests = {
            case["case_id"]: set(case["targets"])
            for case in manifest["levels"][1]["cases"]
        }

        self.assertTrue(
            {
                "test_rpa_headwing",
                "test_strict_2d_coulomb_head_metadata",
                "test_sternheimer_rpa",
                "test_sternheimer_symmetry",
                "test_sternheimer_qsum",
            }.issubset(source_tests["librpa-source-contracts"])
        )
        self.assertTrue(
            {
                "MODULE_RI_librpa_2d_coulomb_head_test",
                "MODULE_RI_ewald_mpi_distribution_test_parallel",
                "MODULE_RI_sternheimer_delta_test",
                "MODULE_RI_sternheimer_periodic_solver_test",
            }.issubset(source_tests["abacus-source-contracts"])
        )

    def test_abacus_reuses_the_pinned_librpa_dependency_trees(self):
        manifest = load_admission_manifest()
        dependencies = manifest["builds"]["abacus"]["dependency_sources"]

        self.assertEqual(
            dependencies,
            {
                "libri": {
                    "component": "librpa",
                    "path": "thirdparty/LibRI",
                    "tree": "d67a9367dcc6c2b29f3833840da3dbacb1fb2b35",
                },
                "libcomm": {
                    "component": "librpa",
                    "path": "thirdparty/LibComm",
                    "tree": "323fc5cb988ffa9d8eea646872706e11f2e4810d",
                },
            },
        )

    def test_validation_rejects_abacus_dependency_tree_drift(self):
        manifest = load_admission_manifest()
        manifest["builds"]["abacus"]["dependency_sources"]["libri"]["tree"] = "0" * 40

        with self.assertRaisesRegex(AdmissionManifestError, "dependency_sources.libri.tree"):
            validate_admission_manifest(manifest)

    def test_validation_rejects_resource_drift(self):
        manifest = load_admission_manifest()
        manifest["limits"]["compile_jobs_max"] = 17

        with self.assertRaisesRegex(AdmissionManifestError, "compile_jobs_max"):
            validate_admission_manifest(manifest)

    def test_validation_rejects_revision_drift(self):
        manifest = load_admission_manifest()
        manifest["sources"]["librpa"]["revision"] = "0" * 40

        with self.assertRaisesRegex(AdmissionManifestError, "sources.librpa.revision"):
            validate_admission_manifest(manifest)

    def test_validation_rejects_missing_route(self):
        manifest = load_admission_manifest()
        for level in manifest["levels"]:
            level["cases"] = [
                case for case in level["cases"] if case.get("route_id") != "strict_2d_gw"
            ]

        with self.assertRaisesRegex(AdmissionManifestError, "route coverage"):
            validate_admission_manifest(manifest)

    def test_validation_rejects_non_v1_reader(self):
        manifest = load_admission_manifest()
        manifest["contract"]["reader_format"] = "legacy"

        with self.assertRaisesRegex(AdmissionManifestError, "reader_format"):
            validate_admission_manifest(manifest)

    def test_loads_an_explicit_manifest_path(self):
        manifest = load_admission_manifest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            loaded = load_admission_manifest(path)

        self.assertEqual(loaded, manifest)

    def test_repository_and_packaged_manifests_are_identical(self):
        packaged = default_admission_manifest_path()
        repository = Path(__file__).resolve().parents[1] / "admission" / packaged.name

        self.assertEqual(packaged.read_bytes(), repository.read_bytes())


if __name__ == "__main__":
    unittest.main()
