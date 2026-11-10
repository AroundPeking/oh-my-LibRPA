"""Turn an element set into the sentence a person can actually judge.

A database set id such as ``Si-SG15-e11ce28df010`` says nothing about the
calculation: it is a hash suffix on a family name. The three facts that decide
whether a basis is the right one for a case, and that a user can check in
seconds, are what this module assembles:

* how many electrons the pseudopotential keeps in the valence (Si: 4),
* how large the numerical orbital is (Si: 3s3p2d, 22 functions per atom),
* how large the auxiliary basis is (Si: 397 per atom),
* and which calculations already used it, with their GW gaps.

Read from the payloads, not from the library index, whenever the two can
disagree. They do: 60 of the recorded auxiliary bases omit the J/K channels
that their own file header lists, so the recorded Si auxiliary dimension is 365
while the file has 397. A label that quotes the index instead of the file would
be wrong in the same way the id is uninformative.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEGENERACY = {
    "S": 1,
    "P": 3,
    "D": 5,
    "F": 7,
    "G": 9,
    "H": 11,
    "I": 13,
    "J": 15,
    "K": 17,
}
_ANGULAR_ORDER = list(DEGENERACY)
_CHANNEL = re.compile(r"Number of ([A-Z])orbital\s*-->\s*(\d+)")
_Z_VALENCE = re.compile(r'z_valence\s*=\s*"?\s*([0-9.]+)')


class BasisLabelError(ValueError):
    """Raised when the payload cannot supply a fact the label claims."""


def valence_electrons(pseudopotential: str | Path) -> int | float | None:
    """Return the number of valence electrons the pseudopotential keeps.

    ``z_valence`` is a UPF field. A format that does not declare it returns
    ``None`` rather than a guess, because a wrong electron count changes how a
    reader judges the basis size.
    """
    try:
        text = Path(pseudopotential).read_text(errors="replace")[:65536]
    except OSError as exc:
        raise BasisLabelError(f"cannot read {pseudopotential}: {exc}") from exc
    match = _Z_VALENCE.search(text)
    if match is None:
        return None
    value = float(match.group(1))
    if not math.isfinite(value) or value <= 0:
        return None
    return int(value) if value == int(value) else value


def orbital_channels(path: str | Path, *, limit_bytes: int = 65536) -> dict[str, int]:
    """Return ``{"S": 3, "P": 3, "D": 2}`` from an ABACUS .orb or .abfs header."""
    try:
        text = Path(path).read_text(errors="replace")[:limit_bytes]
    except OSError as exc:
        raise BasisLabelError(f"cannot read {path}: {exc}") from exc
    channels = {letter: int(count) for letter, count in _CHANNEL.findall(text)}
    if not channels:
        raise BasisLabelError(f"{path}: no angular-momentum channels in the header")
    return {letter: channels[letter] for letter in _ANGULAR_ORDER if letter in channels}


def dimension_from_channels(channels: Mapping[str, int]) -> int:
    """Sum ``count * (2l + 1)``; the definition of a basis dimension."""
    return sum(count * DEGENERACY[letter] for letter, count in channels.items())


def shell_string(channels: Mapping[str, int]) -> str:
    """``12s12p11d9f9g6h4i1j1k`` - the compact form physicists write."""
    return "".join(f"{count}{letter.lower()}" for letter, count in channels.items())


def payload_facts(path: str | Path, role: str) -> dict[str, Any]:
    """Read size facts for one payload, straight from its bytes."""
    file_path = Path(path)
    facts: dict[str, Any] = {"file_name": file_path.name}
    if role == "pp":
        electrons = valence_electrons(file_path)
        facts["valence_electrons"] = electrons
        facts["statement"] = (
            f"{electrons} valence electron{'s' if electrons != 1 else ''}"
            if electrons is not None
            else "valence electron count not declared by this pseudopotential format"
        )
    else:
        channels = orbital_channels(file_path)
        dimension = dimension_from_channels(channels)
        facts["channels"] = channels
        facts["shells"] = shell_string(channels)
        facts["dimension_per_atom"] = dimension
        if role == "nao":
            facts["statement"] = f"{facts['shells']}, {dimension} functions per atom"
        else:
            facts["statement"] = f"{facts['shells']}, {dimension} auxiliary functions per atom"
    return facts


# The headline number a basis is judged by, in priority order: a GW gap when the
# record has one, otherwise the RPA cohesive energy, otherwise nothing. A record
# with only a DFT gap is deliberately NOT described as a quasiparticle result.
_HEADLINE_PROPERTIES: tuple[tuple[str, frozenset[str], str], ...] = (
    ("band_gap", frozenset({"G0W0", "GW", "QSGW"}), "GW gap"),
    ("rpa_cohesive_energy", frozenset({"RPA"}), "RPA cohesive energy"),
)


def _headline(record: Mapping[str, Any]) -> tuple[float, str, str] | None:
    """Return ``(value, unit, phrase)`` for the record's headline result."""
    for key, methods, phrase in _HEADLINE_PROPERTIES:
        for item in record.get("properties") or []:
            if not isinstance(item, dict) or item.get("key") != key:
                continue
            method = str(item.get("method") or "")
            if method.upper() not in methods:
                continue
            value = item.get("value")
            if isinstance(value, (int, float)) and math.isfinite(value):
                return float(value), str(item.get("unit") or ""), f"{phrase} {value:.2f} {item.get('unit') or ''}".strip()
    return None


