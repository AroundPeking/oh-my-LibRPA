import json
import pathlib
import tempfile
import unittest


from oml_mcp.evals import evaluate_evidence, load_scorecard, score_run
from oml_mcp.control import ControlledExecutionService
from oml_mcp.planner import plan_case
from oml_mcp.state import StateStore
from tests.test_materializer import make_periodic_source, make_profile
from tests.test_state import PLAN


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]


class ScorecardTest(unittest.TestCase):
    def test_scorecard_weights_total_one_hundred(self):
        scorecard = load_scorecard()

        self.assertEqual(sum(item["weight"] for item in scorecard["dimensions"]), 100)
        self.assertEqual(scorecard["total_points"], 100)
        self.assertEqual(scorecard["scorecard_id"], "oml-periodic-gw-v1")

    def test_hard_gate_is_non_compensating_even_with_perfect_dimensions(self):
        evidence = {
            "dimensions": {
                "precompute_validation": 1.0,
                "stage_execution_state": 1.0,
                "diagnosis": 1.0,
                "numerical_scientific_validity": 1.0,
                "efficiency_reproducibility": 1.0,
            },
            "hard_gates": {
                "immutable_provenance": True,
                "pinned_versions": True,
                "stage_lineage": True,
                "no_duplicate_active_job": True,
                "no_unresolved_stage_failure": True,
                "finite_final_output": False,
            },
            "penalties": {"failed_attempts": 0, "ambiguous_attempts": 0},
        }

        report = evaluate_evidence(evidence)

        self.assertEqual(report["raw_score"], 100.0)
        self.assertEqual(report["total_score"], 0.0)
        self.assertEqual(report["verdict"], "FAIL")
        self.assertFalse(report["eligible"])

    def test_incomplete_dimensions_are_not_silently_scored(self):
        replay = json.loads(
            (REPOSITORY / "benchmarks" / "replays" / "periodic-gw-incomplete-v1.json").read_text()
        )

        report = evaluate_evidence(replay["evidence"])

        self.assertEqual(report["verdict"], "INCOMPLETE")
        dimensions = {item["dimension_id"]: item for item in report["dimensions"]}
        self.assertEqual(dimensions["diagnosis"]["status"], "NOT_EVALUATED")
        self.assertEqual(
            dimensions["numerical_scientific_validity"]["status"], "NOT_EVALUATED"
        )
        self.assertLess(report["evaluated_points"], 100)

    def test_retry_and_ambiguous_attempt_penalties_are_bounded_and_visible(self):
        replay = json.loads(
            (REPOSITORY / "benchmarks" / "replays" / "periodic-gw-clean-v1.json").read_text()
        )
        replay["evidence"]["penalties"] = {"failed_attempts": 2, "ambiguous_attempts": 1}

        report = evaluate_evidence(replay["evidence"])

        self.assertEqual(report["raw_score"], 100.0)
        self.assertEqual(report["deduction"], 9.0)
        self.assertEqual(report["total_score"], 91.0)
        self.assertEqual(report["verdict"], "PASS")

    def test_frozen_replays_have_expected_verdicts(self):
        expected = {
            "periodic-gw-clean-v1.json": ("PASS", 100.0),
            "periodic-gw-convergence-incomplete-v1.json": ("INCOMPLETE", 55.0),
            "periodic-gw-convergence-pass-v1.json": ("PASS", 100.0),
            "periodic-gw-finite-unvalidated-v1.json": ("INCOMPLETE", 55.0),
            "periodic-gw-incomplete-v1.json": ("INCOMPLETE", 55.0),
            "periodic-gw-nonfinite-v1.json": ("FAIL", 0.0),
        }
        for name, outcome in expected.items():
            replay = json.loads((REPOSITORY / "benchmarks" / "replays" / name).read_text())
            report = evaluate_evidence(replay["evidence"])
            self.assertEqual((report["verdict"], report["total_score"]), outcome, name)

    def test_score_run_uses_persisted_attempts_and_leaves_science_not_evaluated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = StateStore(root / "state.sqlite3")
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-eval",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "run-eval"),
                remote_run_dir=None,
                manifest_digest="f" * 64,
            )
            attempt = store.authorize_submission(
                "run-eval",
                "scf",
                PLAN["digest"],
                preflight={
                    "version_evidence": {"verdict": "match"},
                    "remote_bundle": {"verdict": "not_applicable"},
                },
            )
            store.mark_attempt_submitted(attempt["attempt_id"], "123")
            store.record_attempt_status(attempt["attempt_id"], "PASSED")

            report = score_run(store, "run-eval", provenance_ok=True)

        self.assertEqual(report["verdict"], "INCOMPLETE")
        self.assertEqual(report["progress"]["passed_stages"], ["scf"])
        dimensions = {item["dimension_id"]: item for item in report["dimensions"]}
        self.assertEqual(dimensions["numerical_scientific_validity"]["status"], "NOT_EVALUATED")

    def test_service_score_reports_manifest_tampering_as_a_hard_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")
            service = ControlledExecutionService(profile)
            service.executor.verify_versions = lambda: {"verdict": "match", "components": {}}
            run = service.prepare_run(source, plan.digest)
            pathlib.Path(run["local_run_dir"], "STRU").write_text("tampered\n")

            report = service.score_case(run["run_id"], plan.digest)

        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(report["total_score"], 0.0)
        self.assertIn("immutable_provenance", report["hard_failures"])
        self.assertEqual(report["provenance_errors"][0]["code"], "MANIFEST_MISMATCH")

    def test_prepared_run_uses_immutable_execution_version_receipt(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")
            service = ControlledExecutionService(profile)
            service.executor.verify_versions = lambda: {"verdict": "match", "components": {}}
            run = service.prepare_run(source, plan.digest)

            report = service.score_case(run["run_id"], plan.digest)

        gates = {item["gate_id"]: item["status"] for item in report["hard_gates"]}
        self.assertEqual(gates["pinned_versions"], "PASS")

    def test_packaged_scorecard_matches_repository_copy(self):
        repository = json.loads((REPOSITORY / "benchmarks" / "scorecard-v1.json").read_text())
        packaged = json.loads(
            (REPOSITORY / "oml_mcp" / "benchmarks" / "scorecard-v1.json").read_text()
        )

        self.assertEqual(packaged, repository)

    def test_resolved_retry_is_penalized_but_not_a_permanent_hard_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = StateStore(root / "state.sqlite3")
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-retry",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "run-retry"),
                remote_run_dir=None,
                manifest_digest="f" * 64,
            )
            preflight = {
                "version_evidence": {"verdict": "match"},
                "remote_bundle": {"verdict": "not_applicable"},
            }
            failed = store.authorize_submission(
                "run-retry", "scf", PLAN["digest"], preflight=preflight
            )
            store.mark_attempt_submitted(failed["attempt_id"], "100")
            store.record_attempt_status(failed["attempt_id"], "FAILED")
            passed = store.authorize_submission(
                "run-retry", "scf", PLAN["digest"], preflight=preflight
            )
            store.mark_attempt_submitted(passed["attempt_id"], "101")
            store.record_attempt_status(passed["attempt_id"], "PASSED")

            report = score_run(store, "run-retry", provenance_ok=True)

        gates = {item["gate_id"]: item["status"] for item in report["hard_gates"]}
        self.assertEqual(gates["no_unresolved_stage_failure"], "PASS")
        self.assertEqual(report["penalties"]["failed_attempts"], 1)
        self.assertEqual(report["deduction"], 2.0)

    def test_matching_scientific_report_controls_numerical_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            store = StateStore(root / "state.sqlite3")
            store.register_plan(PLAN)
            store.create_run(
                run_id="run-scored-science",
                plan_id=PLAN["plan_id"],
                plan_digest=PLAN["digest"],
                execution_profile_id="test-local",
                local_run_dir=str(root / "run-scored-science"),
                remote_run_dir=None,
                manifest_digest="f" * 64,
            )
            final_attempt = None
            for stage in PLAN["stages"]:
                attempt = store.authorize_submission(
                    "run-scored-science", stage, PLAN["digest"]
                )
                store.mark_attempt_submitted(attempt["attempt_id"], str(400 + len(stage)))
                store.record_attempt_status(attempt["attempt_id"], "PASSED")
                final_attempt = attempt
            assert final_attempt is not None
            scientific = {
                "schema_version": 1,
                "report_id": "science-scored-pass",
                "run_id": "run-scored-science",
                "plan_digest": PLAN["digest"],
                "benchmark_id": "bn-reader-v1-3d-v1",
                "convergence_bundle_id": "bn-all-v1",
                "request_digest": "3" * 64,
                "final_attempt_id": final_attempt["attempt_id"],
                "manifest_digest": "f" * 64,
                "profile_id": "test-local",
                "scientific_status": "PASS",
                "diagnostics": {"accepted": True, "failure_count": 0, "failures": []},
            }
            store.record_scientific_report(scientific)

            report = score_run(
                store,
                "run-scored-science",
                provenance_ok=True,
                prepared_versions_match=True,
            )

        dimensions = {item["dimension_id"]: item for item in report["dimensions"]}
        self.assertEqual(dimensions["numerical_scientific_validity"]["value"], 1.0)
        self.assertEqual(dimensions["diagnosis"]["value"], 1.0)
        self.assertEqual(report["progress"]["scientific_report_id"], "science-scored-pass")
        self.assertEqual(report["progress"]["scientific_status"], "PASS")

    def test_v2_scorecard_has_the_approved_dimensions_and_packaged_copy(self):
        repository_path = REPOSITORY / "benchmarks" / "scorecard-v2.json"
        packaged_path = REPOSITORY / "oml_mcp" / "benchmarks" / "scorecard-v2.json"
        scorecard = load_scorecard(repository_path)

        self.assertEqual(
            {item["dimension_id"]: item["weight"] for item in scorecard["dimensions"]},
            {
                "reproducibility": 20,
                "prevention": 15,
                "stage_evidence": 20,
                "numerical_evaluation": 15,
                "scientific_evaluation": 20,
                "diagnosis_quality": 10,
            },
        )
        self.assertEqual(
            json.loads(repository_path.read_text(encoding="utf-8")),
            json.loads(packaged_path.read_text(encoding="utf-8")),
        )

    def test_v2_hard_gates_are_non_compensating(self):
        card = load_scorecard(REPOSITORY / "benchmarks" / "scorecard-v2.json")
        dimensions = {item["dimension_id"]: 1.0 for item in card["dimensions"]}

        for failed_gate in card["hard_gates"]:
            hard_gates = {gate_id: True for gate_id in card["hard_gates"]}
            hard_gates[failed_gate] = False
            report = evaluate_evidence(
                {
                    "dimensions": dimensions,
                    "hard_gates": hard_gates,
                    "penalties": {"failed_attempts": 0, "ambiguous_attempts": 0},
                },
                scorecard=card,
            )

            with self.subTest(failed_gate=failed_gate):
                self.assertEqual(report["verdict"], "FAIL")
                self.assertEqual(report["total_score"], 0.0)

    def test_v2_missing_evidence_is_incomplete_not_failed(self):
        card = load_scorecard(REPOSITORY / "benchmarks" / "scorecard-v2.json")
        dimensions = {item["dimension_id"]: 1.0 for item in card["dimensions"]}
        dimensions["scientific_evaluation"] = None
        hard_gates = {gate_id: True for gate_id in card["hard_gates"]}
        hard_gates["scientific_acceptance"] = None

        report = evaluate_evidence(
            {
                "dimensions": dimensions,
                "hard_gates": hard_gates,
                "penalties": {"failed_attempts": 0, "ambiguous_attempts": 0},
            },
            scorecard=card,
        )

        self.assertEqual(report["verdict"], "INCOMPLETE")
        self.assertTrue(report["eligible"])
        self.assertIn("scientific_evaluation", report["not_evaluated"])
        self.assertIn("scientific_acceptance", report["not_evaluated"])


if __name__ == "__main__":
    unittest.main()
