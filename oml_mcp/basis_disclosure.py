"""Report exactly which PP/NAO/ABFS a run will use, before it runs.

The basis is a scientific decision, not a lookup detail: two element sets differ
in pseudopotential family, NAO size and auxiliary basis, and the resulting gap
can differ by an eV. Twenty-three of the thirty-two elements in the shipped
database library have more than one usable set (19 once an auxiliary basis is
required), so "take the first one" is never safe.

This module therefore builds one machine-readable disclosure per prepared run:

* which element set each species came from, including the database set id and
  the set's recorded validation scope when the payloads hash-match a set;
* every payload's file name, SHA-256 and size;
* the NAO shell string and basis dimension per atom, and the ABF channel counts
  and auxiliary dimension per atom;
* the totals for the actual structure (``nbasis``, ``naux``).

The disclosure is written to ``.oml/basis.json`` inside the immutable run and is
covered by the run manifest, so a run that changes its basis after preparation
cannot keep an acknowledgement. Submission requires an acknowledgement whose
digest equals the disclosure digest; OML never answers the question for the
user.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .basis_label import (
    BasisLabelError,
    historical_uses,
    label_for_set,
    payload_facts,
)
from .basis_registry import ElementSet, file_sha256
from .orbital_info import OrbitalInfoError, parse_orbital_header
from .stru import StruError, atom_counts, sections, species

DISCLOSURE_SCHEMA_VERSION = 1
DISCLOSURE_RELATIVE_PATH = Path(".oml") / "basis.json"


class BasisDisclosureError(ValueError):
    """Raised when the run's basis cannot be described without guessing."""


def _orbital_block(text: str, name: str) -> list[str]:
    entries = [line.split()[0] for line in sections(text).get(name, []) if line.split()]
    return entries


def _match_database_set(
    registry: Mapping[str, tuple[ElementSet, ...]] | None,
    element: str,
    hashes: Mapping[str, str],
) -> tuple[ElementSet | None, str | None]:
    """Return the one database set these payloads hash-match, or say why not.

    A set is matched only when its roles and the run's roles agree. Testing
    "every role of the set is present" is not enough: a pp+NAO set is a subset
    of a pp+NAO+ABFS run, so a three-role run would match both and the answer
    would depend on iteration order. When several sets still match exactly, the
    provenance is genuinely ambiguous and the caller reports that instead of
    picking one.
    """
    if registry is None:
        return None, "no basis library was supplied, so no set can be identified"
    observed = set(hashes)
    exact: list[ElementSet] = []
    for candidate in registry.get(element, ()):
        roles = {role: asset.sha256 for role, asset in candidate.files.items()}
        if not roles:
            continue
        if set(roles) != observed:
            continue
        if all(hashes[role] == digest for role, digest in roles.items()):
            exact.append(candidate)
    if len(exact) == 1:
        return exact[0], None
    if len(exact) > 1:
        return None, (
            "several database sets have these exact payload hashes: "
            + ", ".join(item.set_id for item in exact)
        )
    partial = []
    for candidate in registry.get(element, ()):
        roles = {role: asset.sha256 for role, asset in candidate.files.items()}
        if not roles or not set(roles) <= observed:
            continue
        if all(hashes[role] == digest for role, digest in roles.items()):
            partial.append((len(roles), candidate.set_id, candidate))
    if partial:
        best = max(item[0] for item in partial)
        leaders = [item for item in partial if item[0] == best]
        if len(leaders) == 1:
            return leaders[0][2], (
                f"only the {best}-role part of this set matches; the run also carries "
                + ", ".join(sorted(observed - set(leaders[0][2].files)))
                + " that the set does not record"
            )
        return None, (
            "several database sets partially match: "
            + ", ".join(item[1] for item in leaders)
        )
    return None, "no database set has these payload hashes"