def historical_uses(
    records: Iterable[Mapping[str, Any]],
    set_id: str,
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return the calculations that already ran with this element set.

    A set is judged partly by what it has produced. The label therefore quotes
    the material and the quasiparticle gap of each linked calculation, so
    "Si-SG15" reads as "2 silicon diamond calculations, GW gap 1.06 eV".
    """
    uses: list[dict[str, Any]] = []
    for record in records:
        species = record.get("species") or []
        if not any(
            isinstance(item, dict) and item.get("set_id") == set_id for item in species
        ):
            continue
        headline = _headline(record)
        uses.append(
            {
                "record_id": record.get("id"),
                "material": record.get("material"),
                "formula": record.get("formula"),
                "dimension": record.get("dimension"),
                "result": headline[2] if headline else None,
                "result_value": headline[0] if headline else None,
                "result_unit": headline[1] if headline else None,
            }
        )
    uses.sort(key=lambda item: (item["result"] is None, str(item.get("record_id"))))
    return uses[:limit]


def summarise_uses(uses: Sequence[Mapping[str, Any]], element: str) -> str:
    """One clause naming how this set has been used, with its result."""
    if not uses:
        return "no calculation in the archive has used it yet"
    parts: list[str] = []
    for use in uses:
        name = use.get("formula") or use.get("material") or use.get("record_id")
        result = use.get("result")
        parts.append(f"{name} {result}" if result else str(name))
    head = f"{len(uses)} archived calculation{'s' if len(uses) != 1 else ''}"
    return head + ": " + "; ".join(parts)


def _sentence_case(text: str) -> str:
    """Capitalise the first letter only; method names and units keep their case.

    ``str.capitalize`` lowercases the rest, which turns "Si GW gap 1.06 eV" into
    "si gw gap 1.06 ev" - both the material symbol and the unit stop being
    readable.
    """
    return text[:1].upper() + text[1:] if text else text


def label_for_set(
    element: str,
    *,
    valence: int | float | None,
    nao: Mapping[str, Any] | None,
    abf: Mapping[str, Any] | None,
    uses: Sequence[Mapping[str, Any]],
    atom_count: int | None = None,
) -> dict[str, Any]:
    """Assemble the facts plus a one-line sentence for a person to read.

    ``atom_count`` switches from per-atom sizes to the totals of a concrete
    structure, which is what a user comparing two candidate sets for one case
    actually needs: "44 orbital functions" for Si2, not "22 per atom" twice.
    """
    pieces: list[str] = []
    if valence is not None:
        pieces.append(f"{valence} valence electrons")
    nao_dim = (nao or {}).get("dimension_per_atom")
    abf_dim = (abf or {}).get("dimension_per_atom")
    if atom_count:
        if nao_dim is not None:
            pieces.append(f"{int(nao_dim) * atom_count} orbital functions")
        if abf_dim is not None:
            pieces.append(f"{int(abf_dim) * atom_count} auxiliary functions")
        elif abf is None:
            pieces.append("no auxiliary basis")
    else:
        if nao_dim is not None:
            pieces.append(f"{nao_dim} orbital functions per atom")
        if abf_dim is not None:
            pieces.append(f"{abf_dim} auxiliary functions per atom")
        elif abf is None:
            pieces.append("no auxiliary basis")
    sentence = f"{element}: " + ", ".join(pieces) if pieces else f"{element}: no size information"
    return {
        "element": element,
        "atom_count": atom_count,
        "totals": {
            "orbital_functions": int(nao_dim) * atom_count if (nao_dim and atom_count) else None,
            "auxiliary_functions": int(abf_dim) * atom_count if (abf_dim and atom_count) else None,
        },
        "valence_electrons": valence,
        "orbital": dict(nao) if nao else None,
        "auxiliary": dict(abf) if abf else None,
        "sentence": sentence + ". " + _sentence_case(summarise_uses(uses, element)) + ".",
        "uses": list(uses),
    }
