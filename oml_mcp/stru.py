"""STRU parsing, canonical structure fingerprints, and orbital-asset rewriting.

The fingerprint reproduces the LibRPA-database ``cell-sites-v1`` algorithm
byte for byte so that a local case can be matched against archived records.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Iterable, Mapping


STRUCTURE_ALGORITHM = "cell-sites-v1"
BOHR_ANGSTROM = 0.529177210903
_SECTION_HEADER = re.compile(r"[A-Z][A-Z_]+")
_ELEMENT = re.compile(r"[A-Z][a-z]?")


class StruError(ValueError):
    """Raised when a STRU file cannot be parsed or rewritten."""


def sections(text: str) -> dict[str, list[str]]:
    """Split STRU text into named sections, dropping blank and comment lines."""
    result: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = re.split(r"[#!]", raw, maxsplit=1)[0].strip()
        if not line:
            continue
        if _SECTION_HEADER.fullmatch(line):
            current = line
            result.setdefault(current, [])
        elif current is not None:
            result[current].append(line)
    return result


def species(text: str) -> tuple[tuple[str, float, str], ...]:
    """Return ``(element, mass, pseudopotential_file)`` from ATOMIC_SPECIES."""
    entries = sections(text).get("ATOMIC_SPECIES")
    if not entries:
        raise StruError("STRU has no ATOMIC_SPECIES block")
    result = []
    for line in entries:
        fields = line.split()
        if len(fields) < 3 or not _ELEMENT.fullmatch(fields[0]):
            raise StruError(f"malformed ATOMIC_SPECIES line: {line!r}")
        try:
            mass = float(fields[1])
        except ValueError as exc:
            raise StruError(f"invalid atomic mass in {line!r}") from exc
        result.append((fields[0], mass, fields[2]))
    return tuple(result)


def atom_counts(text: str) -> dict[str, int]:
    """Return the number of atoms per element from ATOMIC_POSITIONS."""
    positions = sections(text).get("ATOMIC_POSITIONS")
    if not positions:
        raise StruError("STRU has no ATOMIC_POSITIONS block")
    counts: dict[str, int] = {}
    index = 1
    while index < len(positions):
        element = positions[index].split()[0]
        if not _ELEMENT.fullmatch(element) or index + 2 >= len(positions):
            raise StruError("malformed ATOMIC_POSITIONS species block")
        try:
            count = int(positions[index + 2].split()[0])
        except (IndexError, ValueError) as exc:
            raise StruError("invalid atom count in ATOMIC_POSITIONS") from exc
        if count <= 0 or index + 3 + count > len(positions):
            raise StruError("incomplete ATOMIC_POSITIONS coordinates")
        counts[element] = counts.get(element, 0) + count
        index += 3 + count
    return counts


def _finite_xyz(tokens: Iterable[str]) -> tuple[float, float, float]:
    values = list(tokens)[:3]
    if len(values) < 3:
        raise StruError("expected three coordinates")
    try:
        xyz = tuple(float(value) for value in values)
    except ValueError as exc:
        raise StruError("invalid coordinate") from exc
    if not all(math.isfinite(value) for value in xyz):
        raise StruError("nonfinite coordinate")
    return xyz  # type: ignore[return-value]


def _cell_sites(text: str) -> tuple[list[tuple[float, float, float]], list[tuple[str, tuple[float, float, float]]]]:
    block = sections(text)
    try:
        scale = float(block["LATTICE_CONSTANT"][0].split()[0]) * BOHR_ANGSTROM
        lattice = [
            tuple(value * scale for value in _finite_xyz(line.split()))
            for line in block["LATTICE_VECTORS"][:3]
        ]
        positions = block["ATOMIC_POSITIONS"]
        mode = positions[0].lower()
    except (KeyError, IndexError, ValueError) as exc:
        raise StruError("STRU requires a valid cell and atomic positions") from exc
    if len(lattice) != 3 or not math.isfinite(scale) or scale <= 0:
        raise StruError("unsupported STRU cell")
    if mode not in {"direct", "cartesian", "cartesian_angstrom"}:
        raise StruError("unsupported ATOMIC_POSITIONS coordinate mode")
    sites: list[tuple[str, tuple[float, float, float]]] = []
    index = 1
    while index < len(positions):
        element = positions[index].split()[0]
        if not _ELEMENT.fullmatch(element) or index + 2 >= len(positions):
            raise StruError("malformed ATOMIC_POSITIONS species block")
        try:
            count = int(positions[index + 2].split()[0])
        except (IndexError, ValueError) as exc:
            raise StruError("invalid atom count in ATOMIC_POSITIONS") from exc
        if count <= 0 or index + 3 + count > len(positions):
            raise StruError("incomplete ATOMIC_POSITIONS coordinates")
        for line in positions[index + 3 : index + 3 + count]:
            coords = _finite_xyz(line.split())
            if mode == "direct":
                coords = tuple(
                    sum(coords[j] * lattice[j][i] for j in range(3)) for i in range(3)
                )
            elif mode == "cartesian":
                coords = tuple(value * scale for value in coords)
            sites.append((element, coords))
        index += 3 + count
    return lattice, sites


def structure_fingerprint(text: str, *, dimension: str) -> tuple[str, int]:
    """Return the ``cell-sites-v1`` digest and the number of sites."""
    if dimension not in {"2d", "3d"}:
        raise StruError(f"unsupported dimension {dimension!r}")
    lattice, sites = _cell_sites(text)
    if not sites or any(not math.isfinite(value) for row in lattice for value in row):
        raise StruError("empty or nonfinite cell/sites")

    def quantize(xyz: tuple[float, float, float]) -> list[int]:
        return [round(value * 100000) for value in xyz]

    payload = {
        "algorithm": STRUCTURE_ALGORITHM,
        "dimension": dimension,
        "lattice_angstrom_1e5": [quantize(row) for row in lattice],
        "sites_angstrom_1e5": sorted([element, *quantize(xyz)] for element, xyz in sites),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest, len(sites)


def _header_indices(lines: list[str]) -> list[tuple[int, str]]:
    headers = []
    for index, raw in enumerate(lines):
        line = re.split(r"[#!]", raw, maxsplit=1)[0].strip()
        if line and _SECTION_HEADER.fullmatch(line):
            headers.append((index, line))
    return headers


def _section_ranges(lines: list[str]) -> dict[str, list[int]]:
    headers = _header_indices(lines)
    ranges: dict[str, list[int]] = {}
    for position, (index, name) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        ranges[name] = list(range(index + 1, end))
    return ranges


def rewrite_assets(
    text: str,
    *,
    pp: Mapping[str, str] | None = None,
    nao: Mapping[str, str] | None = None,
    abfs: Mapping[str, str] | None = None,
) -> str:
    """Replace PP / NAO / ABFS file names in a STRU, preserving everything else."""
    lines = text.splitlines()
    order = [element for element, _, _ in species(text)]
    ranges = _section_ranges(lines)

    if pp:
        for index in ranges.get("ATOMIC_SPECIES", []):
            fields = lines[index].split()
            if fields and fields[0] in pp:
                lines[index] = f"{fields[0]} {fields[1]} {pp[fields[0]]}"

    def replace_block(name: str, mapping: Mapping[str, str], *, require_complete: bool) -> bool:
        indices = [index for index in ranges.get(name, []) if lines[index].strip()]
        if not indices:
            return False
        if len(indices) != len(order):
            raise StruError(f"{name} has {len(indices)} entries for {len(order)} species")
        missing = [element for element in order if element not in mapping]
        if require_complete and missing:
            raise StruError(f"{name} is missing entries for {missing}")
        for index, element in zip(indices, order):
            if element in mapping:
                lines[index] = mapping[element]
        return True

    if nao and not replace_block("NUMERICAL_ORBITAL", nao, require_complete=False):
        raise StruError("STRU has no NUMERICAL_ORBITAL block to rewrite")

    if abfs:
        if not replace_block("ABFS_ORBITAL", abfs, require_complete=True):
            indices = [index for index in ranges.get("NUMERICAL_ORBITAL", []) if lines[index].strip()]
            if not indices:
                raise StruError("cannot insert ABFS_ORBITAL without a NUMERICAL_ORBITAL block")
            missing = [element for element in order if element not in abfs]
            if missing:
                raise StruError(f"ABFS_ORBITAL is missing entries for {missing}")
            block = ["", "ABFS_ORBITAL", *[abfs[element] for element in order]]
            lines[indices[-1] + 1 : indices[-1] + 1] = block

    rendered = "\n".join(lines)
    if text.endswith("\n"):
        rendered += "\n"
    return rendered
