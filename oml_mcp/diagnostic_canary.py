"""Fast, reference-free diagnostic-battery canary for periodic 3D GW runs.

This module is the "fast benchmark" the user asked for. It does NOT need a
slow, converged reference and it is deliberately DECOUPLED from the
reference-based ``evaluate_regression`` production gate. Instead it replays
the cheap per-stage inspection battery (``inspect_stage_outputs``) over every
controlled stage and produces a single aggregated verdict.

The canary is fail-closed by design:

* A stage that was never attempted (no valid command receipt) is
  ``NOT_EVALUATED``, never silently PASSED. This is the no-false-pass rule:
  an incomplete pipeline cannot earn a green light.
* A stage that was attempted but produced any FAIL gate is ``FAIL``.
* A stage that was attempted and produced no FAIL gate is ``PASS`` (or
  ``WARN`` when a warning gate fired).
* The battery overall is ``PASS`` only when *every* requested stage was
  attempted and *every* gate in the battery is ``PASS``. Any ``WARN``,
  ``FAIL``, or unattempted stage demotes the battery to ``WARN`` /
  ``FAIL`` / ``NOT_EVALUATED`` respectively, so it never over-claims.

Optionally the battery can attach the curated known-issue remediation via
``diagnose_run`` so a fast scan also tells the agent what to fix next. The
canary never auto-submits or promotes anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .stage_inspection import inspect_stage_outputs
from .stage_templates import CONTROLLED_PERIODIC_STAGES


BATTERY_SCHEMA = "oml.diagnostic-battery.v1"

# Verdicts ordered from most- to least-conservative for the battery status.
_BATTERY_STATUS_ORDER = ("FAIL", "NOT_EVALUATED", "WARN", "PASS")


def _receipt_attempted(root: Path, stage: str) -> bool:
    """Whether a stage has a valid ``COMMAND_COMPLETED`` command receipt.

    A missing receipt means the stage was never run through the controlled
    stage script, so the canary must treat it as NOT_EVALUATED rather than
    as a failure.
    """
    path = root / ".oml" / "stage-results" / f"{stage}.status"
    if not path.is_file():
        return False
    try:
        status = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return False
    return status.startswith("COMMAND_COMPLETED")


def _stage_verdict(report: dict[str, Any]) -> str:
    """Map a stage inspection report onto a fail-closed stage verdict."""
    if report["accepted"]:
        if report["counts"].get("WARN", 0) > 0:
            return "WARN"
        return "PASS"
    return "FAIL"


def run_diagnostic_battery(
    run_path: str | Path,
    *,
    stages: Iterable[str] | None = None,
    include_remediation: bool = True,
) -> dict[str, Any]:
    """Run the reference-free diagnostic battery over the requested stages.

    Args:
        run_path: The immutable run directory holding the produced stage
            artifacts and the ``.oml/stage-results`` command receipts.
        stages: The subset of controlled stages to scan. Defaults to every
            controlled periodic stage (scf, pyatb, nscf, preprocess, librpa).
        include_remediation: When true, attach the curated known-issue
            matches for any FAIL/WARN gate via ``diagnose_run``.

    Returns:
        A ``oml.diagnostic-battery.v1`` report with a fail-closed ``status``,
        per-stage verdicts, an aggregated gate summary, and (optionally)
        ranked remediation matches.
    """
    root = Path(run_path).expanduser().resolve()
    if stages is None:
        stage_list = CONTROLLED_PERIODIC_STAGES
    else:
        stage_list = tuple(dict.fromkeys(stages))
        invalid = [stage for stage in stage_list if stage not in CONTROLLED_PERIODIC_STAGES]
        if invalid:
            raise ValueError(f"unsupported controlled stage(s): {', '.join(invalid)}")

    stage_reports: list[dict[str, Any]] = []
    all_gates: list[dict[str, Any]] = []
    stage_statuses: dict[str, str] = {}
    attempted_stages: list[str] = []
    for stage in stage_list:
        if not _receipt_attempted(root, stage):
            status = "NOT_EVALUATED"
            stage_reports.append(
                {
                    "stage": stage,
                    "status": status,
                    "reason": "stage was not attempted through the controlled stage script",
                    "accepted": False,
                    "counts": {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0},
                    "gates": [],
                }
            )
            stage_statuses[stage] = status
            continue

        attempted_stages.append(stage)
        report = inspect_stage_outputs(root, stage)
        status = _stage_verdict(report)
        stage_statuses[stage] = status
        # Collect the inspected gates for the aggregate summary.
        inspected_gates = [dict(gate) for gate in report["gates"]]
        all_gates.extend(inspected_gates)
        stage_reports.append(
            {
                "stage": stage,
                "status": status,
                "reason": None,
                "accepted": bool(report["accepted"]),
                "counts": dict(report["counts"]),
                "gates": inspected_gates,
            }
        )

    counts = {
        status: sum(
            gate["status"] == status
            for gate in all_gates
        )
        for status in ("PASS", "WARN", "FAIL", "SKIP")
    }

    # Fail-closed battery status. Only an entirely-PASS battery is PASS.
    if "FAIL" in stage_statuses.values():
        battery_status = "FAIL"
    elif any(status != "PASS" for status in stage_statuses.values()):
        # Any NOT_EVALUATED or WARN stage keeps the battery from over-claiming.
        if "NOT_EVALUATED" in stage_statuses.values():
            battery_status = "NOT_EVALUATED"
        else:
            battery_status = "WARN"
    else:
        battery_status = "PASS"

    report: dict[str, Any] = {
        "schema": BATTERY_SCHEMA,
        "schema_version": 1,
        "run_path": str(root),
        "status": battery_status,
        "accepted": battery_status == "PASS",
        "stages": stage_reports,
        "stage_statuses": stage_statuses,
        "gate_counts": counts,
        "gate_count": len(all_gates),
        "promotion_eligibility": "ENABLED" if battery_status == "PASS" else "BLOCKED",
    }

    if include_remediation:
        from .known_issues import diagnose_run

        if attempted_stages:
            merged_failing_gates: list[dict[str, Any]] = []
            merged_matches: list[dict[str, Any]] = []
            for stage in attempted_stages:
                part = diagnose_run(root, stage=stage)
                merged_failing_gates.extend(part["failing_gates"])
                merged_matches.extend(part["matches"])
            merged_matches.sort(
                key=lambda m: (-m["rank"], m["issue"]["issue_id"])
            )
            report["remediation"] = {
                "schema_version": 1,
                "run_path": str(root),
                "stage": attempted_stages,
                "failing_gates": merged_failing_gates,
                "matches": merged_matches[:5],
                "matched_count": len(merged_matches[:5]),
            }
        else:
            report["remediation"] = {
                "schema_version": 1,
                "run_path": str(root),
                "stage": [],
                "failing_gates": [],
                "matches": [],
                "matched_count": 0,
            }

    return report


def score_diagnostic_battery(
    report: dict[str, Any],
) -> dict[str, Any]:
    """Conservative bridge of a battery report into promotion evidence.

    The battery proves only that the produced pipeline is internally
    consistent and diagnostic-clean; it cannot prove numerical reference
    accuracy. So this bridge returns a ``promotion_eligibility`` of
    ``ENABLED`` only when the battery is fully PASS, and otherwise keeps the
    unproven evidence ``NOT_EVALUATED``. It never writes or promotes.
    """
    if report.get("schema") != BATTERY_SCHEMA:
        raise ValueError(f"battery report schema must be {BATTERY_SCHEMA}")
    status = report.get("status")
    if status == "PASS":
        return {
            "schema": "oml.diagnostic-battery-score.v1",
            "status": "PASS",
            "promotion_eligibility": "ENABLED",
            "not_evaluated": [],
            "evidence_note": "diagnostic battery is fully clean; reference accuracy remains unproven",
        }
    if status == "FAIL":
        return {
            "schema": "oml.diagnostic-battery-score.v1",
            "status": "FAIL",
            "promotion_eligibility": "BLOCKED",
            "not_evaluated": [],
            "evidence_note": "at least one diagnostic gate failed",
        }
    if status == "WARN":
        return {
            "schema": "oml.diagnostic-battery-score.v1",
            "status": "WARN",
            "promotion_eligibility": "BLOCKED",
            "not_evaluated": [],
            "evidence_note": "diagnostic battery clean but one or more warning gates fired",
        }
    return {
        "schema": "oml.diagnostic-battery-score.v1",
        "status": "NOT_EVALUATED",
        "promotion_eligibility": "BLOCKED",
        "not_evaluated": [
            stage
            for stage, stage_status in report.get("stage_statuses", {}).items()
            if stage_status == "NOT_EVALUATED"
        ],
        "evidence_note": "one or more stages were never attempted; evidence is incomplete",
    }
