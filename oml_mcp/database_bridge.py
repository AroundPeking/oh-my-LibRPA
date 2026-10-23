"""Turn a campaign manifest into a LibRPA-database candidate package.

The bridge stages the declared files under the database layout
(``data/calculations/<dim>/<material>/<record-id>/``), sanitizes private paths
and job-ID spellings before hashing, and emits three artifacts in the staging
directory: the record draft, the candidate receipt, and the import plan. It
never writes into the database repository; the existing approval/import path
consumes these artifacts.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .campaign_export import FILE_GROUPS, MANIFEST_SCHEMA, sha256_file


RECORD_TYPES = {
    "periodic_3d_gw": "band",
    "strict_2d_gw": "band",
    "strict_2d_sos_rpa": "rpa_energy",
    "molecular_delta_st_rpa": "rpa_energy",
    "solid_delta_st_rpa": "rpa_energy",
}
TEXT_SUFFIXES = frozenset(
    {".in", ".txt", ".dat", ".md", ".log", ".out", ".json", ".yaml", ".yml", ".sh", ".py", ".csv"}
)
_PATH_PATTERNS = (
    (re.compile(r"/Users/[^/\s]+"), "/HPC"),
    (re.compile(r"/home/[^/\s]+"), "/HPC"),
    (re.compile(r"/work\d+/[^/\s]+"), "/HPC"),
    (re.compile(r"ssh://"), ""),
)
_JOB_ID_PATTERN = re.compile(r"SLURM_JOB_ID")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class BridgeError(ValueError):
    """Raised when a manifest cannot be turned into a database candidate."""


def record_type_for_route(route: str) -> str:
    try:
        return RECORD_TYPES[route]
    except KeyError as exc:
        raise BridgeError(f"route {route!r} has no database record type") from exc


def sanitize_text(text: str) -> tuple[str, bool]:
    """Replace private path prefixes and the old job-ID spelling."""
    changed = False
    for pattern, replacement in _PATH_PATTERNS:
        updated = pattern.sub(replacement, text)
        if updated != text:
            changed = True
            text = updated
    updated = _JOB_ID_PATTERN.sub("SLURM_JOBID", text)
    if updated != text:
        changed = True
        text = updated
    return text, changed


def _record_id(campaign_id: str) -> str:
    slug = _SAFE_NAME.sub("-", campaign_id.lower()).strip("-")
    if not slug:
        raise BridgeError("campaign id has no usable characters for a record id")
    return f"oml-{slug}"[:64].rstrip("-")


def _safe_file_name(label: str, fallback: str) -> str:
    name = Path(label or fallback).name
    name = _SAFE_NAME.sub("_", name).strip("._")
    return (name or "file")[:80]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def build_candidate(
    manifest: Mapping[str, Any],
    *,
    staging_root: str | Path,
    approval: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage the manifest and return the record draft, receipt, and plan."""
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise BridgeError(f"unsupported manifest schema {manifest.get('schema_version')!r}")
    workspace = manifest.get("workspace")
    if not isinstance(workspace, str) or not workspace:
        raise BridgeError("manifest has no workspace")
    workspace_path = Path(workspace)
    if not workspace_path.is_dir():
        raise BridgeError(f"manifest workspace does not exist: {workspace_path}")

    case = manifest.get("case") or {}
    dimension = case.get("dimension")
    material = case.get("material")
    if dimension not in {"2d", "3d"} or not material:
        raise BridgeError("manifest case needs a 2d/3d dimension and a material")
    record_type = record_type_for_route(str(manifest.get("route")))
    record_id = _record_id(str(manifest["campaign"]["id"]))

    staging_root = Path(staging_root).resolve()
    record_dir = staging_root / "data" / "calculations" / dimension / material / record_id
    if record_dir.exists():
        raise BridgeError(f"staging record already exists: {record_dir}")

    staged: dict[str, list[dict[str, Any]]] = {group: [] for group in FILE_GROUPS}
    path_map: dict[str, str] = {}
    for group in FILE_GROUPS:
        for index, entry in enumerate(manifest.get("files", {}).get(group, [])):
            relative = entry.get("path")
            if not isinstance(relative, str):
                raise BridgeError(f"files.{group} entry without a path")
            source = workspace_path / relative
            if source.is_symlink() or not source.is_file():
                raise BridgeError(f"missing manifest file: {relative}")
            name = _safe_file_name(str(entry.get("label") or relative), relative)
            target = record_dir / group / name
            if target.exists():
                name = f"{index:03d}_{name}"
                target = record_dir / group / name
            target.parent.mkdir(parents=True, exist_ok=True)

            raw = source.read_bytes()
            transformation = "none"
            data = raw
            if source.suffix.lower() in TEXT_SUFFIXES:
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    text = None
                if text is not None:
                    cleaned, changed = sanitize_text(text)
                    if changed:
                        data = cleaned.encode("utf-8")
                        transformation = "sanitized"
            target.write_bytes(data)

            staged_relative = str(target.relative_to(staging_root))
            path_map[relative] = staged_relative
            staged[group].append(
                {
                    "path": staged_relative,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                    "role": entry.get("role"),
                    "label": entry.get("label") or name,
                    "original_name": Path(relative).name,
                    "original_sha256": entry.get("sha256"),
                    "transformation": transformation,
                }
            )

    structure = next(
        (entry for entry in staged["inputs"] if str(entry.get("role", "")).lower() == "structure"),
        None,
    )
    if structure is None:
        raise BridgeError("manifest inputs need a file with role 'structure'")

    properties = []
    for prop in manifest.get("results", {}).get("properties", []):
        evidence = []
        for reference in prop.get("evidence", []):
            if reference not in path_map:
                raise BridgeError(f"property evidence is not a declared file: {reference}")
            evidence.append(path_map[reference])
        properties.append(
            {
                "key": prop["key"],
                "label": prop.get("label") or prop["key"],
                "category": prop.get("category") or "electronic",
                "method": prop.get("method") or "GW",
                "unit": prop["unit"],
                "status": prop["status"],
                "value": prop["value"],
                "definition": prop["definition"],
                "evidence": evidence,
            }
        )
    if not properties:
        raise BridgeError("manifest has no result properties")

    auxiliary = None
    auxiliary_manifest = manifest.get("auxiliary_basis")
    if auxiliary_manifest:
        auxiliary = {
            "mode": auxiliary_manifest["mode"],
            "threshold": auxiliary_manifest["threshold"],
            "evidence": [
                path_map[reference] for reference in auxiliary_manifest["evidence"]
            ],
        }

    performance_manifest = manifest["performance"]
    evidence_pool = staged["logs"] or staged["results"]
    if not evidence_pool:
        raise BridgeError("performance evidence needs at least one log or result file")
    performance = {
        "cluster_label": performance_manifest["cluster_label"],
        "accelerators": performance_manifest["accelerators"],
        "accelerator_label": performance_manifest["accelerator_label"],
        "nodes": performance_manifest["nodes"],
        "cpus": performance_manifest["cpus"],
        "mpi_ranks": performance_manifest["mpi_ranks"],
        "omp_threads_per_rank": performance_manifest["omp_threads_per_rank"],
        "elapsed_seconds": performance_manifest["elapsed_seconds"],
        "evidence": [evidence_pool[0]["path"]],
    }

    species_manifest = manifest["basis"]["species"]
    atom_count = sum(int(item["atom_count"]) for item in species_manifest)
    ao_count = sum(
        int(item["atom_count"]) * int(item["dimension_per_atom"]) for item in species_manifest
    )
    nbands = int(manifest["definition"]["nbands"])
    occupied = int(case["occupied_bands"])
    computational_scale = {
        "atom_count": atom_count,
        "ao_count": ao_count,
        "matrix_rows": ao_count,
        "matrix_columns": ao_count,
        "state_count": nbands,
        "occupied_states": occupied,
        "unoccupied_states": nbands - occupied,
    }
    if computational_scale["unoccupied_states"] < 0:
        raise BridgeError("nbands must not be smaller than the occupied-band count")

    gap_property = next(
        (
            prop
            for prop in properties
            if "gap" in prop["key"].lower() and "gw" in prop["key"].lower()
        ),
        None,
    ) or next((prop for prop in properties if "gap" in prop["key"].lower()), properties[0])
    summary = {
        "observable": gap_property["key"],
        "value": gap_property["value"],
        "unit": gap_property["unit"],
        "gap_definition": gap_property["definition"],
    }

    record = {
        "schema_version": 1,
        "id": record_id,
        "material": material,
        "formula": case.get("formula") or material,
        "dimension": dimension,
        "record_type": record_type,
        "structure_identity": {
            "algorithm": "cell-sites-v1",
            "sha256": case["structure_sha256"],
            "evidence": structure["path"],
        },
        "species": [
            {"element": item["element"], "set_id": item["set_id"]} for item in species_manifest
        ],
        "auxiliary_basis": auxiliary,
        "computational_scale": computational_scale,
        "workflow": {
            "frontend": "abacus",
            "task": "gw" if record_type == "band" else "rpa",
        },
        "summary": summary,
        "properties": properties,
        "performance": performance,
        "software": manifest["software"],
        "files": staged,
        "source": {
            "collection": "oh-my-librpa campaign",
            "repository": "oh-my-librpa",
            "runtime_provenance": str(manifest["campaign"]["id"]),
        },
        "missing": list(manifest.get("missing") or []),
    }

    record_text = _canonical_json(record)
    record_sha256 = hashlib.sha256(record_text.encode()).hexdigest()
    statement = None
    approved = False
    timestamp = datetime.now(timezone.utc).isoformat()
    if approval is not None:
        statement = approval.get("user_statement")
        if not isinstance(statement, str) or not statement.strip():
            raise BridgeError("approval needs the verbatim user_statement")
        timestamp = approval.get("timestamp") or timestamp
        approved = True
    receipt = {
        "schema_version": 1,
        "approved": approved,
        "candidate_sha256": record_sha256,
        "user_statement": statement,
        "timestamp": timestamp,
    }
    plan = {
        "schema_version": 1,
        "candidate_sha256": record_sha256,
        "record_path": str((record_dir / "record.json").relative_to(staging_root)),
        "files": [
            {"path": entry["path"], "sha256": entry["sha256"]}
            for group in FILE_GROUPS
            for entry in staged[group]
        ],
    }

    record_dir.mkdir(parents=True, exist_ok=True)
    record_path = record_dir / "record.json"
    receipt_path = record_dir / "candidate_receipt.json"
    plan_path = record_dir / "import_plan.json"
    record_path.write_text(record_text, encoding="utf-8")
    receipt_path.write_text(_canonical_json(receipt), encoding="utf-8")
    plan_path.write_text(_canonical_json(plan), encoding="utf-8")

    return {
        "record": record,
        "record_path": str(record_path),
        "receipt": receipt,
        "receipt_path": str(receipt_path),
        "plan": plan,
        "plan_path": str(plan_path),
        "candidate_sha256": record_sha256,
    }
