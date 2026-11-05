"""Compare the PP/NAO/ABFS actually present for a run with a database element set.

The database records a SHA-256 for every payload it publishes, and the reference
records bind each species to a concrete ``set_id``. A GW number is only
comparable to such a record when the calculation really used those payloads:
the same pseudopotential, the same numerical orbital and the same auxiliary
basis. This module turns that requirement into a file-level comparison that can
run before any compute is submitted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .basis_registry import ElementSet


ROLE_SUFFIXES: dict[str, tuple[str, ...]] = {
    "pp": (".upf",),
    "nao": (".orb",),
    "abf": (".abfs",),
}


class InputIdentityError(ValueError):
    """Raised when the observed inputs cannot be attributed to an element/role."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def role_for_name(name: str) -> str | None:
    lowered = name.lower()
    for role, suffixes in ROLE_SUFFIXES.items():
        if any(lowered.endswith(suffix) for suffix in suffixes):
            return role
    return None


def element_for_name(name: str, elements: Sequence[str] | None = None) -> str | None:
    """Attribute a payload file name to an element.

    Case bundles name payloads ``<Element>_...`` (B_gga_...orb, N_ONCV...upf).
    When the expected elements are known, the longest matching prefix wins so
    that ``B`` does not swallow ``Bi``.
    """
    stem = name
    if elements:
        candidates = [
            element
            for element in elements
            if stem == element or stem.startswith(element + "_") or stem.startswith(element + "-")
        ]
        if candidates:
            return max(candidates, key=len)
        return None
    head = stem.split("_", 1)[0].split("-", 1)[0]
    return head if head and head[0].isupper() and head.isalpha() else None


@dataclass(frozen=True)
class ObservedBasis:
    hashes: dict[str, str]
    paths: dict[str, str]
    duplicates: dict[str, tuple[str, ...]]
    unattributed: tuple[str, ...]

    def by_element(self) -> tuple[str, ...]:
        return tuple(sorted({key.split("/", 1)[0] for key in self.hashes}))


def expected_basis_hashes(sets: Mapping[str, ElementSet]) -> dict[str, str]:
    """Flatten resolved element sets into ``<Element>/<role> -> sha256``."""
    expected: dict[str, str] = {}
    for element, element_set in sorted(sets.items()):
        for role, asset in sorted(element_set.files.items()):
            expected[f"{element}/{role}"] = asset.sha256
    return expected


def expected_set_ids(sets: Mapping[str, ElementSet]) -> dict[str, str]:
    return {element: element_set.set_id for element, element_set in sorted(sets.items())}


def observed_basis(case_dir: str | Path, elements: Sequence[str] | None = None) -> ObservedBasis:
    """Hash every PP/NAO/ABFS payload found under ``case_dir``.

    Files that cannot be attributed to an element are reported rather than
    silently ignored, because an unattributed payload is exactly the kind of
    input that has produced a mismatched benchmark before.
    """
    root = Path(case_dir)
    if not root.exists():
        raise InputIdentityError(f"case directory does not exist: {root}")
    hashes: dict[str, str] = {}
    paths: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}
    unattributed: list[str] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        role = role_for_name(path.name)
        if role is None:
            continue
        element = element_for_name(path.name, elements)
        if element is None:
            unattributed.append(str(path.relative_to(root)))
            continue
        key = f"{element}/{role}"
        digest = file_sha256(path)
        if key in hashes:
            if hashes[key] != digest:
                duplicates.setdefault(key, [paths[key]]).append(str(path.relative_to(root)))
            continue
        hashes[key] = digest
        paths[key] = str(path.relative_to(root))
    return ObservedBasis(
        hashes=hashes,
        paths=paths,
        duplicates={key: tuple(value) for key, value in duplicates.items()},
        unattributed=tuple(unattributed),
    )


def compare_basis(
    expected: Mapping[str, str],
    observed: ObservedBasis,
    *,
    expected_names: Mapping[str, str] | None = None,
) -> list[str]:
    """Return one human-readable problem per element/role that does not match."""
    problems: list[str] = []
    for key in sorted(expected):
        name = f" ({expected_names[key]})" if expected_names and key in expected_names else ""
        if key in observed.duplicates:
            problems.append(
                f"{key}{name}: several payloads with different hashes: "
                + ", ".join(observed.duplicates[key])
            )
            continue
        if key not in observed.hashes:
            problems.append(f"{key}{name}: no payload was found in the case")
            continue
        if observed.hashes[key] != expected[key]:
            problems.append(
                f"{key}{name}: {observed.paths[key]} has sha256 {observed.hashes[key]}, "
                f"expected {expected[key]}"
            )
    for key, members in sorted(observed.duplicates.items()):
        if key not in expected:
            problems.append(f"{key}: several payloads with different hashes: " + ", ".join(members))
    return problems


def observed_element_names(observed: ObservedBasis) -> tuple[str, ...]:
    return observed.by_element()
