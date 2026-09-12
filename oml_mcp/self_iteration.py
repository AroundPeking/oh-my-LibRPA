"""Closed-loop self-iteration over the fast ABACUS + LibRPA benchmark.

This is the "auto-evolve" requirement. The loop is:

    baseline definition
        -> propose ONE-axis parameter mutation
        -> materialize a fresh immutable run
        -> submit every stage to the remote scheduler
        -> observe + inspect each stage against the diagnostic gates
        -> compare the produced case against its frozen reference
        -> ACCEPT (record the win) or REJECT (record the failure + lesson)
        -> feed the outcome back as the next baseline / known issue
        -> repeat until the budget is exhausted or no axis can improve

Design rules enforced here
--------------------------
* **One axis per iteration.** Every candidate changes exactly one definition
  axis, reusing ``evolution.propose_candidate``. This keeps attribution clean:
  if the score moves, exactly one parameter caused it.
* **Fresh run per attempt.** The controlled executor forbids reusing a run
  directory after a terminal stage attempt, so every iteration materializes a
  new immutable run.
* **No false pass.** A candidate is accepted only when the fast case returns
  ``PASS`` against its frozen reference. Anything else (FAIL, NOT_EVALUATED,
  infrastructure error) is a rejection, and the reason is recorded.
* **Budgeted and auditable.** Every attempt appends a ledger record with the
  axis, the candidate definition, the observed verdict, and the lesson.
* **Proposal-only by default.** ``execute=False`` performs a dry run that
  proposes candidates and stops; the caller must opt in to real submission.

The engine itself never submits anything: it drives an injected *adapter*.
That keeps the loop testable without touching a cluster, and makes the real
(remote) execution a drop-in implementation of the same interface.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, Sequence

from .evolution import (
    CandidateProposal,
    EvolutionBudget,
    EvolutionError,
    EvolutionUsage,
    ROUTE_MUTATION_AXES,
    propose_candidate,
)
from .fast_benchmark import FastCase, FastCaseError, evaluate_case_against_reference
from .provenance import digest_json


LOOP_SCHEMA = "oml.self-iteration.v1"
LEDGER_SCHEMA = "oml.self-iteration-ledger.v1"

# Outcome vocabulary for one iteration.
ACCEPTED = "ACCEPTED"
REJECTED_GATE = "REJECTED_GATE"
REJECTED_REFERENCE = "REJECTED_REFERENCE"
NOT_EVALUATED = "NOT_EVALUATED"
INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"


class SelfIterationError(ValueError):
    """Raised when the self-iteration loop is misconfigured or misused."""


class IterationAdapter(Protocol):
    """The execution surface the loop drives.

    A real implementation materializes a run, submits the controlled stages
    to Slurm over SSH, waits for completion, and returns the produced case
    outputs. A test implementation returns synthetic outputs immediately.
    """

    def run_candidate(
        self,
        *,
        case: FastCase,
        candidate: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        """Execute one candidate and return its artifacts.

        Must return a mapping with at least:
          ``status``: "COMPLETED" | "FAILED" | "UNKNOWN"
          ``observed``: {file_name: text} for reference comparison
          ``diagnostics``: the aggregated diagnostic-battery report (optional)
          ``run_id`` / ``detail``: provenance for the ledger (optional)
        """
        ...


@dataclass(frozen=True)
class IterationRecord:
    """One auditable iteration of the loop."""

    iteration: int
    changed_axis: str | None
    candidate_digest: str | None
    candidate: dict[str, Any]
    outcome: str
    fast_case_status: str
    reason: str
    lesson: str | None = None
    run_id: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), sort_keys=True))


@dataclass(frozen=True)
class LoopPolicy:
    """How aggressively the loop may explore."""

    budget: EvolutionBudget
    # Axes the caller allows the loop to vary, in priority order.
    allowed_axes: tuple[str, ...]
    # Stop early after this many consecutive rejections (0 disables).
    stop_after_consecutive_rejections: int = 0
    execute: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_axes:
            raise SelfIterationError("loop policy must allow at least one axis")
        if len(set(self.allowed_axes)) != len(self.allowed_axes):
            raise SelfIterationError("loop policy allowed_axes must be unique")
        if (
            isinstance(self.stop_after_consecutive_rejections, bool)
            or not isinstance(self.stop_after_consecutive_rejections, int)
            or self.stop_after_consecutive_rejections < 0
        ):
            raise SelfIterationError(
                "stop_after_consecutive_rejections must be a non-negative integer"
            )


def axis_candidates(
    baseline: dict[str, Any],
    *,
    axis: str,
    values: Sequence[Any],
) -> tuple[dict[str, Any], ...]:
    """Build one-axis candidate definitions for an axis.

    Each returned definition is a deep copy of ``baseline`` with exactly the
    named axis replaced, which is what ``propose_candidate`` requires.
    """
    if axis not in baseline:
        raise SelfIterationError(f"baseline does not define axis: {axis}")
    if not values:
        raise SelfIterationError(f"axis {axis} needs at least one candidate value")
    out: list[dict[str, Any]] = []
    for value in values:
        candidate = json.loads(json.dumps(baseline))
        candidate[axis] = value
        out.append(candidate)
    return tuple(out)


def _default_reference_loader(case: FastCase) -> dict[str, str]:
    """Load reference text for a case from its declared files.

    The reference lives beside the case upstream; when it is not reachable the
    loop treats the comparison as NOT_EVALUATED rather than guessing.
    """
    return {}


def _lesson_for(outcome: str, reason: str, axis: str | None) -> str:
    """Produce a short, reusable lesson string for the ledger."""
    if outcome == ACCEPTED:
        return f"axis {axis} improved the fast-case verdict; keep this value as the new baseline"
    if outcome == REJECTED_REFERENCE:
        return (
            f"axis {axis} produced a numerically wrong result ({reason}); "
            "do not retry this value and check the parameter prescription for this system"
        )
    if outcome == REJECTED_GATE:
        return (
            f"axis {axis} produced a diagnostically invalid run ({reason}); "
            "fix the gate failure before spending more compute on this axis"
        )
    if outcome == NOT_EVALUATED:
        return (
            f"axis {axis} could not be evaluated ({reason}); "
            "supply the missing reference or artifact before iterating again"
        )
    return f"axis {axis} hit an infrastructure error ({reason}); repair the environment first"


def run_self_iteration(
    *,
    case: FastCase,
    baseline: dict[str, Any],
    axis_values: dict[str, Sequence[Any]],
    policy: LoopPolicy,
    adapter: IterationAdapter,
    reference: dict[str, str] | None = None,
    existing_definition_digests: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Run the closed propose -> execute -> evaluate -> accept/reject loop.

    Args:
        case: The fast benchmark case this loop is optimising against.
        baseline: The starting definition (a flat parameter mapping).
        axis_values: Candidate values per axis. Only axes listed in
            ``policy.allowed_axes`` are explored, in that order.
        policy: Budget, allowed axes, early-stop rule and the ``execute`` flag.
        adapter: The execution surface (real remote driver or a test fake).
        reference: Frozen reference text keyed by file name. When omitted the
            case cannot be evaluated and every iteration reports NOT_EVALUATED.
        existing_definition_digests: Digests already explored, so the loop does
            not re-propose a definition it has already seen.

    Returns:
        A ``oml.self-iteration.v1`` report containing the accepted definition,
        the full ledger, and the budget actually consumed.
    """
    if not isinstance(baseline, dict) or not baseline:
        raise SelfIterationError("baseline must be a non-empty definition object")

    registered = ROUTE_MUTATION_AXES.get(case.route)
    if registered is None:
        raise SelfIterationError(
            f"route is not registered for controlled evolution: {case.route}"
        )
    unknown = [axis for axis in policy.allowed_axes if axis not in registered]
    if unknown:
        raise SelfIterationError(
            f"axes are not registered for route {case.route}: {', '.join(unknown)}"
        )
    if not case.evaluable:
        raise SelfIterationError(
            f"fast case {case.case_id} is not evaluable "
            f"(reference_status={case.reference_status}); refusing to iterate without a reference"
        )

    reference = dict(reference or {})
    ledger: list[IterationRecord] = []
    seen = set(existing_definition_digests)
    usage = EvolutionUsage()
    accepted_definition = json.loads(json.dumps(baseline))
    accepted_digest = digest_json({"route_id": case.route, "definition": accepted_definition})
    seen.add(accepted_digest)

    iteration = 0
    consecutive_rejections = 0
    stop_reason = "BUDGET_EXHAUSTED"

    for axis in policy.allowed_axes:
        if usage.candidates >= policy.budget.max_candidates:
            stop_reason = "BUDGET_EXHAUSTED"
            break
        if (
            policy.stop_after_consecutive_rejections
            and consecutive_rejections >= policy.stop_after_consecutive_rejections
        ):
            stop_reason = "CONSECUTIVE_REJECTIONS"
            break

        values = axis_values.get(axis, ())
        for value in values:
            if usage.candidates >= policy.budget.max_candidates:
                stop_reason = "BUDGET_EXHAUSTED"
                break
            if (
                policy.stop_after_consecutive_rejections
                and consecutive_rejections >= policy.stop_after_consecutive_rejections
            ):
                stop_reason = "CONSECUTIVE_REJECTIONS"
                break

            iteration += 1
            candidate = json.loads(json.dumps(accepted_definition))
            candidate[axis] = value

            try:
                proposal: CandidateProposal = propose_candidate(
                    route_id=case.route,
                    baseline=accepted_definition,
                    candidate=candidate,
                    existing_definition_digests=frozenset(seen),
                    budget=policy.budget,
                    usage=usage,
                )
            except EvolutionError as exc:
                # A duplicate or rejected proposal does not consume budget but
                # is still recorded, so the ledger is a complete trace.
                ledger.append(
                    IterationRecord(
                        iteration=iteration,
                        changed_axis=axis,
                        candidate_digest=None,
                        candidate=candidate,
                        outcome=NOT_EVALUATED,
                        fast_case_status="NOT_EVALUATED",
                        reason=str(exc),
                        lesson=f"proposal for axis {axis} was rejected before execution",
                    )
                )
                continue

            usage = EvolutionUsage(
                candidates=usage.candidates + 1,
                cpu_hours=usage.cpu_hours,
                wall_seconds=usage.wall_seconds,
                disk_bytes=usage.disk_bytes,
            )
            seen.add(proposal.definition_digest)

            if not policy.execute:
                ledger.append(
                    IterationRecord(
                        iteration=iteration,
                        changed_axis=axis,
                        candidate_digest=proposal.definition_digest,
                        candidate=proposal.candidate,
                        outcome=NOT_EVALUATED,
                        fast_case_status="NOT_EVALUATED",
                        reason="dry run: execution is disabled by policy",
                        lesson="set execute=True to submit this candidate",
                    )
                )
                continue

            try:
                observation = adapter.run_candidate(
                    case=case,
                    candidate=proposal.candidate,
                    iteration=iteration,
                )
            except Exception as exc:  # adapter/remote failure is a first-class outcome
                consecutive_rejections += 1
                ledger.append(
                    IterationRecord(
                        iteration=iteration,
                        changed_axis=axis,
                        candidate_digest=proposal.definition_digest,
                        candidate=proposal.candidate,
                        outcome=INFRASTRUCTURE_ERROR,
                        fast_case_status="NOT_EVALUATED",
                        reason=f"{type(exc).__name__}: {exc}",
                        lesson=_lesson_for(INFRASTRUCTURE_ERROR, str(exc), axis),
                    )
                )
                continue

            observed = observation.get("observed") or {}
            verdict = evaluate_case_against_reference(case, reference, observed)
            fast_status = verdict["status"]
            run_id = observation.get("run_id")

            diagnostics = observation.get("diagnostics") or {}
            diagnostics_status = diagnostics.get("status")

            if observation.get("status") != "COMPLETED":
                outcome = INFRASTRUCTURE_ERROR
                reason = f"stage execution did not complete: {observation.get('status')}"
            elif diagnostics_status == "FAIL":
                outcome = REJECTED_GATE
                reason = "diagnostic battery failed"
            elif fast_status == "PASS":
                outcome = ACCEPTED
                reason = verdict["reason_code"]
            elif fast_status == "FAIL":
                outcome = REJECTED_REFERENCE
                reason = verdict["reason_code"]
            else:
                outcome = NOT_EVALUATED
                reason = verdict["reason_code"]

            if outcome == ACCEPTED:
                accepted_definition = json.loads(json.dumps(proposal.candidate))
                accepted_digest = proposal.definition_digest
                consecutive_rejections = 0
            else:
                consecutive_rejections += 1

            ledger.append(
                IterationRecord(
                    iteration=iteration,
                    changed_axis=axis,
                    candidate_digest=proposal.definition_digest,
                    candidate=proposal.candidate,
                    outcome=outcome,
                    fast_case_status=fast_status,
                    reason=reason,
                    lesson=_lesson_for(outcome, reason, axis),
                    run_id=run_id,
                    detail={
                        "validators": verdict.get("validators", []),
                        "diagnostics_status": diagnostics_status,
                        "adapter_detail": observation.get("detail"),
                    },
                )
            )

    accepted_iterations = [r.iteration for r in ledger if r.outcome == ACCEPTED]
    return {
        "schema": LOOP_SCHEMA,
        "schema_version": 1,
        "case_id": case.case_id,
        "route": case.route,
        "executed": policy.execute,
        "stop_reason": stop_reason,
        "iterations": iteration,
        "accepted_count": len(accepted_iterations),
        "accepted_iterations": accepted_iterations,
        "baseline_digest": digest_json({"route_id": case.route, "definition": baseline}),
        "accepted_definition": accepted_definition,
        "accepted_digest": accepted_digest,
        "improved": accepted_digest != digest_json({"route_id": case.route, "definition": baseline}),
        "budget": asdict(policy.budget),
        "usage": asdict(usage),
        "ledger": [record.to_dict() for record in ledger],
    }


def write_ledger(report: dict[str, Any], path: str | Path) -> Path:
    """Persist a loop report as a durable ledger artifact."""
    if report.get("schema") != LOOP_SCHEMA:
        raise SelfIterationError(f"report schema must be {LOOP_SCHEMA}")
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": LEDGER_SCHEMA, "schema_version": 1, "report": report}
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target
