"""Pre-submission audit: policies, reference class, and claim eligibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .policy_gates import PolicyFinding, run_gates
from .references import Reference, verdict


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    findings: tuple[PolicyFinding, ...]
    reference_verdict: dict[str, Any] | None
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [finding.to_dict() for finding in self.findings],
            "reference_verdict": self.reference_verdict,
            "reasons": list(self.reasons),
        }


def preflight(
    *,
    mode: str = "production",
    require_physical: bool = False,
    value: float | None = None,
    references: Sequence[Reference] = (),
    tolerance: float = 0.2,
    **gate_inputs: Any,
) -> PreflightResult:
    """Audit a run before submission (or before a claim).

    ``gate_inputs`` are forwarded to :func:`run_gates` (database_basis,
    missing_elements, scf_kgrid, dimension, abfs_orbital, exx_pca_threshold,
    use_shrink_abfs).
    """
    findings = run_gates(mode=mode, **gate_inputs)
    failures = [finding for finding in findings if finding.status == "FAIL"]
    reasons = [f"{finding.gate_id}: {finding.message}" for finding in failures]
    has_physical = any(reference.kind == "physical" for reference in references)
    if require_physical and not has_physical:
        reasons.append("no physical reference was supplied; a physical claim is not allowed")
    reference_verdict = (
        verdict(gates_ok=not failures, value=value, references=references, tolerance=tolerance)
        if value is not None
        else None
    )
    return PreflightResult(
        ok=not reasons,
        findings=findings,
        reference_verdict=reference_verdict,
        reasons=tuple(reasons),
    )
