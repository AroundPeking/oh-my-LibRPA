from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_ID = "abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08"
V2_PROFILE_ID = "abacus-librpa-2026-08-30-v2"
V3_PROFILE_ID = "abacus-librpa-2026-08-30-v3"
STRICT_2D_SOS_RPA_PROFILE_ID = "abacus-librpa-2026-09-02-strict2d-sos-rpa-v1"
PROFILE_NAMES = {
    DEFAULT_PROFILE_ID: "abacus-librpa-pyatb-2026-08.json",
    V2_PROFILE_ID: "abacus-librpa-pyatb-2026-08-v2.json",
    V3_PROFILE_ID: "abacus-librpa-pyatb-2026-08-v3.json",
    STRICT_2D_SOS_RPA_PROFILE_ID: "abacus-librpa-strict2d-sos-rpa-2026-09-v1.json",
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
STRICT_2D_SOS_RPA_CAPABILITIES = frozenset({"strict_2d_sos_rpa"})
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
    librpa = contract["librpa"]
    frequency_grids = _require_mapping(
        librpa,
        "frequency_grids",
        "contract.librpa",
    )
    recognized_types = frequency_grids.get("recognized_types")
    if (
        not isinstance(recognized_types, list)
        or not recognized_types
        or any(not isinstance(value, str) or not value for value in recognized_types)
        or frequency_grids.get("default") not in recognized_types
    ):
        raise ProfileError(
            "contract.librpa.frequency_grids must define a default in recognized_types"
        )
    production_types = frequency_grids.get("production_types")
    time_grid_types = frequency_grids.get("time_grid_types")
    debug_only_types = frequency_grids.get("debug_only_types")
    if (
        not isinstance(production_types, list)
        or not production_types
        or any(value not in recognized_types for value in production_types)
        or frequency_grids.get("default") not in production_types
        or not isinstance(time_grid_types, list)
        or any(value not in recognized_types for value in time_grid_types)
        or any(value not in time_grid_types for value in production_types)
        or not isinstance(debug_only_types, list)
        or any(value not in time_grid_types for value in debug_only_types)
        or set(debug_only_types) & set(production_types)
    ):
        raise ProfileError(
            "contract.librpa.frequency_grids production/time/debug type sets are invalid"
        )
    minimax_counts = frequency_grids.get("minimax_nfreq_supported")
    if (
        not isinstance(minimax_counts, list)
        or not minimax_counts
        or any(not isinstance(value, int) or value <= 0 for value in minimax_counts)
        or minimax_counts != sorted(set(minimax_counts))
    ):
        raise ProfileError(
            "contract.librpa.frequency_grids.minimax_nfreq_supported must be sorted positive integers"
        )
    if (
        not isinstance(frequency_grids.get("default_nfreq"), int)
        or frequency_grids["default_nfreq"] not in minimax_counts
    ):
        raise ProfileError(
            "contract.librpa.frequency_grids.default_nfreq must be a supported minimax count"
        )
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
    abacus_production = _require_mapping(abacus, "production", "contract.abacus")
    librpa_production = _require_mapping(librpa, "production", "contract.librpa")
    if abacus_production.get("out_librpa_reader_version") != 1:
        raise ProfileError("schema v2 production requires ABACUS reader v1")
    if (
        librpa_production.get("version_coul_reader") != 1
        or librpa_production.get("version_lri_reader") != 1
    ):
        raise ProfileError("schema v2 production requires LibRPA reader v1")
    if profile.get("profile_id") == V3_PROFILE_ID:
        sternheimer_abacus = _require_mapping(abacus, "sternheimer", "contract.abacus")
        sternheimer_librpa = _require_mapping(librpa, "sternheimer_rpa", "contract.librpa")
        response_prefix = "v1_sternheimer_coulomb_iq_"
        if (
            sternheimer_abacus.get("response_coulomb_prefix") != response_prefix
            or sternheimer_abacus.get("response_coulomb_format") != "v1"
        ):
            raise ProfileError("schema v2 Sternheimer output requires the dedicated Coulomb v1 prefix")
        if (
            sternheimer_librpa.get("task") != "sternheimer_rpa"
            or sternheimer_librpa.get("prefix_coul_full") != response_prefix
            or sternheimer_librpa.get("version_coul_reader") != 1
            or sternheimer_librpa.get("ordinary_reader_coulomb_role") != "diagnostic_only"
        ):
            raise ProfileError("schema v2 LibRPA Sternheimer task must select the dedicated Coulomb v1 metric")
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
    strict_2d_sos_rpa = profile.get("profile_id") == STRICT_2D_SOS_RPA_PROFILE_ID
    expected_capabilities = (
        STRICT_2D_SOS_RPA_CAPABILITIES if strict_2d_sos_rpa else V2_CAPABILITIES
    )
    if set(capabilities) != expected_capabilities:
        description = (
            "the strict_2d_sos_rpa admission route"
            if strict_2d_sos_rpa
            else "the four admission routes"
        )
        raise ProfileError(f"schema v2 capabilities must list {description}")
    for route_id in sorted(expected_capabilities):
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
    if strict_2d_sos_rpa:
        route_capability = capabilities["strict_2d_sos_rpa"]
        if (
            route_capability.get("status") != "TESTABLE"
            or route_capability.get("admission_level") != "L3"
        ):
            raise ProfileError(
                "capabilities.strict_2d_sos_rpa must remain TESTABLE at L3"
            )
        limits = _require_mapping(admission, "df_dcu_limits", "admission")
        required_limits = {
            "partition": "normal",
            "work_root": "/work1",
            "nodes": 4,
            "mpi_ranks": 4,
            "omp_threads_per_rank": 30,
            "mkl_threads_per_rank": 30,
            "mpi_launcher": "mpirun -ppn 1",
        }
        if any(limits.get(key) != value for key, value in required_limits.items()):
            raise ProfileError(
                "admission.df_dcu_limits must enforce normal, /work1, 4 ranks, and 30 threads"
            )
        route_contract = _require_mapping(
            _require_mapping(profile, "contract", "profile"),
            "strict_2d_sos_rpa",
            "contract",
        )
        if (
            route_contract.get("task") != "rpa"
            or route_contract.get("response_method") != "sos"
            or route_contract.get("reader_format") != "v1"
            or route_contract.get("coulomb") != "full_2d_ewald"
            or route_contract.get("coulomb_head_artifact")
            != "librpa_2d_coulomb_head.dat"
            or route_contract.get("nfreq") != 16
            or route_contract.get("headwing") != "qavg"
            or route_contract.get("head_only") is not False
            or route_contract.get("producer_policy") != "reuse_validated_only"
            or route_contract.get("allow_abacus_rerun") is not False
            or route_contract.get("allow_pyatb_rerun") is not False
        ):
            raise ProfileError("contract.strict_2d_sos_rpa is not the pinned replay-only route")
        if route_contract.get("required_input") != {
            "replace_w_head": True,
            "option_dielect_func": 3,
            "use_2d_dielectric": True,
            "use_pyatb": True,
            "rpa_headwing_mode": "qavg",
            "rpa_headwing_body_start": 1,
        }:
            raise ProfileError("contract.strict_2d_sos_rpa qavg input contract has drifted")
        if route_contract.get("k_mesh_acceptance") != {
            "validated_scope": "four_mesh_functional_and_numerical_not_asymptotic",
            "minimum_meshes_for_exponent_fit": 3,
            "require_stable_asymptotic_fit": True,
            "forbid_convergence_exponent_claim": True,
        }:
            raise ProfileError(
                "contract.strict_2d_sos_rpa must keep the four-mesh series below convergence promotion"
            )
        librpa = profile["components"]["librpa"]
        if not SHA256_PATTERN.fullmatch(str(librpa.get("executable_sha256", ""))):
            raise ProfileError("components.librpa.executable_sha256 must be a SHA-256 digest")
    else:
        limits = _require_mapping(admission, "fisherd_limits", "admission")
        if limits.get("compile_jobs_max") != 16 or limits.get("execution_threads_max") != 48:
            raise ProfileError("admission.fisherd_limits must enforce 16 build jobs and 48 threads")
    promotion = _require_mapping(admission, "promotion", "admission")
    if promotion.get("automatic") is not False or promotion.get("reviewed_commit") is not True:
        raise ProfileError("admission promotion must require a reviewed commit")
    if strict_2d_sos_rpa and promotion.get(
        "mesh_series_is_convergence_evidence_without_stable_fit"
    ) is not False:
        raise ProfileError(
            "strict-2D SOS-RPA promotion must require a stable asymptotic fit"
        )


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
