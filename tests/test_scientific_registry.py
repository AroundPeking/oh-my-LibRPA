import copy
import json
import pathlib
import tempfile
import unittest


from oml_mcp.scientific_evaluation import evaluate_regression
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

    def test_bn_v2_requires_symmetry_equivalence_without_claiming_a_reference(self):
        policy = load_benchmark("bn-reader-v1-3d-v2")

        self.assertEqual(
            policy["required_axes"],
            ["symmetry", "nfreq", "empty_states", "screening_kgrid"],
        )
        self.assertEqual(
            policy["axis_tolerances_ev"],
            {
                "symmetry": 0.0001,
                "nfreq": 0.05,
                "empty_states": 0.05,
                "screening_kgrid": 0.05,
            },
        )
        self.assertEqual(policy["reference_status"], "NOT_AVAILABLE")
        self.assertIsNone(policy["reference"])

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

    def test_convergence_bundle_accepts_materialized_run_id_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            bundle = {
                "schema_version": 1,
                "bundle_id": "bn-live-nfreq-v1",
                "benchmark_id": "bn-reader-v1-3d-v1",
                "axis": "nfreq",
                "run_ids": [
                    "run-20260813T075654Z-4b7c45dd32",
                    "run-20260813T075641Z-80efe676aa",
                ],
            }
            (root / "bn-live-nfreq-v1.json").write_text(
                json.dumps(bundle), encoding="utf-8"
            )

            loaded = load_convergence_bundle("bn-live-nfreq-v1", roots=(root,))

        self.assertEqual(loaded["run_ids"], bundle["run_ids"])


class LibRpaGroundedBenchmarkTest(unittest.TestCase):
    """The LibRPA regression family is the correct source of GW convergence references.

    ``bn-reader-v1-3d-sym-shrink-v1`` freezes a converged reference candidate from
    the OML production BN run, which is the converged version of the LibRPA
    ``g0w0_band_abacus_BN_sym_shrink_libri`` regression material. Unlike the
    material-class identities (SrTiO3/NiO/alpha-MnTe/WSe2) which freeze a single
    numeric gap without a convergence series, this benchmark carries a full
    KS/EXX/GW state window with a positive converged gap, so it can gate real
    convergence work without a false pass.
    """

    def test_packaged_librpa_grounded_policy_carries_a_real_reference(self):
        policy = load_benchmark("bn-reader-v1-3d-sym-shrink-v1")

        self.assertEqual(policy["benchmark_id"], "bn-reader-v1-3d-sym-shrink-v1")
        self.assertEqual(policy["reference_status"], "AVAILABLE")
        self.assertIsInstance(policy["reference"], dict)
        reference = policy["reference"]
        self.assertIn("definition", reference)
        self.assertIn("window", reference)
        self.assertEqual(reference["window"]["state_count"], 24)
        self.assertGreater(reference["window"]["fundamental_gw_gap_ev"], 0.0)
        self.assertEqual(
            reference["definition"]["abacus"]["nspin"], 1
        )
        self.assertTrue(policy["require_positive_gw_gap"])
        self.assertEqual(
            policy["required_axes"],
            ["symmetry", "nfreq", "empty_states", "screening_kgrid"],
        )

    def test_librpa_grounded_reference_self_match_passes(self):
        policy = load_benchmark("bn-reader-v1-3d-sym-shrink-v1")
        reference = policy["reference"]
        result = evaluate_regression(
            reference,
            reference,
            tolerance_ev=float(policy["regression_tolerance_ev"]),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["reason_code"], "WITHIN_TOLERANCE")
        self.assertEqual(result["state_count"], 24)

    def test_librpa_grounded_reference_rejects_definition_drift(self):
        policy = load_benchmark("bn-reader-v1-3d-sym-shrink-v1")
        reference = policy["reference"]
        drifted = copy.deepcopy(reference)
        drifted["definition"]["abacus"]["nbands"] = 30
        result = evaluate_regression(
            drifted,
            reference,
            tolerance_ev=float(policy["regression_tolerance_ev"]),
        )
        self.assertEqual(result["status"], "NOT_EVALUATED")
        self.assertEqual(result["reason_code"], "DEFINITION_MISMATCH")

    def test_librpa_grounded_reference_rejects_software_drift(self):
        policy = load_benchmark("bn-reader-v1-3d-sym-shrink-v1")
        reference = policy["reference"]
        drifted = copy.deepcopy(reference)
        drifted["definition"]["software"]["revisions"]["librpa"] = "0" * 40
        result = evaluate_regression(
            drifted,
            reference,
            tolerance_ev=float(policy["regression_tolerance_ev"]),
        )
        self.assertEqual(result["status"], "NOT_EVALUATED")
        self.assertEqual(result["reason_code"], "DEFINITION_MISMATCH")

    def test_librpa_grounded_reference_rejects_numeric_drift(self):
        policy = load_benchmark("bn-reader-v1-3d-sym-shrink-v1")
        reference = policy["reference"]
        drifted = copy.deepcopy(reference)
        for state in drifted["window"]["states"]:
            state["gw_ev"] = round(float(state["gw_ev"]) + 0.5, 5)
        result = evaluate_regression(
            drifted,
            reference,
            tolerance_ev=float(policy["regression_tolerance_ev"]),
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason_code"], "REGRESSION_TOLERANCE_EXCEEDED")

    def test_librpa_grounded_reference_rejects_state_set_mismatch(self):
        policy = load_benchmark("bn-reader-v1-3d-sym-shrink-v1")
        reference = policy["reference"]
        drifted = copy.deepcopy(reference)
        drifted["window"]["states"] = drifted["window"]["states"][:10]
        result = evaluate_regression(
            drifted,
            reference,
            tolerance_ev=float(policy["regression_tolerance_ev"]),
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason_code"], "STATE_SET_MISMATCH")


if __name__ == "__main__":
    unittest.main()
