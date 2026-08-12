from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .state import ACTIVE_ATTEMPT_STATUSES, StateStore


SCORECARD_NAME = "scorecard-v1.json"


class ScorecardError(ValueError):
    """Raised when scorecard or replay evidence is structurally invalid."""


def default_scorecard_path() -> Path:
    packaged = Path(__file__).resolve().parent / "benchmarks" / SCORECARD_NAME
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[1] / "benchmarks" / SCORECARD_NAME


def load_scorecard(path: str | Path | None = None) -> dict[str, Any]:
    scorecard_path = Path(path) if path is not None else default_scorecard_path()
    try:
        scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScorecardError(f"cannot read scorecard {scorecard_path}: {exc}") from exc
    if not isinstance(scorecard, dict) or scorecard.get("schema_version") != 1:
        raise ScorecardError("scorecard schema_version must be 1")
    dimensions = scorecard.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ScorecardError("scorecard dimensions must be a non-empty array")
    ids = [item.get("dimension_id") for item in dimensions if isinstance(item, dict)]
    weights = [item.get("weight") for item in dimensions if isinstance(item, dict)]
    if len(ids) != len(dimensions) or any(not isinstance(item, str) or not item for item in ids):
        raise ScorecardError("every scorecard dimension requires a non-empty dimension_id")
    if len(set(ids)) != len(ids):
        raise ScorecardError("scorecard dimension IDs must be unique")
    if any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in weights):
        raise ScorecardError("scorecard weights must be positive integers")
    if sum(weights) != scorecard.get("total_points") or sum(weights) != 100:
        raise ScorecardError("scorecard dimension weights must total 100")
    hard_gates = scorecard.get("hard_gates")
    if not isinstance(hard_gates, list) or not hard_gates or len(set(hard_gates)) != len(hard_gates):
        raise ScorecardError("scorecard hard gates must be a non-empty unique array")
    return scorecard


