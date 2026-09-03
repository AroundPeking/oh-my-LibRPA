import copy
import pathlib
import unittest


from oml_mcp.admission_manifest import load_admission_manifest
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


if __name__ == "__main__":
    unittest.main()
