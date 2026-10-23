from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ANGULAR_LETTERS = "SPDFGHIJK"
DEGENERACY = {letter: 2 * index + 1 for index, letter in enumerate(ANGULAR_LETTERS)}
_COUNT_PATTERN = re.compile(
    r"^\s*Number\s+of\s+([A-Za-z])orbital\s*-+>\s*(\d+)\s*$", re.IGNORECASE
)
_BLOCK_COUNTS_HEADER = "number of radial functions for each angular momentum"


class OrbitalInfoError(ValueError):
    """Raised when an ABACUS orbital file header cannot be interpreted."""


@dataclass(frozen=True)
class OrbitalHeader:
    element: str | None
    lmax: int
    radial_counts: dict[int, int]
    mesh: int | None = None
    dr: float | None = None

    @property
    def basis_dimension(self) -> int:
        """Physical basis dimension: sum over l of radial_count * (2l + 1)."""
        return sum(count * DEGENERACY[ANGULAR_LETTERS[l]] for l, count in self.radial_counts.items())

    def basis_dimension_for(self, *, soc: bool = False) -> int:
        """Basis dimension for the spin treatment; SOC doubles the block size."""
        return self.basis_dimension * (2 if soc else 1)

    def shell_summary(self) -> str:
        """Compact shell string such as ``3s3p3d2f``."""
        known = [
            (letter, self.radial_counts[index])
            for index, letter in enumerate(ANGULAR_LETTERS)
            if index in self.radial_counts and self.radial_counts[index]
        ]
        return "".join(f"{count}{letter.lower()}" for letter, count in known)


def _value_after_key(lines: list[str], index: int, key: str) -> str | None:
    line = lines[index]
    remainder = line.split(key, 1)[1].strip() if key in line else ""
    if remainder and not remainder.startswith("-"):
        return remainder.split()[0]
    for follow in lines[index + 1 :]:
        stripped = follow.strip()
        if not stripped or set(stripped) == {"-"}:
            continue
        return stripped.split()[0]
    return None


def parse_orbital_header(path: str | Path) -> OrbitalHeader:
    """Parse the summary block of an ABACUS ``.orb`` file.

    Supports both the compact key/value layout (``Number of Sorbital--> 3``)
    and the older block layout (``Number of radial functions for each angular
    momentum`` followed by one integer per l).
    """
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise OrbitalInfoError(f"cannot read orbital file {path}: {exc}") from exc

    element: str | None = None
    lmax: int | None = None
    counts: dict[int, int] = {}
    mesh: int | None = None
    dr: float | None = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        lowered = stripped.lower()
        if not stripped:
            continue
        if lowered.startswith("element"):
            value = _value_after_key(lines, index, "Element")
            element = value
        elif lowered.startswith("lmax"):
            value = _value_after_key(lines, index, "Lmax")
            if value is not None and value.lstrip("+-").isdigit():
                lmax = int(value)
        elif lowered.startswith("mesh"):
            value = _value_after_key(lines, index, "Mesh")
            if value is not None and value.lstrip("+-").isdigit():
                mesh = int(value)
        elif lowered.startswith("dr"):
            value = _value_after_key(lines, index, "dr")
            if value is None:
                value = stripped[2:].strip().split()[0] if stripped[2:].strip() else None
            if value is not None:
                try:
                    dr = float(value)
                except ValueError:
                    pass
        elif (m := _COUNT_PATTERN.match(stripped)):
            letter = m.group(1).upper()
            if letter not in DEGENERACY:
                raise OrbitalInfoError(f"{path}: unknown angular momentum {letter!r}")
            counts[ANGULAR_LETTERS.index(letter)] = int(m.group(2))
        elif lowered.startswith(_BLOCK_COUNTS_HEADER) and not counts:
            for follow in lines[index + 1 :]:
                values = follow.split()
                if not values:
                    continue
                if all(value.lstrip("+-").isdigit() for value in values):
                    for l_index, value in enumerate(values):
                        counts[l_index] = int(value)
                break

    if not counts:
        raise OrbitalInfoError(f"{path}: no angular-momentum counts found in the orbital header")
    if any(count < 0 for count in counts.values()):
        raise OrbitalInfoError(f"{path}: negative angular-momentum count")
    if lmax is not None and lmax < 0:
        raise OrbitalInfoError(f"{path}: negative Lmax")
    if lmax is None:
        lmax = max(counts)
    return OrbitalHeader(
        element=element,
        lmax=lmax,
        radial_counts=dict(sorted(counts.items())),
        mesh=mesh,
        dr=dr,
    )


def basis_dimension(path: str | Path, *, soc: bool = False) -> int:
    """Return the physical basis dimension declared by one orbital file."""
    return parse_orbital_header(path).basis_dimension_for(soc=soc)
