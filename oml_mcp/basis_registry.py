"""Content-addressed PP/NAO/ABFS sets from the LibRPA-database element library.

The library stores one ``set.json`` per element set under
``data/elements/<Element>/sets/<set-id>/``. Each set lists the pseudopotential
(``pp``), numerical orbital (``nao``) and optional auxiliary basis (``abf``)
payloads by relative path, SHA-256 and physical dimensions. This module loads
those sets, resolves a family request to concrete files, verifies the hashes,
and stages the payloads next to a case bundle.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


ROLES = ("pp", "nao", "abf")
SET_SCHEMA_VERSION = 1
BUILD_SKILL_HINT = (
    "element {element} has no matched PP/NAO/ABFS set in the basis library; "
    "build one with the abacus-librpa-gw-basis-skill method and register the set"
)


class BasisRegistryError(ValueError):
    """Raised when the basis library is missing, malformed, or cannot resolve."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_family(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


@dataclass(frozen=True)
class BasisAsset:
    role: str
    path: Path
    sha256: str
    size_bytes: int | None = None
    dimensions: dict[str, Any] | None = None


@dataclass(frozen=True)
class ElementSet:
    set_id: str
    element: str
    family: str | None
    validation_scope: str | None
    files: dict[str, BasisAsset]
    source: dict[str, Any] | None = None

    def asset(self, role: str) -> BasisAsset | None:
        return self.files.get(role)


