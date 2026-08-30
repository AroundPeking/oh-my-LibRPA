from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .provenance import digest_json


ROUTE_MUTATION_AXES = {
    "periodic_3d_gw": frozenset(
        {
            "nfreq",
            "nbands",
            "screening_kgrid",
            "nao_family",
            "abfs_family",
            "shrink_threshold",
        }
    ),
    "strict_2d_gw": frozenset(
        {"nfreq", "nbands", "in_plane_kgrid", "vacuum", "ewald_precision"}
    ),
    "molecular_delta_st_rpa": frozenset(
        {"box_size", "nfreq", "grid_cutoff", "pca_threshold", "occupied_basis"}
    ),
    "solid_delta_st_rpa": frozenset(
        {"grid_cutoff", "nfreq", "pca_threshold", "coulomb_metric", "kq_sampling"}
    ),
}


class EvolutionError(ValueError):
    """Raised when a candidate violates controlled-evolution policy."""


def _non_negative_number(value: object, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise EvolutionError(f"{label} must be a non-negative number")


@dataclass(frozen=True)
class EvolutionBudget:
    max_candidates: int
    cpu_hours: float
    wall_seconds: int
    disk_bytes: int

    def __post_init__(self) -> None:
        if isinstance(self.max_candidates, bool) or not isinstance(self.max_candidates, int):
            raise EvolutionError("budget.max_candidates must be a positive integer")
        if self.max_candidates <= 0:
            raise EvolutionError("budget.max_candidates must be a positive integer")
        for name in ("cpu_hours", "wall_seconds", "disk_bytes"):
            value = getattr(self, name)
            _non_negative_number(value, f"budget.{name}")
            if value == 0:
                raise EvolutionError(f"budget.{name} must be positive")


@dataclass(frozen=True)
class EvolutionUsage:
    candidates: int = 0
    cpu_hours: float = 0.0
    wall_seconds: int = 0
    disk_bytes: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.candidates, bool) or not isinstance(self.candidates, int):
            raise EvolutionError("usage.candidates must be a non-negative integer")
        for name in ("candidates", "cpu_hours", "wall_seconds", "disk_bytes"):
            _non_negative_number(getattr(self, name), f"usage.{name}")


@dataclass(frozen=True)
class CandidateProposal:
    route_id: str
    changed_axis: str
    baseline_digest: str
    definition_digest: str
    candidate: dict[str, Any]
    status: str = "PROPOSAL_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), sort_keys=True))


def _check_budget(budget: EvolutionBudget, usage: EvolutionUsage) -> None:
    exhausted = []
    if usage.candidates >= budget.max_candidates:
        exhausted.append("candidates")
    if usage.cpu_hours >= budget.cpu_hours:
        exhausted.append("cpu_hours")
    if usage.wall_seconds >= budget.wall_seconds:
        exhausted.append("wall_seconds")
    if usage.disk_bytes >= budget.disk_bytes:
        exhausted.append("disk_bytes")
    if exhausted:
        raise EvolutionError(f"evolution budget exhausted: {', '.join(exhausted)}")


def _changed_axes(
    baseline: dict[str, object],
    candidate: dict[str, object],
) -> tuple[str, ...]:
    keys = set(baseline) | set(candidate)
    return tuple(sorted(key for key in keys if baseline.get(key) != candidate.get(key)))


def propose_candidate(
    *,
    route_id: str,
    baseline: dict[str, object],
    candidate: dict[str, object],
    existing_definition_digests: frozenset[str],
    budget: EvolutionBudget,
    usage: EvolutionUsage,
) -> CandidateProposal:
    try:
        registered_axes = ROUTE_MUTATION_AXES[route_id]
    except KeyError as exc:
        raise EvolutionError(f"route is not registered for controlled evolution: {route_id}") from exc
    if not isinstance(baseline, dict) or not baseline:
        raise EvolutionError("baseline must be a non-empty definition object")
    if not isinstance(candidate, dict) or not candidate:
        raise EvolutionError("candidate must be a non-empty definition object")
    _check_budget(budget, usage)

    changed = _changed_axes(baseline, candidate)
    if len(changed) != 1:
        raise EvolutionError("a candidate must change exactly one definition axis")
    changed_axis = changed[0]
    if changed_axis not in registered_axes:
        raise EvolutionError(
            f"changed axis is not registered for route {route_id}: {changed_axis}"
        )

    baseline_digest = digest_json({"route_id": route_id, "definition": baseline})
    definition_digest = digest_json({"route_id": route_id, "definition": candidate})
    if definition_digest in existing_definition_digests:
        raise EvolutionError(f"duplicate candidate definition: {definition_digest}")
    return CandidateProposal(
        route_id=route_id,
        changed_axis=changed_axis,
        baseline_digest=baseline_digest,
        definition_digest=definition_digest,
        candidate=json.loads(json.dumps(candidate, sort_keys=True)),
    )
