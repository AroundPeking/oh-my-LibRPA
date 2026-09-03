import copy
import pathlib
import unittest


from oml_mcp.admission_manifest import load_admission_manifest
from oml_mcp.benchmark_suite import (
    evaluate_registered_route_benchmark_suite,
    evaluate_route_benchmark_suite,
    load_route_benchmark_suite,
)
from oml_mcp.evals import evaluate_evidence, load_scorecard
from oml_mcp.route_benchmark import (
    RouteBenchmarkError,
    evaluate_registered_route_benchmark,
    evaluate_route_benchmark,
    list_route_benchmarks,
    load_route_benchmark,
)
from oml_mcp.server import build_server


BENCHMARK_ID = "strict2d-sos-rpa-mos2-qavg-v1"
MANIFEST_ID = "df-dcu-strict2d-sos-rpa-2026-09-02-v1"
SUITE_ID = "strict2d-sos-rpa-regression-v1"


class RouteBenchmarkTest(unittest.TestCase):
    def test_strict2d_reference_benchmark_is_registered_and_packaged(self):
        self.assertIn(BENCHMARK_ID, list_route_benchmarks())
        benchmark = load_route_benchmark(BENCHMARK_ID)

        self.assertEqual(benchmark["route_id"], "strict_2d_sos_rpa")
        self.assertEqual(benchmark["material"]["formula"], "MoS2")
        self.assertEqual(benchmark["acceptance_model"], "reference_bounded_four_mesh")
        self.assertEqual(benchmark["required_meshes"], [8, 10, 12, 16])
        self.assertTrue(benchmark["claim_boundary"]["operational_k_mesh_convergence"])
        self.assertTrue(benchmark["claim_boundary"]["forbid_asymptotic_exponent_claim"])
        self.assertFalse(benchmark["claim_boundary"]["strict_2d_gw"])

        root = pathlib.Path(__file__).resolve().parents[1]
        repository = (root / "benchmarks" / "routes" / f"{BENCHMARK_ID}.json").read_bytes()
        packaged = (
            root / "oml_mcp" / "route_benchmarks" / f"{BENCHMARK_ID}.json"
        ).read_bytes()
        self.assertEqual(packaged, repository)

    def test_reference_identity_includes_structure_and_basis_hashes(self):
        benchmark = load_route_benchmark(BENCHMARK_ID)
        identity = benchmark["material"]["identity_sha256"]

        self.assertEqual(identity["STRU"], "c7f5413abc4c450f2c879df296fa4e5ed37d0e57a2547c824f80ea87254630b8")
        self.assertEqual(identity["INPUT"], "3ed451b73a9a24446bd947c2db298449161efdcc9afe236fdda38f9e070be386")
        self.assertEqual(len(identity["pseudopotentials"]), 2)
        self.assertEqual(len(identity["orbitals"]), 2)
        self.assertEqual(len(identity["auxiliary_bases"]), 2)
        self.assertEqual(
            set(benchmark["mesh_identity_sha256"]),
            {"8", "10", "12", "16"},
        )

    def test_registered_reference_passes_all_non_compensating_gates(self):
        result = evaluate_registered_route_benchmark(
            benchmark_id=BENCHMARK_ID,
            manifest_id=MANIFEST_ID,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["scientific_status"], "PASS")
        self.assertEqual(result["promotion_eligibility"], "ENABLED")
        self.assertTrue(all(gate["status"] == "PASS" for gate in result["gates"]))
        self.assertLessEqual(result["metrics"]["gamma_area_scaled_relative_span"], 1.0e-3)
        self.assertLessEqual(result["metrics"]["endpoint_total_delta_millihartree"], 8.0)
        self.assertLessEqual(result["metrics"]["finite_q_control_max_abs_delta_hartree"], 1.0e-9)
        self.assertFalse(result["claims"]["asymptotic_exponent_established"])

    def test_one_failed_hard_gate_blocks_the_benchmark(self):
        benchmark = load_route_benchmark(BENCHMARK_ID)
        manifest = load_admission_manifest(manifest_id=MANIFEST_ID)
        drifted = copy.deepcopy(manifest)
        drifted["validated_cases"][-1]["total_hartree"] += 0.01

        result = evaluate_route_benchmark(benchmark, drifted)

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["scientific_status"], "FAIL")
        self.assertEqual(result["promotion_eligibility"], "BLOCKED")
        failed = {gate["gate_id"] for gate in result["gates"] if gate["status"] == "FAIL"}
        self.assertIn("reference.total_energy", failed)
        self.assertIn("convergence.endpoint_delta", failed)

    def test_status_or_claim_overreach_blocks_the_benchmark(self):
        benchmark = load_route_benchmark(BENCHMARK_ID)
        manifest = load_admission_manifest(manifest_id=MANIFEST_ID)
        manifest["validated_cases"][0]["status"] = "FAILED"
        manifest["k_mesh_claim"]["convergence_exponent_established"] = True

        result = evaluate_route_benchmark(benchmark, manifest)

        failed = {gate["gate_id"] for gate in result["gates"] if gate["status"] == "FAIL"}
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("evidence.status", failed)
        self.assertIn("claim.boundary", failed)

    def test_fit_metrics_are_recomputed_and_checked_against_the_receipt(self):
        benchmark = load_route_benchmark(BENCHMARK_ID)
        manifest = load_admission_manifest(manifest_id=MANIFEST_ID)
        manifest["k_mesh_claim"]["fixed_n_minus_3_rms_millihartree"] = 99.0
        manifest["k_mesh_claim"]["extrapolated_limit_span_millihartree"] = 99.0

        result = evaluate_route_benchmark(benchmark, manifest)

        failed = {gate["gate_id"] for gate in result["gates"] if gate["status"] == "FAIL"}
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("receipt.derived_metrics", failed)
        self.assertAlmostEqual(
            result["metrics"]["fixed_n_minus_3_rms_millihartree"],
            0.399888,
            places=5,
        )
        self.assertAlmostEqual(
            result["metrics"]["extrapolated_limit_span_millihartree"],
            2.09295,
            places=4,
        )

    def test_invalid_benchmark_policy_is_rejected(self):
        benchmark = load_route_benchmark(BENCHMARK_ID)
        benchmark["tolerances"]["endpoint_total_delta_millihartree_max"] = -1.0

        with self.assertRaisesRegex(RouteBenchmarkError, "endpoint"):
            evaluate_route_benchmark(benchmark, load_admission_manifest(manifest_id=MANIFEST_ID))

    def test_benchmark_matrix_covers_target_routes_without_inventing_references(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        text = (root / "docs" / "benchmarks" / "benchmark-matrix-v1.md").read_text(
            encoding="utf-8"
        )

        for phrase in (
            "strict_2d_sos_rpa",
            "strict_2d_gw",
            "molecular_delta_st_rpa",
            "solid_delta_st_rpa",
            "periodic_3d_gw",
            "perovskite_gw",
            "transition_metal_oxide_gw",
            "altermagnet_gw",
            "REFERENCE_PENDING",
            "false-pass",
            "node-hour",
            "MaxRSS",
        ):
            self.assertIn(phrase, text)
        self.assertIn(SUITE_ID, text)

    def test_user_guidance_promotes_only_the_reference_bounded_sos_rpa_route(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        paths = (
            root / "README.md",
            root / "docs" / "guide" / "installation.md",
            root / "docs" / "live-benchmarks" / "2026-09-02-df-dcu-strict2d-sos-rpa.md",
            root / "skills" / "oh-my-librpa" / "SKILL.md",
            root / "skills" / "abacus-librpa-rpa" / "SKILL.md",
            root / "skills" / "abacus-librpa-version-guard" / "SKILL.md",
            root / "skills" / "oh-my-librpa" / "references" / "rpa-route.md",
        )

        for path in paths:
            text = path.read_text(encoding="utf-8")
            normalized = " ".join(text.split())
            self.assertIn("abacus-librpa-2026-09-03-strict2d-sos-rpa-v2", normalized)
            self.assertIn(BENCHMARK_ID, normalized)
            self.assertIn("ENABLED", normalized)
            self.assertIn("reference-bounded", normalized)
            self.assertIn("not strict-2D GW", normalized)
            self.assertIn("no asymptotic exponent", normalized)

        for path in (
            root / "README.md",
            root / "docs" / "guide" / "installation.md",
            root / "skills" / "oh-my-librpa" / "SKILL.md",
        ):
            self.assertIn("evaluate_route_benchmark_suite", path.read_text(encoding="utf-8"))

    def test_harness_scorecard_v3_requires_reference_and_false_pass_gates(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        repository_path = root / "benchmarks" / "scorecard-v3.json"
        packaged_path = root / "oml_mcp" / "benchmarks" / "scorecard-v3.json"
        scorecard = load_scorecard(repository_path)

        self.assertEqual(repository_path.read_bytes(), packaged_path.read_bytes())
        self.assertEqual(scorecard["scorecard_id"], "oml-production-benchmark-v3")
        self.assertEqual(sum(item["weight"] for item in scorecard["dimensions"]), 100)
        self.assertIn("scientific_reference", scorecard["hard_gates"])
        self.assertIn("no_known_false_pass", scorecard["hard_gates"])
        evidence = {
            "dimensions": {
                item["dimension_id"]: 1.0 for item in scorecard["dimensions"]
            },
            "hard_gates": {gate: True for gate in scorecard["hard_gates"]},
            "penalties": {"failed_attempts": 0, "ambiguous_attempts": 0},
        }
        passed = evaluate_evidence(evidence, scorecard=scorecard)
        evidence["hard_gates"]["no_known_false_pass"] = False
        blocked = evaluate_evidence(evidence, scorecard=scorecard)

        self.assertEqual(passed["verdict"], "PASS")
        self.assertEqual(passed["total_score"], 100.0)
        self.assertEqual(blocked["verdict"], "FAIL")
        self.assertFalse(blocked["eligible"])
        self.assertEqual(blocked["total_score"], 0.0)

    def test_registered_regression_suite_has_positive_and_failure_fixtures(self):
        suite = load_route_benchmark_suite(SUITE_ID)

        self.assertEqual(suite["benchmark_id"], BENCHMARK_ID)
        self.assertGreaterEqual(len(suite["cases"]), 10)
        self.assertEqual(
            {case["expected_verdict"] for case in suite["cases"]},
            {"PASS", "BLOCK"},
        )
        case_ids = {case["case_id"] for case in suite["cases"]}
        for case_id in (
            "reference-pass",
            "mixed-reader-contract",
            "missing-mesh",
            "non-finite-energy",
            "failed-process-status",
            "energy-drift",
            "finite-q-drift",
            "asymptotic-overclaim",
            "stale-fit-receipt",
        ):
            self.assertIn(case_id, case_ids)
        root = pathlib.Path(__file__).resolve().parents[1]
        self.assertEqual(
            (root / "benchmarks" / "suites" / f"{SUITE_ID}.json").read_bytes(),
            (
                root / "oml_mcp" / "benchmark_suites" / f"{SUITE_ID}.json"
            ).read_bytes(),
        )

    def test_registered_regression_suite_has_no_false_pass_or_false_block(self):
        result = evaluate_registered_route_benchmark_suite(suite_id=SUITE_ID)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["false_pass_count"], 0)
        self.assertEqual(result["false_block_count"], 0)
        self.assertEqual(result["fixture_mismatch_count"], 0)
        self.assertEqual(result["review_eligibility"], "REVIEWABLE")
        self.assertTrue(result["scorecard_gate_evidence"]["no_known_false_pass"])
        self.assertTrue(all(case["status"] == "PASS" for case in result["cases"]))

    def test_regression_suite_detects_a_false_pass(self):
        suite = load_route_benchmark_suite(SUITE_ID)
        suite["cases"].append(
            {
                "case_id": "deliberate-false-pass",
                "expected_verdict": "BLOCK",
                "operations": [],
                "expected_failed_gates": [],
            }
        )

        result = evaluate_route_benchmark_suite(suite)

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["false_pass_count"], 1)


class RouteBenchmarkServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_inspects_and_evaluates_the_reference_benchmark(self):
        server = build_server()
        inspected = await server.call_tool(
            "inspect_route_benchmark",
            {"benchmark_id": BENCHMARK_ID},
        )
        evaluated = await server.call_tool(
            "evaluate_route_benchmark",
            {"benchmark_id": BENCHMARK_ID, "manifest_id": MANIFEST_ID},
        )

        self.assertFalse(inspected.is_error, inspected.content)
        self.assertEqual(inspected.structured_content["benchmark_id"], BENCHMARK_ID)
        self.assertFalse(evaluated.is_error, evaluated.content)
        self.assertEqual(evaluated.structured_content["status"], "PASS")

    async def test_mcp_runs_the_registered_false_pass_regression_suite(self):
        result = await build_server().call_tool(
            "evaluate_route_benchmark_suite",
            {"suite_id": SUITE_ID},
        )

        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.structured_content["status"], "PASS")
        self.assertEqual(result.structured_content["false_pass_count"], 0)
        self.assertEqual(result.structured_content["false_block_count"], 0)


if __name__ == "__main__":
    unittest.main()
