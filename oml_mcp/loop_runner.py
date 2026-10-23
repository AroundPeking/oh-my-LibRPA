"""Closed-loop runner for the automated converged-result workflow.

One loop iteration is: run the current definition, analyze the produced bands
(smoothness, layer localization, gaps) and the fullcoul health, then either
accept the result or consult the retry rules for the next single-axis
candidate. Every trial is written to a ledger; candidate experiments are
proposals derived from rules and are never applied by any other path.

The runner is injected, so the loop can be exercised with synthetic artifacts
in tests and later bound to the real controlled-execution adapter.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .band_analysis import BandAnalysisError, analyze_band_set
from .coulomb_gate import CoulombGateError, coulomb_health
from .retry_rules import RetryRuleError, load_rules, lookup


DECREASE_STEP = 0.1
COULOMB_METHODS = {
    "out_librpa_3d_coulomb_method": ("ewald", "direct_reciprocal"),
    "out_librpa_2d_coulomb_method": ("ewald", "direct_mixed_fourier"),
}


class LoopError(ValueError):
    """Raised when the loop cannot be constructed or the ledger cannot be written."""


@dataclass(frozen=True)
class TrialOutcome:
    status: str
    artifacts: dict[str, str] = field(default_factory=dict)
    coulomb: dict[str, Any] | None = None
    elapsed_seconds: float | None = None
    job_ids: tuple[str, ...] = ()
    note: str = ""


class LoopRunner(Protocol):
    def run(self, definition: Mapping[str, Any], *, trial: int) -> TrialOutcome: ...


@dataclass
class TrialRecord:
    trial: int
    definition: dict[str, Any]
    definition_digest: str
    rule_id: str | None = None
    action: str | None = None
    outcome_status: str | None = None
    accepted: bool | None = None
    reasons: tuple[str, ...] = ()
    analysis: dict[str, Any] | None = None
    coulomb_verdict: str | None = None
    elapsed_seconds: float | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial": self.trial,
            "definition": self.definition,
            "definition_digest": self.definition_digest,
            "rule_id": self.rule_id,
            "action": self.action,
            "outcome_status": self.outcome_status,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "analysis": self.analysis,
            "coulomb_verdict": self.coulomb_verdict,
            "elapsed_seconds": self.elapsed_seconds,
            "artifacts": dict(self.artifacts),
            "note": self.note,
        }


@dataclass
class LoopResult:
    status: str
    definition: dict[str, Any]
    records: tuple[TrialRecord, ...]
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "definition": self.definition,
            "reason": self.reason,
            "records": [record.to_dict() for record in self.records],
        }


def definition_digest(definition: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(definition), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def analyze_outcome(
    outcome: TrialOutcome,
    *,
    occupied_bands: int | None = None,
    gap_reference_ev: float | None = None,
    gap_tolerance_ev: float = 0.2,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return ``(band_analysis, coulomb_health)``; either may be ``None``."""
    artifacts = outcome.artifacts or {}
    analysis = None
    if all(key in artifacts for key in ("ks", "exx", "gw")):
        try:
            analysis = analyze_band_set(
                {key: artifacts[key] for key in ("ks", "exx", "gw")},
                occupied_bands=occupied_bands,
                gap_reference_ev=gap_reference_ev,
                gap_tolerance_ev=gap_tolerance_ev,
            )
        except BandAnalysisError as exc:
            raise LoopError(f"band analysis failed: {exc}") from exc
    coulomb = None
    if outcome.coulomb:
        try:
            coulomb = coulomb_health(
                outcome.coulomb["matrix"],
                other_construction=outcome.coulomb.get("other"),
            )
        except CoulombGateError as exc:
            raise LoopError(f"coulomb health check failed: {exc}") from exc
    return analysis, coulomb


def diagnose(
    analysis: dict[str, Any] | None,
    coulomb: dict[str, Any] | None,
    *,
    lri_error_large: bool = False,
    auxiliary_ill_conditioned: bool = False,
) -> str | None:
    """Choose the retry rule that matches the observed evidence."""
    if auxiliary_ill_conditioned:
        return "r9"
    if coulomb is not None and coulomb["verdict"] == "FAIL":
        layer = (analysis or {}).get("localization", {}).get("layer")
        return "r4" if layer == "gw" else "r2"
    if analysis is not None:
        localization = analysis["localization"]
        layer = localization["layer"]
        if layer == "gw":
            return "r4"
        if layer == "exx":
            extent = localization["exx_minus_ks"]["classification"]
            return "r2" if extent == "large_range" else "r3"
        gap_check = analysis.get("gap_check")
        if gap_check is not None and not gap_check["pass"]:
            return "r7"
        if not analysis["accepted"]:
            # A non-smooth KS layer or an unmatched artifact: no rule claims it.
            return None
    if lri_error_large:
        return "r8"
    return None


def _decreased(value: Any) -> Any | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return value * DECREASE_STEP


def _previous_value(records: tuple[TrialRecord, ...], key: str, current: Any) -> Any | None:
    for record in reversed(records):
        if key in record.definition:
            value = record.definition[key]
            if value != current:
                return value
    return None


