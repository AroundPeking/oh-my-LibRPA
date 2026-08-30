from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_ID = "abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08"
V2_PROFILE_ID = "abacus-librpa-2026-08-30-v2"
PROFILE_NAMES = {
    DEFAULT_PROFILE_ID: "abacus-librpa-pyatb-2026-08.json",
    V2_PROFILE_ID: "abacus-librpa-pyatb-2026-08-v2.json",
}
PROFILE_NAME = PROFILE_NAMES[DEFAULT_PROFILE_ID]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
WORKFLOW_HELPERS = frozenset(
    {"perform.sh", "get_diel.py", "output_librpa.py", "preprocess_abacus_for_librpa_band.py"}
)
V2_CAPABILITIES = frozenset(
    {
        "periodic_3d_gw",
        "strict_2d_gw",
        "molecular_delta_st_rpa",
        "solid_delta_st_rpa",
    }
)
CAPABILITY_STATUSES = frozenset({"BLOCKED", "TESTABLE", "EXPERIMENTAL", "ENABLED"})
ADMISSION_LEVELS = ["L0", "L1", "L2", "L3", "L4"]


class ProfileError(ValueError):
    """Raised when a compatibility profile is incomplete or malformed."""


def _packaged_profile_dir() -> Path:
    return Path(__file__).resolve().parent / "profiles"


def _repository_profile_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "profiles"


def list_profiles() -> tuple[str, ...]:
    return tuple(PROFILE_NAMES)


def default_profile_path() -> Path:
    return _registered_profile_path(DEFAULT_PROFILE_ID)


def _registered_profile_path(profile_id: str) -> Path:
    try:
        name = PROFILE_NAMES[profile_id]
    except KeyError as exc:
        raise ProfileError(f"unknown profile_id: {profile_id}") from exc
    packaged = _packaged_profile_dir() / name
    if packaged.is_file():
        return packaged
    return _repository_profile_dir() / name


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


def _validate_components(profile: dict[str, Any]) -> dict[str, Any]:
    components = _require_mapping(profile, "components", "profile")
    for name in ("abacus", "librpa", "pyatb"):
        entry = _require_mapping(components, name, "components")
        _validate_revision(name, entry)
        for key in ("repository", "ref"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise ProfileError(f"{name}.{key} must be a non-empty string")
    return components


def _validate_contract(profile: dict[str, Any], *, schema_version: int) -> None:
    contract = _require_mapping(profile, "contract", "profile")
    for name in ("abacus", "librpa", "pyatb_adapter"):
        _require_mapping(contract, name, "contract")
    helpers = _require_mapping(contract, "workflow_helpers", "contract")
    if set(helpers) != WORKFLOW_HELPERS:
        raise ProfileError("contract.workflow_helpers must list the approved helper quartet")
    if any(
        not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value)
        for value in helpers.values()
    ):
        raise ProfileError("contract.workflow_helpers values must be SHA-256 digests")
    if schema_version == 1:
        return

    abacus = contract["abacus"]
    librpa = contract["librpa"]
    abacus_production = _require_mapping(abacus, "production", "contract.abacus")
    librpa_production = _require_mapping(librpa, "production", "contract.librpa")
    if abacus_production.get("out_librpa_reader_version") != 1:
        raise ProfileError("schema v2 production requires ABACUS reader v1")
    if (
        librpa_production.get("version_coul_reader") != 1
        or librpa_production.get("version_lri_reader") != 1
    ):
        raise ProfileError("schema v2 production requires LibRPA reader v1")
    symmetry = _require_mapping(contract, "symmetry", "contract")
    if symmetry.get("source") != "stru_out":
        raise ProfileError("contract.symmetry.source must be stru_out")
    if symmetry.get("rotation_reconstruction") != "librpa":
        raise ProfileError("contract.symmetry.rotation_reconstruction must be librpa")
    if symmetry.get("copy_legacy_sidecars") != []:
        raise ProfileError("contract.symmetry.copy_legacy_sidecars must be empty")


