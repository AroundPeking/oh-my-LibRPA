from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .evolution import (
    ROUTE_MUTATION_AXES,
    CandidateProposal,
    EvolutionBudget,
    EvolutionError,
    EvolutionUsage,
    propose_candidate,
)
from .material_class import MATERIAL_CLASS_NAMES, MaterialClassError


PRESCRIPTION_SCHEMA = "oml.parameter-prescription.v1"
PACKAGED_PRESCRIPTION_ROOT = Path(__file__).with_name("parameter_prescriptions")


# System families are the lightweight, physics-level classification used for
# per-system INPUT PARAMETER selection. They are deliberately separate from the
# heavy material-class identity registry (which freezes PP/NAO hashes and a
# numerical reference): choosing parameters needs the physics of the system,
# not the frozen identity of one benchmark case.
#
# A prescription may therefore be keyed by a registered material class OR by a
# system family; material classes stay valid so existing identities keep working.
SYSTEM_FAMILIES: dict[str, str] = {
    "bulk_bn_gw": "Light-element wide-gap 3D insulator (hexagonal BN); no magnetic order.",
    "bulk_bn_soc_gw": "Light-element wide-gap 3D insulator with spin-orbit coupling (BN SOC variants).",
    "transition_metal_oxide_gw": "Correlated 3d transition-metal oxide (MnO2, NiO), spin-polarised.",
    "simple_semiconductor_gw": "Conventional sp semiconductor (Si, GaAs), no magnetic order.",
    "wide_gap_oxide_gw": "Closed-shell ionic wide-gap oxide (MgO).",
    "soc_semiconductor_gw": "Zinc-blende semiconductor with spin-orbit coupling (GaAs).",
    "isolated_molecule_rpa": "Isolated molecule in a box (H2O, H2, Li atom), molecular RPA/G0W0.",
}

# Which family each fast benchmark case belongs to. Used to pick the right
# prescription automatically from a case id.
CASE_ID_TO_FAMILY: dict[str, tuple[str, str]] = {
    "bn-3d-sym-shrink-g0w0": ("periodic_3d_gw", "bulk_bn_gw"),
    "bn-3d-shrink-g0w0": ("periodic_3d_gw", "bulk_bn_gw"),
    "bn-3d-headwing-g0w0": ("periodic_3d_gw", "bulk_bn_gw"),
    "bn-3d-soc-g0w0": ("periodic_3d_gw", "bulk_bn_soc_gw"),
    "bn-3d-headwing-shrink-soc-g0w0": ("periodic_3d_gw", "bulk_bn_soc_gw"),
    "mno2-nspin2-shrink-wing-g0w0": ("periodic_3d_gw", "transition_metal_oxide_gw"),
    "si-3d-aims-g0w0": ("periodic_3d_gw", "simple_semiconductor_gw"),
    "si-band-aims-g0w0": ("periodic_3d_gw", "simple_semiconductor_gw"),
    "gaas-3d-soc-wing-aims-g0w0": ("periodic_3d_gw", "soc_semiconductor_gw"),
    "mgo-3d-aims-g0w0": ("periodic_3d_gw", "wide_gap_oxide_gw"),
    "h2o-molecule-rpa": ("molecular_delta_st_rpa", "isolated_molecule_rpa"),
    "h2o-molecule-aims-g0w0": ("molecular_delta_st_rpa", "isolated_molecule_rpa"),
    "h2-molecule-aims-g0w0": ("molecular_delta_st_rpa", "isolated_molecule_rpa"),
    "li-atom-aims-g0w0": ("molecular_delta_st_rpa", "isolated_molecule_rpa"),
    "mos2-strict2d-sos-rpa-qavg": ("strict_2d_sos_rpa", "default"),
    "si-solid-delta-st-rpa": ("solid_delta_st_rpa", "default"),
}


class ParameterPrescriptionError(ValueError):
    """Raised when a parameter prescription is malformed or cannot be applied."""