def next_candidate(
    rule: dict[str, Any],
    definition: Mapping[str, Any],
    records: tuple[TrialRecord, ...],
) -> tuple[dict[str, Any], str, str] | None:
    """Apply the first concrete candidate experiment as one-axis change."""
    for experiment in rule["candidate_experiments"]:
        direction = experiment.get("direction")
        parameters = list(experiment.get("parameters") or [])
        if not parameters:
            continue
        if direction == "decrease":
            for key in parameters:
                if key not in definition:
                    continue
                value = _decreased(definition[key])
                if value is None or value == definition[key]:
                    continue
                candidate = dict(definition)
                candidate[key] = value
                return candidate, key, experiment["action"]
        elif direction == "switch":
            for key in parameters:
                if key not in definition or key not in COULOMB_METHODS:
                    continue
                first, second = COULOMB_METHODS[key]
                current = definition[key]
                target = second if current == first else first
                if target == current:
                    continue
                candidate = dict(definition)
                candidate[key] = target
                return candidate, key, experiment["action"]
        elif direction == "revert":
            for key in parameters:
                current = definition.get(key)
                previous = _previous_value(records, key, current)
                if previous is None:
                    continue
                candidate = dict(definition)
                candidate[key] = previous
                return candidate, key, experiment["action"]
    return None


def run_loop(
    definition: Mapping[str, Any],
    runner: LoopRunner,
    *,
    occupied_bands: int | None = None,
    gap_reference_ev: float | None = None,
    gap_tolerance_ev: float = 0.2,
    max_trials: int = 8,
    max_consecutive_failures: int = 3,
    lri_error_large: bool = False,
    auxiliary_ill_conditioned: bool = False,
    ledger_path: str | Path | None = None,
) -> LoopResult:
    """Run the first trial, then follow the retry rules until acceptance or stop."""
    if max_trials <= 0:
        raise LoopError("max_trials must be positive")
    rules = load_rules()
    current = dict(definition)
    seen = {definition_digest(current)}
    records: list[TrialRecord] = []
    consecutive_failures = 0
    stop_status = "BUDGET_EXHAUSTED"
    stop_reason = ""

    for trial in range(1, max_trials + 1):
        outcome = runner.run(current, trial=trial)
        record = TrialRecord(
            trial=trial,
            definition=dict(current),
            definition_digest=definition_digest(current),
            outcome_status=outcome.status,
            artifacts=dict(outcome.artifacts or {}),
            elapsed_seconds=outcome.elapsed_seconds,
            note=outcome.note,
        )
        records.append(record)

        if outcome.status != "COMPLETED":
            consecutive_failures += 1
            stop_status = "INFRASTRUCTURE_ERROR"
            stop_reason = f"trial {trial} did not complete: {outcome.status}"
            if consecutive_failures >= max_consecutive_failures:
                break
            continue

        analysis, coulomb = analyze_outcome(
            outcome,
            occupied_bands=occupied_bands,
            gap_reference_ev=gap_reference_ev,
            gap_tolerance_ev=gap_tolerance_ev,
        )
        record.analysis = analysis
        record.coulomb_verdict = coulomb["verdict"] if coulomb else None
        accepted = bool(analysis and analysis["accepted"]) and not (
            coulomb is not None and coulomb["verdict"] == "FAIL"
        )
        record.accepted = accepted
        reasons = list((analysis or {}).get("reasons", ()))
        if coulomb is not None and coulomb["verdict"] == "FAIL":
            reasons.extend(coulomb["findings"])
        record.reasons = tuple(reasons)

        if accepted:
            stop_status = "ACCEPTED"
            stop_reason = f"trial {trial} passed the analysis gates"
            break

        rule_id = diagnose(
            analysis,
            coulomb,
            lri_error_large=lri_error_large,
            auxiliary_ill_conditioned=auxiliary_ill_conditioned,
        )
        if rule_id is None:
            stop_status = "NO_RULE"
            stop_reason = f"trial {trial} produced no matching retry rule: {reasons}"
            break

        try:
            rule = lookup(rule_id, rules)
        except RetryRuleError as exc:
            raise LoopError(str(exc)) from exc
        record.rule_id = rule_id
        proposal = next_candidate(rule, current, tuple(records))
        if proposal is None:
            stop_status = "NO_ACTION"
            stop_reason = (
                f"rule {rule_id} has no applicable one-axis candidate for this definition"
            )
            break
        candidate, axis, action = proposal
        record.action = f"{action} [{axis}]"
        digest = definition_digest(candidate)
        if digest in seen:
            stop_status = "DUPLICATE_DEFINITION"
            stop_reason = f"rule {rule_id} proposed an already-tried definition"
            break
        seen.add(digest)
        current = candidate
        consecutive_failures = 0
    else:
        stop_status = "BUDGET_EXHAUSTED"
        stop_reason = f"max_trials={max_trials} reached"

    result = LoopResult(
        status=stop_status, definition=current, records=tuple(records), reason=stop_reason
    )
    if ledger_path is not None:
        write_ledger(result, ledger_path)
    return result


def measure_noise_floor(
    definition: Mapping[str, Any],
    runner: LoopRunner,
    *,
    occupied_bands: int | None = None,
) -> dict[str, Any]:
    """Run the same definition twice and return the GW gap reproducibility delta.

    This is the control-replay anchor: acceptance tolerances for a campaign
    must sit above the measured floor, not at machine precision.
    """
    outcomes = [runner.run(definition, trial=0), runner.run(definition, trial=0)]
    analyses = [
        analyze_outcome(outcome, occupied_bands=occupied_bands)[0] for outcome in outcomes
    ]
    if any(analysis is None for analysis in analyses):
        return {"evaluated": False, "gap_delta_ev": None, "reason": "band artifacts missing"}
    assert analyses[0] is not None and analyses[1] is not None
    first = analyses[0]["gaps"]["gw"]["indirect_gap_ev"]
    second = analyses[1]["gaps"]["gw"]["indirect_gap_ev"]
    return {"evaluated": True, "gap_delta_ev": abs(second - first), "replays": 2}


def write_ledger(result: LoopResult, path: str | Path) -> None:
    """Write the full loop receipt as pretty JSON."""
    path = Path(path)
    try:
        path.write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise LoopError(f"cannot write loop ledger {path}: {exc}") from exc