def build_basis_disclosure(
    run_dir: str | Path,
    *,
    registry: Mapping[str, tuple[ElementSet, ...]] | None = None,
    records: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    soc: bool = False,
) -> dict[str, Any]:
    """Describe the basis a run directory will actually submit, or raise.

    Every file is read from the run directory itself after STRU rewriting, so a
    database override and a case-bundled payload are described the same way and
    cannot disagree with what the solver will open.
    """
    root = Path(run_dir)
    stru_path = root / "STRU"
    try:
        text = stru_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BasisDisclosureError(f"cannot read {stru_path}: {exc}") from exc
    warnings: list[str] = []
    try:
        species_entries = species(text)
    except StruError as exc:
        raise BasisDisclosureError(f"cannot parse {stru_path}: {exc}") from exc
    try:
        counts = atom_counts(text)
    except StruError as exc:
        # The per-atom basis size is still reportable, and it is the part the
        # decision needs; the structure totals are not. Degrade rather than
        # refuse, but say so in the disclosure instead of shipping a silent
        # zero.
        counts = {}
        warnings.append(f"atom counts unavailable: {exc}")

    numerical = _orbital_block(text, "NUMERICAL_ORBITAL")
    auxiliary = _orbital_block(text, "ABFS_ORBITAL")
    elements = [entry[0] for entry in species_entries]
    if numerical and len(numerical) != len(elements):
        raise BasisDisclosureError(
            f"NUMERICAL_ORBITAL lists {len(numerical)} files for {len(elements)} species"
        )
    if auxiliary and len(auxiliary) != len(elements):
        raise BasisDisclosureError(
            f"ABFS_ORBITAL lists {len(auxiliary)} files for {len(elements)} species"
        )

    per_element: dict[str, Any] = {}
    total_basis = 0
    total_aux = 0
    total_atoms = 0
    missing_auxiliary: list[str] = []
    unmatched: list[str] = []

    for index, (element, mass, pp_name) in enumerate(species_entries):
        entry: dict[str, Any] = {
            "element": element,
            "mass": mass,
            "atom_count": counts.get(element, 0),
            "payloads": {},
        }
        hashes: dict[str, str] = {}
        roles: list[tuple[str, str]] = [("pp", pp_name)]
        if numerical:
            roles.append(("nao", numerical[index]))
        if auxiliary:
            roles.append(("abf", auxiliary[index]))
        for role, name in roles:
            path = root / name
            if not path.is_file():
                raise BasisDisclosureError(
                    f"{element}/{role}: declared payload {name} is missing from the run directory"
                )
            digest = file_sha256(path)
            hashes[role] = digest
            payload: dict[str, Any] = {
                "file_name": name,
                "sha256": digest,
                "size_bytes": path.stat().st_size,
            }
            # Sizes come from the bytes that will actually be read. The library
            # index disagrees with its own files for 60 auxiliary bases (it omits
            # the J/K channels), so quoting the index would misreport the basis.
            try:
                facts = payload_facts(path, role)
            except BasisLabelError as exc:
                raise BasisDisclosureError(f"{element}/{role}: {exc}") from exc
            for key in ("valence_electrons", "shells", "channels", "dimension_per_atom"):
                if key in facts:
                    payload[key] = facts[key]
            entry["payloads"][role] = payload

        database_set, match_note = _match_database_set(registry, element, hashes)
        if database_set is None:
            entry["provenance"] = {
                "source": "run-bundled",
                "set_id": None,
                "family": None,
                "validation_scope": None,
                "matched_database_set": False,
                "match_note": match_note,
                "note": (
                    "these payloads are not identified as one database element set; "
                    "treat the provenance as the case bundle rather than a database record"
                ),
            }
            unmatched.append(element)
        else:
            entry["provenance"] = {
                "source": "LibRPA-database",
                "set_id": database_set.set_id,
                "family": database_set.family,
                "validation_scope": database_set.validation_scope,
                "matched_database_set": True,
                "match_note": match_note,
                "set_source": dict(database_set.source or {}),
            }

        nao = entry["payloads"].get("nao")
        abf = entry["payloads"].get("abf")
        per_atom = int(nao["dimension_per_atom"]) if nao else None
        aux_per_atom = int(abf["dimension_per_atom"]) if abf else None
        entry["basis_dimension_per_atom"] = per_atom
        entry["auxiliary_dimension_per_atom"] = aux_per_atom
        atoms = entry["atom_count"]
        total_atoms += atoms
        if per_atom is not None:
            entry["basis_dimension_total"] = per_atom * atoms
            total_basis += per_atom * atoms
        else:
            entry["basis_dimension_total"] = None
        if aux_per_atom is not None:
            entry["auxiliary_dimension_total"] = aux_per_atom * atoms
            total_aux += aux_per_atom * atoms
        else:
            entry["auxiliary_dimension_total"] = None
            missing_auxiliary.append(element)
        entry["label"] = label_for_set(
            element,
            valence=entry["payloads"].get("pp", {}).get("valence_electrons"),
            nao=entry["payloads"].get("nao"),
            abf=entry["payloads"].get("abf"),
            uses=historical_uses(records, (entry["provenance"] or {}).get("set_id")),
            atom_count=atoms or None,
        )
        entry["label_sentence"] = entry["label"]["sentence"]
        per_element[element] = entry

    complete = bool(total_basis) and not missing_auxiliary and bool(counts)
    if not counts:
        warnings.append(
            "STRU has no readable ATOMIC_POSITIONS, so the atom counts and the total "
            "basis dimension are unknown"
        )
    elif not total_basis:
        warnings.append(
            "no NUMERICAL_ORBITAL payload could be sized, so the basis dimension is unknown"
        )

    return {
        "schema_version": DISCLOSURE_SCHEMA_VERSION,
        # INCOMPLETE means OML could not describe the basis, which is itself a
        # reason to stop: an undisclosed basis is exactly what must not be
        # submitted.
        "status": "DECLARED_NOT_YET_APPROVED" if complete else "INCOMPLETE",
        "policy": (
            "OML reports the basis and stops. It does not choose a pseudopotential "
            "family, an orbital set or an auxiliary basis, and it will not submit a "
            "stage until a human acknowledges this exact disclosure."
        ),
        "structure": {
            "atom_count": total_atoms,
            "species": [
                {
                    "element": element,
                    "atom_count": counts.get(element, 0),
                    "pseudopotential": pp_name,
                }
                for element, _, pp_name in species_entries
            ],
            "soc": soc,
        },
        "elements": per_element,
        "warnings": warnings,
        "totals": {
            "nbasis": total_basis or None,
            "naux": (total_aux or None) if not missing_auxiliary else None,
            "missing_auxiliary_elements": missing_auxiliary,
            "elements_without_database_set": unmatched,
        },
    }


