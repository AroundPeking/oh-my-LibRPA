from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal


GateStatus = Literal["PASS", "WARN", "FAIL", "SKIP"]
VALID_GATE_STATUSES = frozenset({"PASS", "WARN", "FAIL", "SKIP"})


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_compatible(item) for item in value]
    if isinstance(value, list):
        return [_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class InputEntry:
    key: str
    value: str
    line: int


@dataclass(frozen=True)
class InputDocument:
    path: Path
    syntax: str
    entries: tuple[InputEntry, ...]

    def value(self, key: str, default: str | None = None) -> str | None:
        normalized = key.lower()
        for entry in reversed(self.entries):
            if entry.key == normalized:
                return entry.value
        return default

    def values(self, key: str) -> tuple[str, ...]:
        normalized = key.lower()
        return tuple(entry.value for entry in self.entries if entry.key == normalized)

    def lines(self, key: str) -> tuple[int, ...]:
        normalized = key.lower()
        return tuple(entry.line for entry in self.entries if entry.key == normalized)

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(entry.key for entry in self.entries))

    @property
    def duplicates(self) -> tuple[str, ...]:
        counts: dict[str, int] = {}
        for entry in self.entries:
            counts[entry.key] = counts.get(entry.key, 0) + 1
        return tuple(key for key in self.keys if counts[key] > 1)

    def to_dict(self) -> dict[str, Any]:
        return _json_compatible(asdict(self))


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: GateStatus
    message: str
    evidence: tuple[str, ...] = ()
    repair: str | None = None
    measurements: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.status not in VALID_GATE_STATUSES:
            raise ValueError(f"invalid gate status: {self.status}")
        if self.status in {"WARN", "FAIL"}:
            if not self.evidence:
                raise ValueError(f"{self.status} gate requires evidence")
            if not self.repair:
                raise ValueError(f"{self.status} gate requires a repair action")

    def to_dict(self) -> dict[str, Any]:
        return _json_compatible(asdict(self))


@dataclass(frozen=True)
class ValidationReport:
    profile_id: str
    gates: tuple[GateResult, ...]

    @property
    def accepted(self) -> bool:
        return all(gate.status != "FAIL" for gate in self.gates)

    def to_dict(self) -> dict[str, Any]:
        counts = {status: 0 for status in ("PASS", "WARN", "FAIL", "SKIP")}
        for gate in self.gates:
            counts[gate.status] += 1
        return {
            "profile_id": self.profile_id,
            "accepted": self.accepted,
            "counts": counts,
            "gates": [gate.to_dict() for gate in self.gates],
        }


@dataclass(frozen=True)
class ArtifactInfo:
    path: Path
    artifact_type: str
    format_version: str
    size: int
    metadata: dict[str, Any]
    gates: tuple[GateResult, ...] = ()

    @property
    def accepted(self) -> bool:
        return all(gate.status != "FAIL" for gate in self.gates)

    def to_dict(self) -> dict[str, Any]:
        data = _json_compatible(asdict(self))
        data["accepted"] = self.accepted
        return data


@dataclass(frozen=True)
class IntakeReport:
    source_path: Path
    stack: str
    files: tuple[dict[str, Any], ...]
    markers: tuple[str, ...]
    gates: tuple[GateResult, ...] = ()

    @property
    def accepted(self) -> bool:
        return all(gate.status != "FAIL" for gate in self.gates)

    def to_dict(self) -> dict[str, Any]:
        data = _json_compatible(asdict(self))
        data["accepted"] = self.accepted
        return data


@dataclass(frozen=True)
class CasePlan:
    plan_id: str
    digest: str
    source_digest: str
    route: str
    stages: tuple[str, ...]
    profile_id: str
    options: dict[str, Any]
    source_manifest: tuple[dict[str, Any], ...]
    assumptions: tuple[str, ...]
    gates: tuple[GateResult, ...] = ()

    @property
    def accepted(self) -> bool:
        return all(gate.status != "FAIL" for gate in self.gates)

    def to_dict(self) -> dict[str, Any]:
        data = _json_compatible(asdict(self))
        data["accepted"] = self.accepted
        return data
