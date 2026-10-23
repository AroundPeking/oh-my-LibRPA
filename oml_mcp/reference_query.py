"""Read-only lookup of archived LibRPA-database records by structure identity.

The database is the durable experience store: a campaign may reuse the
parameters of an archived case only when the structure fingerprint matches and
the record passes the trust gate below. Similarity alone never justifies
copying parameters (see the project's experience-capture policy).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRUSTED_RECORD_TYPES = frozenset({"band", "rpa_energy", "large_system_gw", "reader_conversion"})
AUXILIARY_REQUIRED_TYPES = frozenset({"band", "rpa_energy", "large_system_gw"})
AUXILIARY_MODES = frozenset({"pca_generated", "prebuilt_abfs_pca"})


class ReferenceQueryError(ValueError):
    """Raised when the reference database cannot be read."""


@dataclass(frozen=True)
class ReferenceCandidate:
    record_id: str
    path: Path
    material: str
    record_type: str
    dimension: str
    structure_sha256: str
    trustworthy: bool
    reasons: tuple[str, ...]
    species: tuple[dict[str, Any], ...]
    auxiliary_basis: dict[str, Any] | None
    software: dict[str, Any]
    inputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "path": str(self.path),
            "material": self.material,
            "record_type": self.record_type,
            "dimension": self.dimension,
            "structure_sha256": self.structure_sha256,
            "trustworthy": self.trustworthy,
            "reasons": list(self.reasons),
            "species": list(self.species),
            "auxiliary_basis": self.auxiliary_basis,
            "software": self.software,
            "inputs": list(self.inputs),
        }


def load_records(root: str | Path) -> tuple[tuple[dict[str, Any], Path], ...]:
    """Load every ``record.json`` under ``data/calculations``."""
    root = Path(root)
    calculations = root / "data" / "calculations"
    if not calculations.is_dir():
        raise ReferenceQueryError(f"reference database has no data/calculations directory: {calculations}")
    records: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(calculations.glob("*/*/*/record.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReferenceQueryError(f"cannot read reference record {path}: {exc}") from exc
        if isinstance(value, dict):
            records.append((value, path))
    return tuple(records)


def _software_identity(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("commit") or entry.get("executable_sha256"):
        return True
    return bool(entry.get("missing_reason"))


def trust_reasons(record: dict[str, Any]) -> tuple[str, ...]:
    """Return why a record cannot lend parameters; an empty tuple means trusted."""
    reasons: list[str] = []
    identity = record.get("structure_identity")
    if not isinstance(identity, dict) or identity.get("algorithm") != "cell-sites-v1" or not identity.get("sha256"):
        reasons.append("structure identity is missing or not cell-sites-v1")
    properties = record.get("properties") or []
    validated = [
        item
        for item in properties
        if isinstance(item, dict) and str(item.get("status", "")).lower() == "validated"
    ]
    if not validated:
        reasons.append("no validated property")
    software = record.get("software") or {}
    for code in ("abacus", "frontend", "librpa"):
        if code in software and not _software_identity(software.get(code)):
            reasons.append(f"software identity is incomplete for {code}")
    if "abacus" not in software and "frontend" not in software:
        reasons.append("producer software identity is missing")
    if "librpa" not in software:
        reasons.append("libRPA software identity is missing")
    record_type = record.get("record_type")
    if record_type in AUXILIARY_REQUIRED_TYPES:
        auxiliary = record.get("auxiliary_basis")
        if (
            not isinstance(auxiliary, dict)
            or auxiliary.get("mode") not in AUXILIARY_MODES
            or not isinstance(auxiliary.get("threshold"), (int, float))
        ):
            reasons.append("auxiliary-basis provenance is not recorded")
    species = record.get("species") or []
    if not species or any(
        not isinstance(item, dict) or not item.get("set_id") for item in species
    ):
        reasons.append("species set ids are incomplete")
    return tuple(reasons)


def find_reference_records(
    root: str | Path,
    *,
    structure_sha256: str,
    record_type: str | None = None,
    limit: int = 10,
) -> tuple[ReferenceCandidate, ...]:
    """Return archived records with the same structure fingerprint, trusted first."""
    candidates: list[ReferenceCandidate] = []
    for record, path in load_records(root):
        identity = record.get("structure_identity") or {}
        if identity.get("sha256") != structure_sha256:
            continue
        if record_type is not None and record.get("record_type") != record_type:
            continue
        reasons = trust_reasons(record)
        inputs = tuple(
            str(item.get("path"))
            for item in (record.get("files") or {}).get("inputs", [])
            if isinstance(item, dict) and item.get("path")
        )
        candidates.append(
            ReferenceCandidate(
                record_id=str(record.get("id") or path.parent.name),
                path=path,
                material=str(record.get("material") or path.parent.parent.name),
                record_type=str(record.get("record_type") or ""),
                dimension=str(record.get("dimension") or path.parent.parent.parent.name),
                structure_sha256=str(identity.get("sha256")),
                trustworthy=not reasons,
                reasons=reasons,
                species=tuple(item for item in (record.get("species") or []) if isinstance(item, dict)),
                auxiliary_basis=record.get("auxiliary_basis") if isinstance(record.get("auxiliary_basis"), dict) else None,
                software=record.get("software") if isinstance(record.get("software"), dict) else {},
                inputs=inputs,
            )
        )
    candidates.sort(key=lambda candidate: (not candidate.trustworthy, candidate.record_id))
    return tuple(candidates[:limit])