@dataclass(frozen=True)
class ParameterRule:
    """A single tunable input parameter and how to pick a value for a system."""

    name: str
    default: Any
    allowed_range: tuple[Any, ...]
    target: Any
    per_system_override_rule: str
    rationale: str
    gate_id: str | None = None
    confidence: str = "established"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "default": self.default,
            "allowed_range": list(self.allowed_range),
            "target": self.target,
            "per_system_override_rule": self.per_system_override_rule,
            "rationale": self.rationale,
            "gate_id": self.gate_id,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class ParameterPrescription:
    route_id: str
    material_class: str
    description: str
    parameters: dict[str, ParameterRule]
    extends: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PRESCRIPTION_SCHEMA,
            "route_id": self.route_id,
            "material_class": self.material_class,
            "description": self.description,
            "extends": self.extends,
            "parameters": {name: rule.to_dict() for name, rule in self.parameters.items()},
        }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParameterPrescriptionError(f"cannot read prescription {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ParameterPrescriptionError(f"prescription root must be an object: {path}")
    return value


def _validate_parameter_rule(name: str, raw: Any) -> ParameterRule:
    if not isinstance(raw, dict):
        raise ParameterPrescriptionError(f"prescription parameter {name} must be an object")
    rule = raw.get("per_system_override_rule")
    if not isinstance(rule, str) or not rule:
        raise ParameterPrescriptionError(f"prescription parameter {name} lacks an override rule")
    rationale = raw.get("rationale")
    if not isinstance(rationale, str) or not rationale:
        raise ParameterPrescriptionError(f"prescription parameter {name} lacks a rationale")
    allowed_range = raw.get("allowed_range")
    if not isinstance(allowed_range, list) or not allowed_range:
        raise ParameterPrescriptionError(
            f"prescription parameter {name} must declare a non-empty allowed_range"
        )
    return ParameterRule(
        name=name,
        default=raw.get("default"),
        allowed_range=tuple(allowed_range),
        target=raw.get("target"),
        per_system_override_rule=rule,
        rationale=rationale,
        gate_id=raw.get("gate_id"),
        confidence=raw.get("confidence", "established"),
    )


def _validate_prescription(value: dict[str, Any]) -> None:
    if value.get("schema") != PRESCRIPTION_SCHEMA:
        raise ParameterPrescriptionError(
            f"prescription schema must be {PRESCRIPTION_SCHEMA}"
        )
    route_id = value.get("route_id")
    if not isinstance(route_id, str) or not route_id:
        raise ParameterPrescriptionError("prescription route_id must be a non-empty string")
    if route_id not in ROUTE_MUTATION_AXES:
        raise ParameterPrescriptionError(
            f"route is not registered for controlled evolution: {route_id}"
        )
    material_class = value.get("material_class")
    if not isinstance(material_class, str) or not material_class:
        raise ParameterPrescriptionError(
            "prescription material_class must be a non-empty string"
        )
    if (
        material_class != "default"
        and material_class not in MATERIAL_CLASS_NAMES
        and material_class not in SYSTEM_FAMILIES
    ):
        raise ParameterPrescriptionError(
            f"prescription material_class is not a registered material class or system family: "
            f"{material_class}"
        )
    parameters = value.get("parameters")
    if not isinstance(parameters, dict) or not parameters:
        raise ParameterPrescriptionError("prescription parameters must be a non-empty object")
    for name, raw in parameters.items():
        rule = _validate_parameter_rule(name, raw)
        if rule.name not in ROUTE_MUTATION_AXES[route_id]:
            raise ParameterPrescriptionError(
                f"prescription parameter {name} is not a registered mutation axis for {route_id}"
            )


def _prescription_path(route_id: str, material_class: str) -> Path:
    return PACKAGED_PRESCRIPTION_ROOT / f"{route_id}__{material_class}.json"


def _find_entries(route_id: str, material_class: str) -> list[dict[str, Any]]:
    """Return the prescription chain for (route_id, material_class) in resolution order.

    The chain walks from the most specific entry (material-class override) up to
    the route's 'default' entry, following the 'extends' pointer so a material
    entry can extend the route baseline. Returns entries most-specific-first.
    """
    if route_id not in ROUTE_MUTATION_AXES:
        raise ParameterPrescriptionError(
            f"route is not registered for controlled evolution: {route_id}"
        )
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_class = material_class
    while current_class is not None:
        path = _prescription_path(route_id, current_class)
        if not path.is_file():
            if current_class == material_class:
                raise ParameterPrescriptionError(
                    f"no prescription for route {route_id}, material_class {material_class}"
                )
            break
        entry = _load_json(path)
        _validate_prescription(entry)
        if entry["route_id"] != route_id:
            raise ParameterPrescriptionError(
                f"prescription {path} is for route {entry['route_id']}, not {route_id}"
            )
        chain.append(entry)
        extends = entry.get("extends")
        if extends is None:
            break
        if extends in seen:
            raise ParameterPrescriptionError(
                f"prescription extends cycle detected at {current_class}"
            )
        seen.add(current_class)
        current_class = extends
    return chain


def load_prescription(route_id: str, material_class: str = "default") -> ParameterPrescription:
    """Load and merge the prescription chain for a (route_id, material_class) pair.

    The most specific entry wins; parameters not overridden by a material entry
    fall back to the 'default' entry for that route.
    """
    chain = _find_entries(route_id, material_class)
    merged: dict[str, ParameterRule] = {}
    # chain is most-specific-first, so iterate reversed so base entries load first.
    for entry in reversed(chain):
        for name, raw in entry["parameters"].items():
            merged[name] = _validate_parameter_rule(name, raw)
    description = chain[0].get("description", "")
    return ParameterPrescription(
        route_id=route_id,
        material_class=material_class,
        description=description,
        parameters=merged,
        extends=chain[0].get("extends"),
    )


def _rule_value(rule: ParameterRule, value: Any) -> Any:
    return rule.default if value is None else value


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _within_range(rule: ParameterRule, value: Any) -> bool:
    """Whether ``value`` satisfies the rule's allowed_range.

    Three shapes are supported:
      * numeric bounds: ``[lo, hi]`` with scalar value;
      * component-wise bounds: ``[[lo...], [hi...]]`` with a same-length list value
        (e.g. a k-mesh ``[1,1,1] .. [8,8,8]``);
      * an explicit enum of allowed values (e.g. a basis family name).
    """
    allowed = rule.allowed_range
    if len(allowed) == 2:
        lo, hi = allowed
        if _is_number(lo) and _is_number(hi):
            return _is_number(value) and lo <= value <= hi
        if (
            isinstance(lo, list)
            and isinstance(hi, list)
            and len(lo) == len(hi)
            and all(_is_number(item) for item in lo)
            and all(_is_number(item) for item in hi)
            and isinstance(value, list)
            and len(value) == len(lo)
            and all(_is_number(item) for item in value)
        ):
            return all(
                low <= item <= high for item, low, high in zip(value, lo, hi)
            )
    return value in allowed


def _validate_value(rule: ParameterRule, value: Any) -> None:
    if value is None:
        return
    if not _within_range(rule, value):
        raise ParameterPrescriptionError(
            f"value for {rule.name} is outside the allowed range "
            f"{list(rule.allowed_range)}: {value!r}"
        )


def apply_prescription(
    route_id: str,
    material_class: str,
    *,
    definition: dict[str, object] | None = None,
) -> dict[str, Any]:
    """Return the prescription defaults for (route_id, material_class).

    If ``definition`` is given, each prescription rule is applied to it as an
    ``exx_cs_inv_thr``/``nbands``-style input override and the resulting definition
    is returned. This does NOT submit anything: it is a proposal-only helper.
    """
    prescription = load_prescription(route_id, material_class)
    if definition is None:
        return prescription.to_dict()
    if not isinstance(definition, dict):
        raise ParameterPrescriptionError("definition must be an object")
    result = dict(definition)
    applied: dict[str, Any] = {}
    for name, rule in prescription.parameters.items():
        # Only override a parameter when the prescription pins an explicit target.
        # A parameter whose target is None (e.g. nbands must equal nbasis, which is
        # system-dependent) is left untouched so the caller keeps the definition.
        if rule.target is None:
            continue
        value = rule.target
        _validate_value(rule, value)
        result[name] = value
        applied[name] = value
    return {"prescription": prescription.to_dict(), "definition": result, "applied": applied}


def list_system_families() -> tuple[str, ...]:
    """Return every registered system family used for parameter selection."""
    return tuple(SYSTEM_FAMILIES)


def resolve_prescription_keys(case_id: str) -> tuple[str, str] | None:
    """Map a fast-benchmark case id onto its (route, system_family) prescription key.

    Returns ``None`` when the case is not classified into a family, so callers
    can fall back to the route default instead of guessing.
    """
    mapped = CASE_ID_TO_FAMILY.get(case_id)
    if mapped is None:
        return None
    return mapped


def _default_budget() -> EvolutionBudget:
    return EvolutionBudget(
        max_candidates=4,
        cpu_hours=24.0,
        wall_seconds=86400,
        disk_bytes=10_000_000_000,
    )


def tune_parameter(
    *,
    route_id: str,
    material_class: str,
    baseline: dict[str, object],
    axis: str,
    value: Any,
    budget: EvolutionBudget | None = None,
    usage: EvolutionUsage | None = None,
) -> CandidateProposal:
    """Propose a one-axis parameter change for a (route_id, material_class) pair.

    This reuses ``evolution.propose_candidate``'s controlled one-axis mutation
    semantics, so the candidate is proposal-only (never auto-submitted). The
    prescribed allowed range for ``axis`` is enforced before the proposal is made.
    """
    prescription = load_prescription(route_id, material_class)
    rule = prescription.parameters.get(axis)
    if rule is None:
        raise ParameterPrescriptionError(
            f"axis {axis} is not prescribed for route {route_id}, material_class {material_class}"
        )
    _validate_value(rule, value)
    candidate = dict(baseline)
    candidate[axis] = value
    return propose_candidate(
        route_id=route_id,
        baseline=baseline,
        candidate=candidate,
        existing_definition_digests=frozenset(),
        budget=budget or _default_budget(),
        usage=usage or EvolutionUsage(),
    )