# Fields that are added after the digest is computed and therefore must not be
# part of it; otherwise re-reading the file would produce a different digest
# than the one written into it.
_VOLATILE_FIELDS = ("acknowledgement", "digest")


def disclosure_digest(disclosure: Mapping[str, Any]) -> str:
    """Digest of the disclosure content, excluding fields added after hashing."""
    payload = {
        key: value for key, value in disclosure.items() if key not in _VOLATILE_FIELDS
    }
    from .provenance import digest_json

    return digest_json(payload)


def format_basis_disclosure(disclosure: Mapping[str, Any]) -> str:
    """Render the disclosure the way a person reads it: what, how big, what for.

    The ids come last and are labelled as ids. A user deciding between two
    element sets needs the valence count, the basis size and what the set has
    already produced; the hash suffix on a family name is bookkeeping.
    """
    lines: list[str] = []
    structure = disclosure.get("structure", {})
    lines.append(
        f"Basis disclosure for {structure.get('atom_count', '?')} atoms"
        + (" (SOC)" if structure.get("soc") else "")
    )
    lines.append("")
    for element, entry in disclosure.get("elements", {}).items():
        label = entry.get("label") or {}
        if label.get("sentence"):
            lines.append(f"  {label['sentence']}")
        else:
            lines.append(
                f"  {element}: {entry.get('atom_count')} atom(s), "
                f"{entry.get('basis_dimension_per_atom')} basis functions/atom"
            )
        provenance = entry.get("provenance", {})
        payloads = entry.get("payloads", {})
        pp = payloads.get("pp")
        nao = payloads.get("nao")
        abf = payloads.get("abf")
        lines.append(
            "    files: "
            + ", ".join(
                value
                for value in (
                    f"PP {pp['file_name']}" if pp else None,
                    f"NAO {nao['file_name']}" if nao else None,
                    f"ABF {abf['file_name']}" if abf else "no ABF",
                )
                if value
            )
        )
        if provenance.get("matched_database_set"):
            lines.append(
                f"    from: LibRPA-database set {provenance.get('set_id')} "
                f"(family {provenance.get('family')!r})"
            )
        else:
            lines.append(
                "    from: the case bundle (these payloads are not one database set)"
            )
        for role, payload in (("PP", pp), ("NAO", nao), ("ABF", abf)):
            if not payload:
                continue
            digest = (payload.get("sha256") or "")[:16]
            extra = payload.get("shells")
            lines.append(
                f"    {role} sha256 {digest}…"
                + (f"  shells {extra}" if extra else "")
            )
        lines.append(
            f"    this structure: {entry.get('basis_dimension_total')} orbital functions"
            + (
                f", {entry.get('auxiliary_dimension_total')} auxiliary functions"
                if entry.get("auxiliary_dimension_total") is not None
                else ", no auxiliary basis"
            )
        )
        for use in label.get("uses") or []:
            result = use.get("result") or "no reported number"
            lines.append(
                f"    used by {use.get('record_id')} ({use.get('material')}, "
                f"{use.get('dimension')}): {result}"
            )
        lines.append("")
    totals = disclosure.get("totals", {})
    lines.append(
        f"Totals: nbasis = {totals.get('nbasis')}, naux = {totals.get('naux')}"
    )
    if totals.get("missing_auxiliary_elements"):
        lines.append(
            "  no auxiliary basis for: "
            + ", ".join(totals["missing_auxiliary_elements"])
            + " (shrink/ABFS stages will not have one)"
        )
    if totals.get("elements_without_database_set"):
        lines.append(
            "  not one database set: "
            + ", ".join(totals["elements_without_database_set"])
        )
    lines.append("")
    lines.append(f"disclosure digest: {disclosure.get('digest', '(not yet computed)')}")
    return "\n".join(lines)