def _load_set(path: Path, root: Path) -> ElementSet:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BasisRegistryError(f"cannot read element set {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BasisRegistryError(f"element set {path} must be a JSON object")
    if value.get("schema_version") != SET_SCHEMA_VERSION:
        raise BasisRegistryError(f"{path}: unsupported schema_version {value.get('schema_version')!r}")
    element = value.get("element")
    set_id = value.get("id") or path.parent.name
    if not isinstance(element, str) or not element:
        raise BasisRegistryError(f"{path}: missing element")
    files: dict[str, BasisAsset] = {}
    root = root.resolve()
    for entry in value.get("files") or []:
        if not isinstance(entry, dict):
            raise BasisRegistryError(f"{path}: file entries must be objects")
        role = entry.get("role")
        if role not in ROLES:
            # The database also stores non-OML roles (for example FHI-aims
            # species defaults); they do not participate in OML basis choice.
            continue
        relative = entry.get("path")
        if not isinstance(relative, str):
            raise BasisRegistryError(f"{path}: file entry without a path")
        asset_path = (root / relative).resolve()
        if asset_path != root and root not in asset_path.parents:
            raise BasisRegistryError(f"{path}: asset path escapes the library root: {relative}")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not digest:
            raise BasisRegistryError(f"{path}: asset {relative} has no sha256")
        files[role] = BasisAsset(
            role=role,
            path=asset_path,
            sha256=digest,
            size_bytes=entry.get("size_bytes"),
            dimensions=entry.get("dimensions"),
        )
    return ElementSet(
        set_id=str(set_id),
        element=element,
        family=value.get("family"),
        validation_scope=value.get("validation_scope"),
        files=files,
        source=value.get("source") if isinstance(value.get("source"), dict) else None,
    )


def load_registry(root: str | Path) -> dict[str, tuple[ElementSet, ...]]:
    """Load every element set under ``<root>/data/elements``."""
    root = Path(root)
    elements_root = root / "data" / "elements"
    if not elements_root.is_dir():
        raise BasisRegistryError(f"basis library has no data/elements directory: {elements_root}")
    registry: dict[str, list[ElementSet]] = {}
    for path in sorted(elements_root.glob("*/sets/*/set.json")):
        element_set = _load_set(path, root)
        registry.setdefault(element_set.element, []).append(element_set)
    if not registry:
        raise BasisRegistryError(f"no element sets found under {elements_root}")
    return {
        element: tuple(sorted(sets, key=lambda item: (item.family or "", item.set_id)))
        for element, sets in registry.items()
    }


def _family_match(requested: str, element_set: ElementSet) -> bool:
    wanted = _normalize_family(requested)
    if not wanted:
        return False
    family = _normalize_family(element_set.family or "")
    return bool(family) and (family == wanted or family in wanted or wanted in _normalize_family(element_set.set_id))


class BasisAmbiguityError(BasisRegistryError):
    """Raised when more than one database set matches and nobody chose one.

    The basis is a scientific decision, not a lookup: two element sets differ
    in pseudopotential family, NAO size and auxiliary basis, so picking the
    first alphabetically is picking a different calculation. Twenty-three of the
    thirty-two elements in the shipped library have more than one usable set (19
    once an auxiliary basis is required), so this happens on real cases, not
    only on synthetic ones.
    """

    def __init__(self, element: str, candidates: tuple[ElementSet, ...], message: str) -> None:
        super().__init__(message)
        self.element = element
        self.candidates = candidates

    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(item.set_id for item in self.candidates)


def describe_set(element_set: ElementSet) -> dict[str, Any]:
    """Return the provenance and size of one element set, with no judgement."""
    described: dict[str, Any] = {
        "set_id": element_set.set_id,
        "element": element_set.element,
        "family": element_set.family,
        "validation_scope": element_set.validation_scope,
        "source": dict(element_set.source or {}),
        "roles": {},
    }
    for role, asset in sorted(element_set.files.items()):
        entry: dict[str, Any] = {
            "path": str(asset.path),
            "file_name": asset.path.name,
            "sha256": asset.sha256,
            "size_bytes": asset.size_bytes if asset.size_bytes is not None else asset.path.stat().st_size,
        }
        if asset.dimensions:
            entry["dimensions"] = dict(asset.dimensions)
        described["roles"][role] = entry
    return described


def resolve_set(
    registry: Mapping[str, tuple[ElementSet, ...]],
    element: str,
    *,
    family: str | None = None,
    require_abf: bool = False,
    set_id: str | None = None,
) -> ElementSet:
    """Resolve one element to a concrete set; ``abfs_default`` keeps the set's own ABFS.

    ``set_id`` is the only way to choose between several matching sets. Without
    it an ambiguous element raises ``BasisAmbiguityError`` instead of silently
    taking the first candidate: the caller (a human, through the reported
    candidates) is the one that decides.
    """
    candidates = registry.get(element)
    if not candidates:
        raise BasisRegistryError(BUILD_SKILL_HINT.format(element=element))
    filtered = [item for item in candidates if "pp" in item.files and "nao" in item.files]
    if not filtered:
        raise BasisRegistryError(
            f"element {element} has only incomplete sets (missing pp or nao); "
            + BUILD_SKILL_HINT.format(element=element)
        )
    if family and family != "abfs_default":
        filtered = [item for item in filtered if _family_match(family, item)]
        if not filtered:
            available = sorted({item.family or item.set_id for item in candidates})
            raise BasisRegistryError(
                f"element {element} has no set for family {family!r}; available: {available}"
            )
    if require_abf:
        filtered = [item for item in filtered if "abf" in item.files]
        if not filtered:
            raise BasisRegistryError(
                f"element {element} has no set with an auxiliary basis; "
                "generate the ABFS with the abacus-librpa-gw-basis-skill method"
            )
    if set_id is not None:
        exact = [item for item in filtered if item.set_id == set_id]
        if not exact:
            available = sorted(item.set_id for item in filtered)
            raise BasisRegistryError(
                f"element {element} has no usable set {set_id!r}"
                + (f" for family {family!r}" if family else "")
                + f"; usable sets: {available}"
            )
        return exact[0]
    if len(filtered) > 1:
        listed = ", ".join(
            f"{item.set_id} (family={item.family!r})" for item in filtered
        )
        raise BasisAmbiguityError(
            element,
            tuple(filtered),
            f"element {element} matches {len(filtered)} database sets: {listed}. "
            "Refusing to choose one: name the set explicitly "
            f"(set_id={filtered[0].set_id!r} is one candidate).",
        )
    return filtered[0]


def verify_asset(asset: BasisAsset) -> None:
    """Fail when an asset is missing, a symlink, or does not match its SHA-256."""
    if asset.path.is_symlink() or not asset.path.is_file():
        raise BasisRegistryError(f"missing or linked asset: {asset.path}")
    actual = file_sha256(asset.path)
    if actual != asset.sha256:
        raise BasisRegistryError(
            f"asset hash mismatch for {asset.path}: {actual} != {asset.sha256}"
        )
    if asset.size_bytes is not None and asset.path.stat().st_size != asset.size_bytes:
        raise BasisRegistryError(f"asset size mismatch for {asset.path}")


def stage_element_sets(
    registry: Mapping[str, tuple[ElementSet, ...]],
    elements: Iterable[str],
    *,
    destination: str | Path,
    family: str | None = None,
    require_abf: bool = False,
) -> dict[str, dict[str, str]]:
    """Copy resolved assets into ``destination`` and return their staged names."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    staged: dict[str, dict[str, str]] = {}
    for element in dict.fromkeys(elements):
        element_set = resolve_set(registry, element, family=family, require_abf=require_abf)
        mapping: dict[str, str] = {}
        for role in ROLES:
            asset = element_set.files.get(role)
            if asset is None:
                continue
            verify_asset(asset)
            name = f"{element}_{role}_{asset.sha256[:12]}{asset.path.suffix}"
            target = destination / name
            shutil.copyfile(asset.path, target)
            if file_sha256(target) != asset.sha256:
                raise BasisRegistryError(f"staged copy of {asset.path} changed bytes")
            mapping[role] = name
        staged[element] = mapping
    return staged
