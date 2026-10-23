"""Emit ``oml.campaign-manifest.v1`` receipts for completed campaigns.

The manifest is the single hand-off from the loop to the LibRPA database: it
carries the case identity, the complete definition (including basis hashes),
software identity, file hashes, performance, result properties, gate receipts,
and the condensed trial ledger. It never writes into the database itself.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


MANIFEST_SCHEMA = "oml.campaign-manifest.v1"
FILE_GROUPS = ("inputs", "results", "logs")
AUXILIARY_MODES = frozenset({"pca_generated", "prebuilt_abfs_pca"})
DIMENSIONS = frozenset({"2d", "3d"})
PROPERTY_STATUSES = frozenset({"reported", "validated", "provisional", "failed"})
_HEX64 = 64


class ManifestError(ValueError):
    """Raised when a campaign manifest is incomplete or inconsistent."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entry(
    path: str | Path,
    *,
    root: str | Path | None = None,
    role: str = "input",
    label: str | None = None,
) -> dict[str, Any]:
    """Describe one campaign file; ``path`` is stored relative to ``root``."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ManifestError(f"manifest file must be a regular file: {path}")
    relative = Path(path.name) if root is None else path.resolve().relative_to(Path(root).resolve())
    return {
        "path": str(relative),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "role": role,
        "label": label or path.name,
    }


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(manifest), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _text(container: Mapping[str, Any], key: str, label: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label}.{key} must be a non-empty string")
    return value


def _integer(container: Mapping[str, Any], key: str, label: str, *, minimum: int = 1) -> int:
    value = container.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ManifestError(f"{label}.{key} must be an integer >= {minimum}")
    return value


def _hex(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != _HEX64 or any(c not in "0123456789abcdef" for c in value.lower()):
        raise ManifestError(f"{label} must be a lowercase 64-hex digest")
    return value


def _validate_files(files: Mapping[str, Any], workspace: Path) -> dict[str, list[dict[str, Any]]]:
    validated: dict[str, list[dict[str, Any]]] = {}
    for group in FILE_GROUPS:
        entries = files.get(group, [])
        if not isinstance(entries, list):
            raise ManifestError(f"files.{group} must be a list")
        checked = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise ManifestError(f"files.{group} entries must be objects")
            relative = entry.get("path")
            if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
                raise ManifestError(f"files.{group} paths must be workspace-relative strings")
            resolved = (workspace / relative).resolve()
            if workspace not in resolved.parents and resolved != workspace:
                raise ManifestError(f"files.{group} path escapes the workspace: {relative}")
            if resolved.is_symlink() or not resolved.is_file():
                raise ManifestError(f"missing manifest file: {relative}")
            digest = _hex(entry.get("sha256"), f"files.{group}.{relative}.sha256")
            size = entry.get("size_bytes")
            if not isinstance(size, int) or size < 0:
                raise ManifestError(f"files.{group}.{relative}.size_bytes must be a non-negative integer")
            if sha256_file(resolved) != digest:
                raise ManifestError(f"stale sha256 for {relative}")
            if resolved.stat().st_size != size:
                raise ManifestError(f"stale size for {relative}")
            role = entry.get("role")
            if not isinstance(role, str) or not role:
                raise ManifestError(f"files.{group}.{relative}.role must be a non-empty string")
            checked.append(dict(entry))
        validated[group] = checked
    if not any(validated.values()):
        raise ManifestError("manifest declares no files")
    return validated


def build_manifest(
    *,
    campaign_id: str,
    route: str,
    case: Mapping[str, Any],
    definition: Mapping[str, Any],
    basis: Mapping[str, Any],
    software: Mapping[str, Any],
    files: Mapping[str, Any],
    performance: Mapping[str, Any],
    properties: Iterable[Mapping[str, Any]],
    workspace: str | Path,
    auxiliary_basis: Mapping[str, Any] | None = None,
    gates: Mapping[str, Any] | None = None,
    ledger: Iterable[Mapping[str, Any]] | None = None,
    missing: Iterable[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Validate and assemble a campaign manifest."""
    _text({"campaign_id": campaign_id}, "campaign_id", "campaign")
    _text({"route": route}, "route", "manifest")
    if not isinstance(definition, Mapping) or not definition:
        raise ManifestError("definition must be a non-empty object")

    case_checked = {
        "material": _text(case, "material", "case"),
        "formula": case.get("formula") or _text(case, "material", "case"),
        "dimension": _text(case, "dimension", "case"),
        "structure_sha256": _hex(case.get("structure_sha256"), "case.structure_sha256"),
        "site_count": _integer(case, "site_count", "case"),
        "occupied_bands": _integer(case, "occupied_bands", "case"),
    }
    if case_checked["dimension"] not in DIMENSIONS:
        raise ManifestError("case.dimension must be 2d or 3d")

    species = basis.get("species") if isinstance(basis, Mapping) else None
    if not isinstance(species, list) or not species:
        raise ManifestError("basis.species must be a non-empty list")
    species_checked = []
    for item in species:
        if not isinstance(item, Mapping):
            raise ManifestError("basis.species entries must be objects")
        species_checked.append(
            {
                "element": _text(item, "element", "basis.species"),
                "set_id": _text(item, "set_id", "basis.species"),
                "pp_sha256": _hex(item.get("pp_sha256"), "basis.species.pp_sha256"),
                "nao_sha256": _hex(item.get("nao_sha256"), "basis.species.nao_sha256"),
                "abf_sha256": (
                    _hex(item.get("abf_sha256"), "basis.species.abf_sha256")
                    if item.get("abf_sha256")
                    else None
                ),
                "dimension_per_atom": _integer(item, "dimension_per_atom", "basis.species"),
                "atom_count": _integer(item, "atom_count", "basis.species"),
            }
        )

    software_checked = {}
    for code in ("abacus", "librpa"):
        entry = software.get(code) if isinstance(software, Mapping) else None
        if not isinstance(entry, Mapping):
            raise ManifestError(f"software.{code} is required")
        commit = entry.get("commit")
        executable = entry.get("executable_sha256")
        if not commit and not executable:
            raise ManifestError(f"software.{code} needs a commit or executable_sha256")
        software_checked[code] = {
            "commit": commit,
            "executable_sha256": executable,
            "source_url": entry.get("source_url"),
        }

    workspace = Path(workspace).resolve()
    files_checked = _validate_files(files, workspace)
    if not any(
        str(entry.get("role", "")).lower() == "structure" for entry in files_checked["inputs"]
    ):
        raise ManifestError("files.inputs needs an entry with role 'structure'")

    performance_checked = {
        "cluster_label": _text(performance, "cluster_label", "performance"),
        "nodes": _integer(performance, "nodes", "performance"),
        "cpus": _integer(performance, "cpus", "performance"),
        "mpi_ranks": _integer(performance, "mpi_ranks", "performance"),
        "omp_threads_per_rank": _integer(performance, "omp_threads_per_rank", "performance"),
        "elapsed_seconds": performance.get("elapsed_seconds"),
        "accelerators": performance.get(
            "accelerators", {"type": "none", "per_node": 0, "total": 0}
        ),
        "accelerator_label": performance.get("accelerator_label", "no accelerator"),
    }
    elapsed = performance_checked["elapsed_seconds"]
    if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed <= 0:
        raise ManifestError("performance.elapsed_seconds must be a positive number")

    declared = {
        str(entry["path"])
        for group in FILE_GROUPS
        for entry in files_checked[group]
    }
    properties_checked = []
    for prop in properties:
        if not isinstance(prop, Mapping):
            raise ManifestError("properties entries must be objects")
        evidence = prop.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ManifestError("every property needs at least one evidence path")
        for reference in evidence:
            if reference not in declared:
                raise ManifestError(f"property evidence is not a declared file: {reference}")
        status = str(prop.get("status", ""))
        if status not in PROPERTY_STATUSES:
            raise ManifestError(f"unsupported property status {status!r}")
        properties_checked.append(
            {
                "key": _text(prop, "key", "property"),
                "value": prop.get("value"),
                "unit": _text(prop, "unit", "property"),
                "definition": _text(prop, "definition", "property"),
                "status": status,
                "evidence": list(evidence),
            }
        )
    if not properties_checked:
        raise ManifestError("at least one result property is required")

    auxiliary_checked = None
    if auxiliary_basis is not None:
        mode = _text(auxiliary_basis, "mode", "auxiliary_basis")
        if mode not in AUXILIARY_MODES:
            raise ManifestError(f"auxiliary_basis.mode must be one of {sorted(AUXILIARY_MODES)}")
        threshold = auxiliary_basis.get("threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ManifestError("auxiliary_basis.threshold must be a number")
        evidence = auxiliary_basis.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ManifestError("auxiliary_basis needs at least one evidence path")
        for reference in evidence:
            if reference not in declared:
                raise ManifestError(f"auxiliary-basis evidence is not a declared file: {reference}")
        auxiliary_checked = {"mode": mode, "threshold": threshold, "evidence": list(evidence)}

    ledger_checked = []
    for record in ledger or []:
        if not isinstance(record, Mapping):
            raise ManifestError("ledger entries must be objects")
        ledger_checked.append(
            {
                "trial": record.get("trial"),
                "rule_id": record.get("rule_id"),
                "action": record.get("action"),
                "accepted": record.get("accepted"),
                "reasons": list(record.get("reasons") or []),
            }
        )

    return {
        "schema_version": MANIFEST_SCHEMA,
        "campaign": {
            "id": campaign_id,
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        },
        "workspace": str(workspace),
        "route": route,
        "case": case_checked,
        "definition": dict(definition),
        "basis": {"species": species_checked},
        "auxiliary_basis": auxiliary_checked,
        "software": software_checked,
        "files": files_checked,
        "performance": performance_checked,
        "results": {"properties": properties_checked},
        "gates": dict(gates or {}),
        "ledger": ledger_checked,
        "missing": [str(item) for item in (missing or [])],
    }


def write_manifest(manifest: Mapping[str, Any], path: str | Path) -> None:
    """Write the manifest as YAML or JSON, chosen by the suffix."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise ManifestError("writing YAML needs PyYAML") from exc
        text = yaml.safe_dump(dict(manifest), sort_keys=False, allow_unicode=True)
    elif suffix == ".json":
        text = json.dumps(dict(manifest), indent=2, ensure_ascii=False) + "\n"
    else:
        raise ManifestError("manifest path must end in .yaml, .yml, or .json")
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot write manifest {path}: {exc}") from exc