def write_disclosure(run_dir: str | Path, disclosure: Mapping[str, Any]) -> Path:
    """Write ``.oml/basis.json`` and return its path."""
    path = Path(run_dir) / DISCLOSURE_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(disclosure, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def read_disclosure(run_dir: str | Path) -> dict[str, Any] | None:
    path = Path(run_dir) / DISCLOSURE_RELATIVE_PATH
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BasisDisclosureError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BasisDisclosureError(f"{path}: disclosure must be a JSON object")
    return value


def summarise_disclosure(disclosure: Mapping[str, Any]) -> str:
    """One-paragraph statement of where the basis comes from and how big it is."""
    parts: list[str] = []
    totals = disclosure.get("totals", {})
    structure = disclosure.get("structure", {})
    for element, entry in disclosure.get("elements", {}).items():
        provenance = entry.get("provenance", {})
        payloads = entry.get("payloads", {})
        nao = payloads.get("nao") or {}
        abf = payloads.get("abf") or {}
        origin = (
            f"database set {provenance.get('set_id')}"
            if provenance.get("matched_database_set")
            else "run-bundled files (no single database set matches)"
        )
        parts.append(
            f"{element} x{entry.get('atom_count')}: {origin}; "
            f"PP {payloads.get('pp', {}).get('file_name')}; "
            f"NAO {nao.get('file_name')} {nao.get('shells')} "
            f"({nao.get('dimension_per_atom')}/atom); "
            f"ABF {abf.get('file_name', 'none')}"
            + (
                f" {abf.get('shells')} ({abf.get('dimension_per_atom')}/atom)"
                if abf
                else ""
            )
        )
    return (
        f"{structure.get('atom_count', '?')} atoms, "
        f"nbasis={totals.get('nbasis')}, naux={totals.get('naux')}. "
        + " | ".join(parts)
    )


def iter_fingerprints(disclosure: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield one flat record per (element, role) for compact reporting."""
    for element, entry in disclosure.get("elements", {}).items():
        for role, payload in entry.get("payloads", {}).items():
            yield {
                "element": element,
                "role": role,
                "file_name": payload.get("file_name"),
                "sha256": payload.get("sha256"),
                "size_bytes": payload.get("size_bytes"),
                "set_id": (entry.get("provenance") or {}).get("set_id"),
            }