def _validate_v1_capabilities(profile: dict[str, Any], components: dict[str, Any]) -> None:
    capabilities = _require_mapping(profile, "capabilities", "profile")
    periodic_3d = _require_mapping(capabilities, "periodic_3d_gw", "capabilities")
    if periodic_3d.get("status") != "ENABLED":
        raise ProfileError("capabilities.periodic_3d_gw.status must be ENABLED")
    strict_2d = _require_mapping(capabilities, "strict_2d_gw", "capabilities")
    if strict_2d.get("status") != "BLOCKED":
        raise ProfileError("capabilities.strict_2d_gw.status must be BLOCKED")
    if strict_2d.get("reason_code") != "LIBRPA_070_STRICT_2D_INVALID":
        raise ProfileError(
            "capabilities.strict_2d_gw.reason_code must be LIBRPA_070_STRICT_2D_INVALID"
        )
    if strict_2d.get("component") != "librpa":
        raise ProfileError("capabilities.strict_2d_gw.component must be librpa")
    if strict_2d.get("component_revision") != components["librpa"]["revision"]:
        raise ProfileError(
            "capabilities.strict_2d_gw component revision must match the pinned LibRPA revision"
        )
    requirements = strict_2d.get("enablement_requires")
    if (
        not isinstance(requirements, list)
        or len(requirements) < 4
        or any(not isinstance(item, str) or not item for item in requirements)
    ):
        raise ProfileError(
            "capabilities.strict_2d_gw.enablement_requires must list at least four requirements"
        )


def _validate_v2_capabilities(profile: dict[str, Any]) -> None:
    capabilities = _require_mapping(profile, "capabilities", "profile")
    if set(capabilities) != V2_CAPABILITIES:
        raise ProfileError("schema v2 capabilities must list the four admission routes")
    for route_id in sorted(V2_CAPABILITIES):
        capability = _require_mapping(capabilities, route_id, "capabilities")
        status = capability.get("status")
        if status not in CAPABILITY_STATUSES:
            raise ProfileError(f"capabilities.{route_id}.status is invalid")
        if capability.get("admission_level") not in ADMISSION_LEVELS:
            raise ProfileError(f"capabilities.{route_id}.admission_level is invalid")
        required = capability.get("experimental_requires")
        if required != ["L0", "L1", "L2", "L3"]:
            raise ProfileError(
                f"capabilities.{route_id}.experimental_requires must be L0 through L3"
            )

    admission = _require_mapping(profile, "admission", "profile")
    if admission.get("levels") != ADMISSION_LEVELS:
        raise ProfileError("admission.levels must be L0 through L4")
    limits = _require_mapping(admission, "fisherd_limits", "admission")
    if limits.get("compile_jobs_max") != 16 or limits.get("execution_threads_max") != 48:
        raise ProfileError("admission.fisherd_limits must enforce 16 build jobs and 48 threads")
    promotion = _require_mapping(admission, "promotion", "admission")
    if promotion.get("automatic") is not False or promotion.get("reviewed_commit") is not True:
        raise ProfileError("admission promotion must require a reviewed commit")


def validate_profile(profile: dict[str, Any]) -> None:
    schema_version = profile.get("schema_version")
    if schema_version not in {1, 2}:
        raise ProfileError("schema_version must be 1 or 2")
    if not isinstance(profile.get("profile_id"), str) or not profile["profile_id"]:
        raise ProfileError("profile_id must be a non-empty string")

    components = _validate_components(profile)
    if schema_version == 1:
        _validate_v1_capabilities(profile, components)
    else:
        _validate_v2_capabilities(profile)
    _validate_contract(profile, schema_version=schema_version)


def load_profile(
    path: str | Path | None = None,
    *,
    profile_id: str | None = None,
) -> dict[str, Any]:
    if path is not None and profile_id is not None:
        raise ProfileError("path and profile_id are mutually exclusive")
    profile_path = Path(path) if path is not None else _registered_profile_path(
        profile_id or DEFAULT_PROFILE_ID
    )
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
