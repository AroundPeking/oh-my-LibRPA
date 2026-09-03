from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .admission_manifest import load_admission_manifest
from .provenance import digest_json
from .route_benchmark import (
    RouteBenchmarkError,
    evaluate_route_benchmark,
    load_route_benchmark,
)


STRICT2D_SOS_RPA_REGRESSION_SUITE_ID = "strict2d-sos-rpa-regression-v1"
ROUTE_BENCHMARK_SUITE_NAMES = {
    STRICT2D_SOS_RPA_REGRESSION_SUITE_ID: f"{STRICT2D_SOS_RPA_REGRESSION_SUITE_ID}.json",
}


def _packaged_suite_dir() -> Path:
    return Path(__file__).resolve().parent / "benchmark_suites"


def _repository_suite_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "suites"


def list_route_benchmark_suites() -> tuple[str, ...]:
    return tuple(ROUTE_BENCHMARK_SUITE_NAMES)


def _suite_path(suite_id: str) -> Path:
    try:
        name = ROUTE_BENCHMARK_SUITE_NAMES[suite_id]
    except KeyError as exc:
        raise RouteBenchmarkError(f"unknown route benchmark suite: {suite_id}") from exc
    packaged = _packaged_suite_dir() / name
    return packaged if packaged.is_file() else _repository_suite_dir() / name


def validate_route_benchmark_suite(suite: dict[str, Any]) -> None:
    if suite.get("schema") != "oml.route-benchmark-suite.v1":
        raise RouteBenchmarkError(
            "route benchmark suite schema must be oml.route-benchmark-suite.v1"
        )
    if suite.get("suite_id") != STRICT2D_SOS_RPA_REGRESSION_SUITE_ID:
        raise RouteBenchmarkError("route benchmark suite is not registered")
    benchmark = load_route_benchmark(str(suite.get("benchmark_id")))
    if suite.get("manifest_id") != benchmark["manifest_id"]:
        raise RouteBenchmarkError("route benchmark suite manifest does not match benchmark")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise RouteBenchmarkError("route benchmark suite cases must be non-empty")
    case_ids: set[str] = set()
    verdicts: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise RouteBenchmarkError("route benchmark suite cases must be objects")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise RouteBenchmarkError("route benchmark suite case IDs must be unique")
        case_ids.add(case_id)
        verdict = case.get("expected_verdict")
        if verdict not in {"PASS", "BLOCK"}:
            raise RouteBenchmarkError(f"suite case {case_id} has an invalid verdict")
        verdicts.add(verdict)
        operations = case.get("operations")
        if not isinstance(operations, list):
            raise RouteBenchmarkError(f"suite case {case_id} operations must be an array")
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("op") not in {
                "replace",
                "remove",
            }:
                raise RouteBenchmarkError(f"suite case {case_id} has an invalid operation")
            path = operation.get("path")
            if (
                not isinstance(path, list)
                or not path
                or any(
                    isinstance(segment, bool)
                    or not isinstance(segment, (str, int))
                    for segment in path
                )
            ):
                raise RouteBenchmarkError(f"suite case {case_id} has an invalid path")
            if operation["op"] == "replace" and "value" not in operation:
                raise RouteBenchmarkError(
                    f"suite case {case_id} replace operation requires a value"
                )
        expected_gates = case.get("expected_failed_gates", [])
        if (
            not isinstance(expected_gates, list)
            or any(not isinstance(gate, str) or not gate for gate in expected_gates)
            or len(expected_gates) != len(set(expected_gates))
        ):
            raise RouteBenchmarkError(
                f"suite case {case_id} expected_failed_gates must be unique strings"
            )
        expected_error = case.get("expected_error_contains")
        if expected_error is not None and (
            not isinstance(expected_error, str) or not expected_error
        ):
            raise RouteBenchmarkError(
                f"suite case {case_id} expected_error_contains must be non-empty"
            )
    if verdicts != {"PASS", "BLOCK"}:
        raise RouteBenchmarkError("route benchmark suite requires PASS and BLOCK cases")


def load_route_benchmark_suite(suite_id: str) -> dict[str, Any]:
    path = _suite_path(suite_id)
    try:
        suite = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RouteBenchmarkError(f"cannot read route benchmark suite {path}: {exc}") from exc
    if not isinstance(suite, dict):
        raise RouteBenchmarkError("route benchmark suite root must be an object")
    validate_route_benchmark_suite(suite)
    return copy.deepcopy(suite)


