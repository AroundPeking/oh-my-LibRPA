"""Per-step scorecard for ONE complete ABACUS -> LibRPA calculation.

The 2026-09-12 scope decision: the active benchmark scores whether a single
complete calculation does every step correctly, not whether parameter ladders
converge. This module turns the diagnostic battery's per-stage gates into a
fixed step scorecard (100 points) so a run reports *where* it earned or lost
points instead of one aggregate verdict.

Steps and weights (total 100):

- ``scf``            15  ground-state self-consistency (OUT.ABACUS, vxc, stru_out)
- ``nscf``           10  band-path wave functions (eig.txt, band_KS assets)
- ``pyatb``          15  PyATB head/wing adapter (metadata, eigenvector/velocity dims)
- ``coulomb_dataset`` 15 reader-v1 Coulomb family (Hermitian + PSD per q block)
- ``preprocess``     10  band preprocessing (kpath info, per-k files)
- ``librpa``         20  LibRPA stage (completion, GW band shape, finite scalars)
- ``handoff``        15  cross-step state-space contract (nbands == nbasis)

Scoring rules are deliberately strict and never over-claim:

- A step whose stage was never attempted scores 0 and is ``NOT_EVALUATED``.
- Any FAIL gate zeroes the step, regardless of other passes.
- Any WARN gate halves the step (integer floor) and marks it ``WARN``.
- A step with only neutral SKIP gates scores 0 and is ``SKIP``.
- Full marks require every gate PASS and every step attempted; the total can
  only be 100 when every step is fully green.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .diagnostic_canary import run_diagnostic_battery


STEP_SCORECARD_SCHEMA = "oml.step-scorecard.v1"
STEP_SCORECARD_ID = "oml-full-calculation-steps-v1"

# The fixed step -> weight table. The sum MUST stay 100; a test pins it.
STEP_WEIGHTS: dict[str, int] = {
    "scf": 15,
    "nscf": 10,
    "pyatb": 15,
    "coulomb_dataset": 15,
    "preprocess": 10,
    "librpa": 20,
    "handoff": 15,
}


def _route_gate(stage: str, gate_id: str) -> str:
    """Assign one gate to its scorecard step."""
    if stage == "pyatb":
        if gate_id.startswith("coulomb."):
            return "coulomb_dataset"
        if gate_id.startswith("stage.state_space."):
            return "handoff"
        return "pyatb"
    if stage in STEP_WEIGHTS:
        return stage
    raise ValueError(f"unroutable stage {stage!r} for gate {gate_id!r}")


def score_run_steps(run_path: str | Path) -> dict[str, Any]:
    """Score one run step by step against the fixed 100-point table.

    The underlying evidence is the reference-free diagnostic battery: the
    scorecard adds no checks of its own, it only attributes the existing
    gates to the step where the work happened and assigns points.
    """
    battery = run_diagnostic_battery(run_path, include_remediation=True)
    attempted = {
        stage: report["status"] != "NOT_EVALUATED"
        for stage, report in (
            (report["stage"], report) for report in battery["stages"]
        )
    }

    step_gates: dict[str, list[dict[str, Any]]] = {step: [] for step in STEP_WEIGHTS}
    step_attempted: dict[str, bool] = {step: False for step in STEP_WEIGHTS}
    for report in battery["stages"]:
        stage = report["stage"]
        for gate in report["gates"]:
            step = _route_gate(stage, str(gate["gate_id"]))
            step_gates[step].append(gate)
        if attempted[stage]:
            step_attempted[_route_gate(stage, "stage.command")] = True
            for gate in report["gates"]:
                step_attempted[_route_gate(stage, str(gate["gate_id"]))] = True

    steps: list[dict[str, Any]] = []
    total = 0
    statuses: list[str] = []
    for step, weight in STEP_WEIGHTS.items():
        gates = step_gates[step]
        counts = {
            status: sum(gate["status"] == status for gate in gates)
            for status in ("PASS", "WARN", "FAIL", "SKIP")
        }
        if not step_attempted[step]:
            status = "NOT_EVALUATED"
        elif counts["FAIL"] > 0:
            status = "FAIL"
        elif counts["WARN"] > 0:
            status = "WARN"
        elif counts["PASS"] > 0:
            status = "PASS"
        else:
            status = "SKIP"
        if status == "PASS":
            points = weight
        elif status == "WARN":
            points = weight // 2
        else:
            points = 0
        total += points
        statuses.append(status)
        steps.append(
            {
                "step": step,
                "weight": weight,
                "points": points,
                "status": status,
                "gate_counts": counts,
                "gate_ids": [str(gate["gate_id"]) for gate in gates],
            }
        )

    if "FAIL" in statuses:
        overall = "FAIL"
    elif "NOT_EVALUATED" in statuses:
        overall = "NOT_EVALUATED"
    elif "WARN" in statuses or "SKIP" in statuses:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "schema": STEP_SCORECARD_SCHEMA,
        "scorecard_id": STEP_SCORECARD_ID,
        "run_path": str(Path(run_path).expanduser().resolve()),
        "status": overall,
        "total_points": total,
        "max_points": 100,
        "steps": steps,
        "battery_status": battery["status"],
        "remediation": battery.get("remediation"),
        "promotion_eligibility": "ENABLED" if overall == "PASS" else "BLOCKED",
    }
