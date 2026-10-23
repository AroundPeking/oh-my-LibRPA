"""Typed references and the claim vocabulary.

A replay reference (a frozen regression baseline) can only support the claim
"the code reproduced its regression". A physical reference (a trusted database
or literature value with a scope) is required for any physical claim. The
verdict function enforces that separation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence


KINDS = frozenset({"replay", "physical"})
STATUSES = frozenset({"validated", "reported", "provisional", "regression"})
PHYSICAL_STATUSES = frozenset({"validated", "reported", "provisional"})
STATUS_PRIORITY = {"validated": 0, "provisional": 1, "reported": 2, "regression": 3}


class ReferenceError(ValueError):
    """Raised when a reference is malformed."""


@dataclass(frozen=True)
class Reference:
    kind: str
    value: float
    source: str
    scope: str
    status: str
    unit: str = "eV"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "value": self.value,
            "source": self.source,
            "scope": self.scope,
            "status": self.status,
            "unit": self.unit,
        }


def _make(kind: str, value: Any, source: str, scope: str, status: str) -> Reference:
    if kind not in KINDS:
        raise ReferenceError(f"unsupported reference kind {kind!r}")
    if status not in STATUSES:
        raise ReferenceError(f"unsupported reference status {status!r}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReferenceError("reference value must be a number")
    if not isinstance(source, str) or not source:
        raise ReferenceError("reference source must be a non-empty string")
    return Reference(kind=kind, value=float(value), source=source, scope=str(scope), status=status)


def replay_reference(value: float, *, source: str, scope: str = "regression replay") -> Reference:
    return _make("replay", value, source, scope, "regression")


def physical_reference(value: float, *, source: str, scope: str, status: str) -> Reference:
    if status not in PHYSICAL_STATUSES:
        raise ReferenceError(f"physical references need one of {sorted(PHYSICAL_STATUSES)}")
    return _make("physical", value, source, scope, status)


def physical_from_record(record: dict[str, Any], *, source_id: str | None = None) -> Reference | None:
    """Map one LibRPA-database record to a physical reference, when it has a value."""
    summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
    value = summary.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    statuses = {
        str(prop.get("status", "")).lower()
        for prop in record.get("properties") or []
        if isinstance(prop, dict)
    }
    if "validated" in statuses:
        status = "validated"
    elif "provisional" in statuses:
        status = "provisional"
    else:
        status = "reported"
    record_id = source_id or record.get("id") or "unknown"
    return physical_reference(
        float(value),
        source=f"librapa_database:{record_id}",
        scope=str(summary.get("scope") or ""),
        status=status,
    )


def judge(reference: Reference, value: float, tolerance: float) -> dict[str, Any]:
    delta = value - reference.value
    return {
        "reference": reference.to_dict(),
        "value_ev": value,
        "reference_ev": reference.value,
        "delta_ev": delta,
        "tolerance_ev": tolerance,
        "pass": abs(delta) <= tolerance,
    }


def verdict(
    *,
    gates_ok: bool,
    value: float | None,
    references: Sequence[Reference],
    tolerance: float = 0.2,
) -> dict[str, Any]:
    """Return the strongest claim the evidence supports."""
    if not gates_ok:
        return {"verdict": "REJECTED_GATES", "reason": "policy or analysis gates failed"}
    if value is None:
        return {"verdict": "INCONCLUSIVE", "reason": "no produced value"}
    physical = sorted(
        (reference for reference in references if reference.kind == "physical"),
        key=lambda reference: STATUS_PRIORITY.get(reference.status, 9),
    )
    if physical:
        check = judge(physical[0], value, tolerance)
        if check["pass"]:
            claim = "ACCEPTED_PHYSICAL" if physical[0].status == "validated" else "ACCEPTED_REFERENCE"
        else:
            claim = "REJECTED_PHYSICAL"
        return {"verdict": claim, "check": check, "reference": physical[0].to_dict()}
    replay = [reference for reference in references if reference.kind == "replay"]
    if replay:
        check = judge(replay[0], value, tolerance)
        claim = "REPRODUCED_REPLAY" if check["pass"] else "REJECTED_REPLAY"
        return {"verdict": claim, "check": check, "reference": replay[0].to_dict()}
    return {"verdict": "INCONCLUSIVE", "reason": "no reference of any class was supplied"}