def _resolve_mutation_parent(
    root: dict[str, Any],
    path: list[str | int],
) -> tuple[dict[str, Any] | list[Any], str | int]:
    current: Any = root
    for segment in path[:-1]:
        try:
            current = current[segment]
        except (KeyError, IndexError, TypeError) as exc:
            raise RouteBenchmarkError(f"suite mutation path does not exist: {path}") from exc
    if not isinstance(current, (dict, list)):
        raise RouteBenchmarkError(f"suite mutation parent is not a container: {path}")
    final = path[-1]
    if isinstance(current, list) and not isinstance(final, int):
        raise RouteBenchmarkError(f"suite list mutation requires an integer index: {path}")
    if isinstance(current, dict) and not isinstance(final, str):
        raise RouteBenchmarkError(f"suite object mutation requires a string key: {path}")
    try:
        current[final]
    except (KeyError, IndexError, TypeError) as exc:
        raise RouteBenchmarkError(f"suite mutation target does not exist: {path}") from exc
    return current, final


def _apply_suite_operations(
    manifest: dict[str, Any],
    operations: list[dict[str, Any]],
) -> None:
    for operation in operations:
        parent, final = _resolve_mutation_parent(manifest, operation["path"])
        if operation["op"] == "replace":
            parent[final] = copy.deepcopy(operation["value"])
        else:
            del parent[final]


def evaluate_route_benchmark_suite(suite: dict[str, Any]) -> dict[str, Any]:
    validate_route_benchmark_suite(suite)
    benchmark = load_route_benchmark(suite["benchmark_id"])
    baseline = load_admission_manifest(manifest_id=suite["manifest_id"])
    reports = []
    false_pass_count = 0
    false_block_count = 0
    fixture_mismatch_count = 0
    for case in suite["cases"]:
        manifest = copy.deepcopy(baseline)
        _apply_suite_operations(manifest, case["operations"])
        evaluator_error = None
        result = None
        try:
            result = evaluate_route_benchmark(benchmark, manifest)
        except (RouteBenchmarkError, TypeError, ValueError) as exc:
            evaluator_error = str(exc)
        observed_verdict = (
            "PASS" if result is not None and result["status"] == "PASS" else "BLOCK"
        )
        expected_verdict = case["expected_verdict"]
        false_pass = expected_verdict == "BLOCK" and observed_verdict == "PASS"
        false_block = expected_verdict == "PASS" and observed_verdict == "BLOCK"
        failed_gates = (
            []
            if result is None
            else [
                gate["gate_id"]
                for gate in result["gates"]
                if gate["status"] == "FAIL"
            ]
        )
        expected_gates = case.get("expected_failed_gates", [])
        expected_error = case.get("expected_error_contains")
        gate_receipt_matches = set(expected_gates).issubset(failed_gates)
        error_receipt_matches = expected_error is None or (
            evaluator_error is not None and expected_error in evaluator_error
        )
        fixture_matches = (
            observed_verdict == expected_verdict
            and gate_receipt_matches
            and error_receipt_matches
        )
        false_pass_count += int(false_pass)
        false_block_count += int(false_block)
        fixture_mismatch_count += int(not fixture_matches and not false_pass and not false_block)
        reports.append(
            {
                "case_id": case["case_id"],
                "status": "PASS" if fixture_matches else "FAIL",
                "expected_verdict": expected_verdict,
                "observed_verdict": observed_verdict,
                "failed_gates": failed_gates,
                "evaluator_error": evaluator_error,
            }
        )
    passed = not (false_pass_count or false_block_count or fixture_mismatch_count)
    return {
        "schema": "oml.route-benchmark-suite-result.v1",
        "suite_id": suite["suite_id"],
        "suite_digest": digest_json(suite),
        "benchmark_id": suite["benchmark_id"],
        "manifest_id": suite["manifest_id"],
        "status": "PASS" if passed else "FAIL",
        "review_eligibility": "REVIEWABLE" if passed else "BLOCKED",
        "scorecard_gate_evidence": {
            "no_known_false_pass": false_pass_count == 0,
        },
        "case_count": len(reports),
        "false_pass_count": false_pass_count,
        "false_block_count": false_block_count,
        "fixture_mismatch_count": fixture_mismatch_count,
        "cases": reports,
    }


def evaluate_registered_route_benchmark_suite(*, suite_id: str) -> dict[str, Any]:
    return evaluate_route_benchmark_suite(load_route_benchmark_suite(suite_id))