def _metric(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScorecardError(f"{label} must be a number from 0 to 1 or null")
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise ScorecardError(f"{label} must be between 0 and 1")
    return normalized


def evaluate_evidence(
    evidence: dict[str, Any],
    *,
    scorecard: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card = scorecard or load_scorecard()
    dimension_values = evidence.get("dimensions")
    hard_values = evidence.get("hard_gates")
    penalties = evidence.get("penalties", {})
    if not isinstance(dimension_values, dict) or not isinstance(hard_values, dict):
        raise ScorecardError("evidence requires dimensions and hard_gates objects")

    dimension_reports = []
    raw_score = 0.0
    evaluated_points = 0
    for item in card["dimensions"]:
        dimension_id = item["dimension_id"]
        value = _metric(dimension_values.get(dimension_id), f"dimensions.{dimension_id}")
        points = 0.0 if value is None else round(item["weight"] * value, 6)
        if value is not None:
            evaluated_points += item["weight"]
        raw_score += points
        dimension_reports.append(
            {
                "dimension_id": dimension_id,
                "weight": item["weight"],
                "status": "NOT_EVALUATED" if value is None else "EVALUATED",
                "value": value,
                "points": points,
            }
        )

    gate_reports = []
    hard_failures = []
    incomplete_gates = []
    for gate_id in card["hard_gates"]:
        value = hard_values.get(gate_id)
        if value not in {True, False, None}:
            raise ScorecardError(f"hard_gates.{gate_id} must be true, false, or null")
        status = "PASS" if value is True else "FAIL" if value is False else "NOT_EVALUATED"
        gate_reports.append({"gate_id": gate_id, "status": status})
        if value is False:
            hard_failures.append(gate_id)
        elif value is None:
            incomplete_gates.append(gate_id)

    penalty_rules = card["penalties"]
    failed_attempts = int(penalties.get("failed_attempts", 0))
    ambiguous_attempts = int(penalties.get("ambiguous_attempts", 0))
    if failed_attempts < 0 or ambiguous_attempts < 0:
        raise ScorecardError("attempt penalties cannot be negative")
    deduction = min(
        penalty_rules["maximum_deduction"],
        failed_attempts * penalty_rules["failed_attempts"]
        + ambiguous_attempts * penalty_rules["ambiguous_attempts"],
    )
    raw_score = round(raw_score, 6)
    eligible = not hard_failures
    total_score = 0.0 if not eligible else round(max(0.0, raw_score - deduction), 6)
    incomplete_dimensions = [
        item["dimension_id"] for item in dimension_reports if item["status"] == "NOT_EVALUATED"
    ]
    if hard_failures:
        verdict = "FAIL"
    elif incomplete_dimensions or incomplete_gates:
        verdict = "INCOMPLETE"
    elif total_score >= card["pass_threshold"]:
        verdict = "PASS"
    else:
        verdict = "FAIL"
    return {
        "ok": True,
        "scorecard_id": card["scorecard_id"],
        "verdict": verdict,
        "eligible": eligible,
        "raw_score": raw_score,
        "deduction": float(deduction),
        "total_score": total_score,
        "evaluated_points": evaluated_points,
        "dimensions": dimension_reports,
        "hard_gates": gate_reports,
        "hard_failures": hard_failures,
        "not_evaluated": [*incomplete_dimensions, *incomplete_gates],
        "penalties": {
            "failed_attempts": failed_attempts,
            "ambiguous_attempts": ambiguous_attempts,
        },
    }


def score_run(
    store: StateStore,
    run_id: str,
    *,
    provenance_ok: bool,
    prepared_versions_match: bool | None = None,
) -> dict[str, Any]:
    run = store.get_run(run_id)
    plan = store.get_plan(run["plan_id"])
    attempts = store.list_attempts(run_id)
    stages = list(plan["stages"])
    passed_stages = [
        stage for stage in stages if any(item["stage"] == stage and item["status"] == "PASSED" for item in attempts)
    ]
    failed_attempts = sum(item["status"] in {"FAILED", "CANCELLED"} for item in attempts)
    ambiguous_attempts = sum(item["status"] in {"UNKNOWN", "SUBMITTING"} for item in attempts)
    active_by_stage = {
        stage: sum(item["stage"] == stage and item["status"] in ACTIVE_ATTEMPT_STATUSES for item in attempts)
        for stage in stages
    }
    duplicate_active = any(count > 1 for count in active_by_stage.values())
    unresolved_failure = any(
        stage_attempts[-1]["status"] in {"FAILED", "CANCELLED"}
        for stage in stages
        if (
            stage_attempts := sorted(
                (item for item in attempts if item["stage"] == stage),
                key=lambda item: item["attempt_number"],
            )
        )
    )
    version_receipts = [
        item.get("preflight", {}).get("version_evidence", {}).get("verdict")
        for item in attempts
        if item.get("preflight")
    ]
    pinned_versions: bool | None
    if version_receipts:
        pinned_versions = all(item == "match" for item in version_receipts)
    else:
        pinned_versions = prepared_versions_match
    librpa_attempts = [item for item in attempts if item["stage"] == "librpa"]
    finite_final: bool | None = None
    if librpa_attempts:
        latest = librpa_attempts[-1]
        inspection = store.get_inspection(latest["attempt_id"])
        if inspection is not None:
            finite_final = bool(inspection["accepted"])
    evidence = {
        "dimensions": {
            "precompute_validation": 1.0 if provenance_ok else 0.0,
            "stage_execution_state": len(passed_stages) / len(stages),
            "diagnosis": None,
            "numerical_scientific_validity": None,
            "efficiency_reproducibility": (
                1.0 if attempts and all(item["scheduler_id"] for item in attempts) else 0.5
            ),
        },
        "hard_gates": {
            "immutable_provenance": provenance_ok,
            "pinned_versions": pinned_versions,
            "stage_lineage": passed_stages == stages[: len(passed_stages)],
            "no_duplicate_active_job": not duplicate_active,
            "no_unresolved_stage_failure": not unresolved_failure,
            "finite_final_output": finite_final,
        },
        "penalties": {
            "failed_attempts": failed_attempts,
            "ambiguous_attempts": ambiguous_attempts,
        },
    }
    report = evaluate_evidence(evidence)
    report["run_id"] = run_id
    report["progress"] = {
        "planned_stages": stages,
        "passed_stages": passed_stages,
        "attempt_count": len(attempts),
    }
    return report
