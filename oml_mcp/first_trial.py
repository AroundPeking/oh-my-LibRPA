"""Assemble the first-trial parameter definition for a case.

The first trial combines three already-validated sources: the route/material
prescription defaults, the content-addressed PP/NAO/ABFS sets from the
LibRPA-database element library, and the physical basis dimension from the
``.orb`` headers (``nbands = nbasis``). If a trusted archived record shares the
structure fingerprint, it is returned alongside the definition as a reference;
it is never applied silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .basis_registry import (
    BasisRegistryError,
    load_registry,
    resolve_set,
    stage_element_sets,
)
from .orbital_info import basis_dimension
from .parameter_prescriptions import load_prescription
from .reference_query import find_reference_records
from .stru import atom_counts, species, structure_fingerprint


@dataclass(frozen=True)
class FirstTrial:
    definition: dict[str, Any]
    basis: dict[str, dict[str, Any]]
    nbasis: int
    atom_counts: dict[str, int]
    structure_sha256: str
    site_count: int
    references: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "definition": dict(self.definition),
            "basis": {element: dict(value) for element, value in self.basis.items()},
            "nbasis": self.nbasis,
            "atom_counts": dict(self.atom_counts),
            "structure_sha256": self.structure_sha256,
            "site_count": self.site_count,
            "references": list(self.references),
        }


def prescription_defaults(route: str, material_class: str = "default") -> dict[str, Any]:
    """Return the route prescription's default/target value per parameter."""
    prescription = load_prescription(route, material_class)
    definition: dict[str, Any] = {}
    for name, rule in prescription.parameters.items():
        value = rule.target if rule.target is not None else rule.default
        if value is not None:
            definition[name] = value
    return definition


def build_first_trial(
    case_root: str | Path,
    *,
    route: str,
    registry_root: str | Path,
    dimension: str,
    material_class: str = "default",
    soc: bool = False,
    family: str | None = None,
    require_abf: bool = False,
    reference_root: str | Path | None = None,
    stage_dir: str | Path | None = None,
) -> FirstTrial:
    """Resolve basis files, compute ``nbands = nbasis``, and return the definition."""
    case_root = Path(case_root)
    stru_path = case_root / "STRU"
    try:
        stru_text = stru_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BasisRegistryError(f"cannot read case STRU {stru_path}: {exc}") from exc

    species_entries = species(stru_text)
    elements = [entry[0] for entry in species_entries]
    counts = atom_counts(stru_text)
    registry = load_registry(registry_root)
    staged = (
        stage_element_sets(
            registry,
            elements,
            destination=stage_dir,
            family=family,
            require_abf=require_abf,
        )
        if stage_dir is not None
        else None
    )

    basis: dict[str, dict[str, Any]] = {}
    nbasis = 0
    for element in elements:
        element_set = resolve_set(registry, element, family=family, require_abf=require_abf)
        nao = element_set.asset("nao")
        pp = element_set.asset("pp")
        abf = element_set.asset("abf")
        assert nao is not None and pp is not None  # enforced by the registry loader
        per_atom = basis_dimension(nao.path, soc=soc)
        nbasis += per_atom * counts.get(element, 0)
        record: dict[str, Any] = {
            "set_id": element_set.set_id,
            "family": element_set.family,
            "pp_file": (staged or {}).get(element, {}).get("pp", pp.path.name),
            "nao_file": (staged or {}).get(element, {}).get("nao", nao.path.name),
            "abf_file": ((staged or {}).get(element, {}).get("abf") or (abf.path.name if abf else None)),
            "pp_sha256": pp.sha256,
            "nao_sha256": nao.sha256,
            "abf_sha256": abf.sha256 if abf else None,
            "dimension_per_atom": per_atom,
            "atom_count": counts.get(element, 0),
            "source_path": str(nao.path),
        }
        basis[element] = record

    definition = prescription_defaults(route, material_class)
    definition["nbands"] = nbasis

    structure_sha256, site_count = structure_fingerprint(stru_text, dimension=dimension)
    references: tuple[dict[str, Any], ...] = ()
    if reference_root is not None:
        references = tuple(
            candidate.to_dict()
            for candidate in find_reference_records(
                reference_root, structure_sha256=structure_sha256
            )
        )

    return FirstTrial(
        definition=definition,
        basis=basis,
        nbasis=nbasis,
        atom_counts=dict(counts),
        structure_sha256=structure_sha256,
        site_count=site_count,
        references=references,
    )
