from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROFILE_NAME = "abacus-librpa-pyatb-2026-08.json"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WORKFLOW_HELPERS = frozenset(
    {"perform.sh", "get_diel.py", "output_librpa.py", "preprocess_abacus_for_librpa_band.py"}
)


class ProfileError(ValueError):
    """Raised when a compatibility profile is incomplete or malformed."""


def default_profile_path() -> Path:
    packaged = Path(__file__).resolve().parent / "profiles" / PROFILE_NAME
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[1] / "profiles" / PROFILE_NAME


def _require_mapping(parent: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ProfileError(f"{context}.{key} must be an object")
    return value


def _validate_revision(component: str, entry: dict[str, Any]) -> None:
    revision = entry.get("revision")
    if not isinstance(revision, str) or len(revision) != 40:
        raise ProfileError(f"{component}.revision must be a full 40-character git SHA")
    try:
        int(revision, 16)
    except ValueError as exc:
        raise ProfileError(f"{component}.revision must be hexadecimal") from exc


def validate_profile(profile: dict[str, Any]) -> None:
    if profile.get("schema_version") != 1:
        raise ProfileError("schema_version must be 1")
    if not isinstance(profile.get("profile_id"), str) or not profile["profile_id"]:
        raise ProfileError("profile_id must be a non-empty string")

    components = _require_mapping(profile, "components", "profile")
    for name in ("abacus", "librpa", "pyatb"):
        entry = _require_mapping(components, name, "components")
        _validate_revision(name, entry)
        for key in ("repository", "ref"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise ProfileError(f"{name}.{key} must be a non-empty string")

    contract = _require_mapping(profile, "contract", "profile")
    for name in ("abacus", "librpa", "pyatb_adapter"):
        _require_mapping(contract, name, "contract")
    helpers = _require_mapping(contract, "workflow_helpers", "contract")
    if set(helpers) != WORKFLOW_HELPERS:
        raise ProfileError("contract.workflow_helpers must list the approved helper quartet")
    if any(not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value) for value in helpers.values()):
        raise ProfileError("contract.workflow_helpers values must be SHA-256 digests")


def load_profile(path: str | Path | None = None) -> dict[str, Any]:
    profile_path = Path(path) if path is not None else default_profile_path()
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileError(f"profile not found: {profile_path}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"invalid profile JSON at {profile_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError("profile root must be an object")
    validate_profile(data)
    return data
