import json
import pathlib
import tempfile
import unittest


from oml_mcp.scientific_registry import (
    ScientificRegistryError,
    load_benchmark,
    load_convergence_bundle,
)


class ScientificRegistryTest(unittest.TestCase):
    def test_packaged_bn_policy_has_approved_thresholds_but_no_reference(self):
        policy = load_benchmark("bn-reader-v1-3d-v1")

        self.assertEqual(policy["benchmark_id"], "bn-reader-v1-3d-v1")
        self.assertEqual(policy["regression_tolerance_ev"], 0.001)
        self.assertEqual(policy["convergence_tolerance_ev"], 0.05)
        self.assertEqual(policy["state_window"], {"below_vbm": 3, "above_cbm": 3})
        self.assertEqual(
            policy["required_axes"],
            ["nfreq", "empty_states", "screening_kgrid"],
        )
        self.assertIsNone(policy["reference"])
        self.assertEqual(policy["reference_status"], "NOT_AVAILABLE")
        self.assertTrue(policy["require_positive_gw_gap"])

    def test_registry_rejects_paths_and_unknown_identifiers(self):
        for identifier in ("../bn", "/tmp/bn", "nested/bn", "BN with spaces"):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ScientificRegistryError) as raised:
                    load_benchmark(identifier)
                self.assertEqual(raised.exception.code, "REGISTRY_ID_INVALID")

        with self.assertRaises(ScientificRegistryError) as missing:
            load_benchmark("not-registered")
        self.assertEqual(missing.exception.code, "BENCHMARK_NOT_FOUND")

    def test_private_root_precedes_packaged_policy_and_must_validate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            packaged = load_benchmark("bn-reader-v1-3d-v1")
            private = {**packaged, "convergence_tolerance_ev": 0.04}
            (root / "bn-reader-v1-3d-v1.json").write_text(
                json.dumps(private), encoding="utf-8"
            )

            loaded = load_benchmark("bn-reader-v1-3d-v1", roots=(root,))
            private["required_axes"] = ["nfreq", "nfreq"]
            (root / "bn-reader-v1-3d-v1.json").write_text(
                json.dumps(private), encoding="utf-8"
            )
            with self.assertRaises(ScientificRegistryError) as invalid:
                load_benchmark("bn-reader-v1-3d-v1", roots=(root,))

        self.assertEqual(loaded["convergence_tolerance_ev"], 0.04)
        self.assertEqual(invalid.exception.code, "BENCHMARK_INVALID")

    def test_convergence_bundle_uses_registered_run_ids_not_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            bundle = {
                "schema_version": 1,
                "bundle_id": "bn-nfreq-v1",
                "benchmark_id": "bn-reader-v1-3d-v1",
                "axis": "nfreq",
                "run_ids": ["run-coarse", "run-fine"],
            }
            (root / "bn-nfreq-v1.json").write_text(json.dumps(bundle), encoding="utf-8")

            loaded = load_convergence_bundle("bn-nfreq-v1", roots=(root,))
            bundle["run_ids"] = ["/tmp/run", "run-fine"]
            (root / "bn-nfreq-v1.json").write_text(json.dumps(bundle), encoding="utf-8")
            with self.assertRaises(ScientificRegistryError) as invalid:
                load_convergence_bundle("bn-nfreq-v1", roots=(root,))

        self.assertEqual(loaded["axis"], "nfreq")
        self.assertEqual(loaded["run_ids"], ["run-coarse", "run-fine"])
        self.assertEqual(invalid.exception.code, "CONVERGENCE_BUNDLE_INVALID")


if __name__ == "__main__":
    unittest.main()
