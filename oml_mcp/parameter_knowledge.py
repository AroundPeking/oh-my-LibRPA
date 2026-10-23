from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


KNOWLEDGE_SCHEMA = "oml.parameter-knowledge.v1"
PACKAGED_KNOWLEDGE_ROOT = Path(__file__).with_name("parameter_knowledge")
ENTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
OWNERS = frozenset({"abacus", "librpa"})
STAGES = frozenset({"abfs_generation", "production", "both", "workflow_control"})
DEFAULT_ORIGINS = frozenset({"oml", "abacus", "librpa", "user"})
REQUIRED_ENTRY_FIELDS = ("schema_version", "id", "title", "parameters", "sources")
REQUIRED_PARAMETER_FIELDS = ("owner", "stage", "default", "default_origin", "meaning")


class ParameterKnowledgeError(ValueError):
    """Raised when a parameter-knowledge entry is malformed or cannot be loaded."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParameterKnowledgeError(f"cannot read parameter knowledge {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ParameterKnowledgeError(f"parameter-knowledge root must be an object: {path}")
    return value


def _validate_parameter(name: str, parameter: Any, path: Path) -> None:
    if not isinstance(parameter, dict):
        raise ParameterKnowledgeError(f"{path}: parameter {name!r} must be an object")
    missing = [key for key in REQUIRED_PARAMETER_FIELDS if key not in parameter]
    if missing:
        raise ParameterKnowledgeError(f"{path}: parameter {name!r} missing {missing}")
    if parameter["owner"] not in OWNERS:
        raise ParameterKnowledgeError(f"{path}: parameter {name!r} owner {parameter['owner']!r} is not one of {sorted(OWNERS)}")
    if parameter["stage"] not in STAGES:
        raise ParameterKnowledgeError(f"{path}: parameter {name!r} stage {parameter['stage']!r} is not one of {sorted(STAGES)}")
    if parameter["default_origin"] not in DEFAULT_ORIGINS:
        raise ParameterKnowledgeError(
            f"{path}: parameter {name!r} default_origin {parameter['default_origin']!r} is not one of {sorted(DEFAULT_ORIGINS)}"
        )
    if not isinstance(parameter["meaning"], str) or not parameter["meaning"].strip():
        raise ParameterKnowledgeError(f"{path}: parameter {name!r} needs a non-empty meaning")
    stage_defaults = parameter.get("stage_defaults", {})
    if not isinstance(stage_defaults, dict):
        raise ParameterKnowledgeError(f"{path}: parameter {name!r} stage_defaults must be an object")
    for stage, override in stage_defaults.items():
        if stage not in ("abfs_generation", "production"):
            raise ParameterKnowledgeError(f"{path}: parameter {name!r} stage_defaults has unknown stage {stage!r}")
        if not isinstance(override, dict) or "value" not in override:
            raise ParameterKnowledgeError(f"{path}: parameter {name!r} stage_defaults[{stage!r}] needs a value")


def _validate_entry(entry: dict[str, Any], path: Path) -> None:
    missing = [key for key in REQUIRED_ENTRY_FIELDS if key not in entry]
    if missing:
        raise ParameterKnowledgeError(f"{path}: missing fields {missing}")
    if entry["schema_version"] != KNOWLEDGE_SCHEMA:
        raise ParameterKnowledgeError(f"{path}: unsupported schema_version {entry['schema_version']!r}")
    if not ENTRY_ID_PATTERN.match(str(entry["id"])):
        raise ParameterKnowledgeError(f"{path}: invalid entry id {entry['id']!r}")
    if not isinstance(entry["title"], str) or not entry["title"].strip():
        raise ParameterKnowledgeError(f"{path}: title must be a non-empty string")
    parameters = entry["parameters"]
    if not isinstance(parameters, dict) or not parameters:
        raise ParameterKnowledgeError(f"{path}: parameters must be a non-empty object")
    for name, parameter in parameters.items():
        _validate_parameter(name, parameter, path)
    sources = entry["sources"]
    if not isinstance(sources, list) or not sources:
        raise ParameterKnowledgeError(f"{path}: sources must be a non-empty list")
    for source in sources:
        if not isinstance(source, dict) or not source.get("kind") or not source.get("ref"):
            raise ParameterKnowledgeError(f"{path}: every source needs kind and ref")
        if not source.get("accessed"):
            raise ParameterKnowledgeError(f"{path}: every source needs an accessed date")
    for key in ("adjust", "constraints"):
        value = entry.get(key, [])
        if not isinstance(value, list):
            raise ParameterKnowledgeError(f"{path}: {key} must be a list")
    for rule in entry.get("adjust", []):
        if not isinstance(rule, dict) or not rule.get("symptom") or not rule.get("action"):
            raise ParameterKnowledgeError(f"{path}: every adjust rule needs symptom and action")


def load_entries(root: Path | None = None) -> tuple[dict[str, Any], ...]:
    """Load and validate every packaged parameter-knowledge entry."""
    root = root or PACKAGED_KNOWLEDGE_ROOT
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.json")):
        entry = _load_json(path)
        _validate_entry(entry, path)
        if entry["id"] in seen:
            raise ParameterKnowledgeError(f"duplicate knowledge id {entry['id']!r}")
        seen.add(entry["id"])
        entries.append(entry)
    if not entries:
        raise ParameterKnowledgeError(f"no parameter-knowledge entries under {root}")
    return tuple(entries)


def build_index(entries: tuple[dict[str, Any], ...] | None = None) -> dict[str, dict[str, Any]]:
    """Index entries by exact input name; duplicate declarations are rejected."""
    entries = entries if entries is not None else load_entries()
    index: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for name, parameter in entry["parameters"].items():
            if name in index:
                raise ParameterKnowledgeError(
                    f"parameter {name!r} is declared by both {index[name]['entry_id']!r} and {entry['id']!r}"
                )
            index[name] = {
                "entry_id": entry["id"],
                "title": entry["title"],
                "parameter": parameter,
                "adjust": tuple(entry.get("adjust", ())),
                "constraints": tuple(entry.get("constraints", ())),
                "sources": tuple(entry["sources"]),
                "related": entry.get("related", {}),
            }
    return index


def lookup(name: str, entries: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any]:
    """Return the knowledge record for one exact ABACUS or LibRPA input name."""
    index = build_index(entries)
    try:
        return index[name]
    except KeyError as exc:
        raise ParameterKnowledgeError(f"unknown parameter {name!r}") from exc


def parameter_names(entries: tuple[dict[str, Any], ...] | None = None) -> tuple[str, ...]:
    return tuple(sorted(build_index(entries)))
