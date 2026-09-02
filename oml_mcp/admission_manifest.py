from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .profiles import (
    STRICT_2D_SOS_RPA_PROFILE_ID,
    V2_CAPABILITIES,
    V2_PROFILE_ID,
    load_profile,
)


DEFAULT_MANIFEST_NAME = "fisherd-v2-2026-08-30.json"
DEFAULT_MANIFEST_ID = "fisherd-v2-2026-08-30"
STRICT_2D_SOS_RPA_MANIFEST_ID = "df-dcu-strict2d-sos-rpa-2026-09-02-v1"
MANIFEST_NAMES = {
    DEFAULT_MANIFEST_ID: DEFAULT_MANIFEST_NAME,
    STRICT_2D_SOS_RPA_MANIFEST_ID: "df-dcu-strict2d-sos-rpa-2026-09-02-v1.json",
}
ADMISSION_LEVELS = ("L0", "L1", "L2", "L3")
ABACUS_DEPENDENCY_SOURCES = {
    "libri": {
        "component": "librpa",
        "path": "thirdparty/LibRI",
        "tree": "d67a9367dcc6c2b29f3833840da3dbacb1fb2b35",
    },
    "libcomm": {
        "component": "librpa",
        "path": "thirdparty/LibComm",
        "tree": "323fc5cb988ffa9d8eea646872706e11f2e4810d",
    },
}


class AdmissionManifestError(ValueError):
    """Raised when an admission campaign drifts from its pinned profile."""


def _packaged_manifest_path() -> Path:
    return Path(__file__).resolve().parent / "admission_manifests" / DEFAULT_MANIFEST_NAME


def _repository_manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "admission" / DEFAULT_MANIFEST_NAME


def default_admission_manifest_path() -> Path:
    packaged = _packaged_manifest_path()
    return packaged if packaged.is_file() else _repository_manifest_path()


def _registered_manifest_path(manifest_id: str) -> Path:
    try:
        name = MANIFEST_NAMES[manifest_id]
    except KeyError as exc:
        raise AdmissionManifestError(f"unknown manifest_id: {manifest_id}") from exc
    packaged = Path(__file__).resolve().parent / "admission_manifests" / name
    if packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[1] / "admission" / name


def _require_mapping(parent: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise AdmissionManifestError(f"{context}.{key} must be an object")
    return value


def _require_non_empty_string(parent: dict[str, Any], key: str, context: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise AdmissionManifestError(f"{context}.{key} must be a non-empty string")
    return value


def _validate_strict_2d_sos_rpa_manifest(manifest: dict[str, Any]) -> None:
    profile = load_profile(profile_id=STRICT_2D_SOS_RPA_PROFILE_ID)
    if manifest.get("manifest_id") != STRICT_2D_SOS_RPA_MANIFEST_ID:
        raise AdmissionManifestError(
            f"manifest_id must be {STRICT_2D_SOS_RPA_MANIFEST_ID}"
        )
    _require_non_empty_string(manifest, "campaign_id", "manifest")
    sources = _require_mapping(manifest, "sources", "manifest")
    if set(sources) != {"abacus", "librpa", "pyatb"}:
        raise AdmissionManifestError("sources must contain abacus, librpa, and pyatb")
    for name, expected in profile["components"].items():
        actual = _require_mapping(sources, name, "sources")
        for key in ("repository", "ref", "revision"):
            if actual.get(key) != expected[key]:
                raise AdmissionManifestError(
                    f"sources.{name}.{key} must match profile {STRICT_2D_SOS_RPA_PROFILE_ID}"
                )
    if sources["librpa"].get("executable_sha256") != profile["components"]["librpa"][
        "executable_sha256"
    ]:
        raise AdmissionManifestError("sources.librpa.executable_sha256 must match the profile")

    host = _require_mapping(manifest, "host", "manifest")
    if host.get("alias") != "df_dcu":
        raise AdmissionManifestError("host.alias must be df_dcu")
    if host.get("partition") != "normal":
        raise AdmissionManifestError("host.partition must be normal")
    if host.get("work_root") != "/work1" or not str(host.get("remote_root", "")).startswith(
        "/work1/"
    ):
        raise AdmissionManifestError("all host work paths must be under /work1")

    expected_limits = profile["admission"]["df_dcu_limits"]
    limits = _require_mapping(manifest, "limits", "manifest")
    for key in (
        "nodes",
        "mpi_ranks",
        "omp_threads_per_rank",
        "mkl_threads_per_rank",
        "mpi_launcher",
    ):
        if limits.get(key) != expected_limits[key]:
            raise AdmissionManifestError(f"limits.{key} must match the df_dcu profile")

    route = _require_mapping(manifest, "route", "manifest")
    if (
        route.get("route_id") != "strict_2d_sos_rpa"
        or route.get("status") != "TESTABLE"
        or route.get("response_method") != "sos"
        or route.get("execution_stages") != ["librpa"]
        or route.get("producer_policy") != "reuse_validated_only"
    ):
        raise AdmissionManifestError("route must be the TESTABLE LibRPA-only strict_2d_sos_rpa replay")
    contract = _require_mapping(manifest, "contract", "manifest")
    required_contract = {
        "reader_format": "v1",
        "task": "rpa",
        "nfreq": 16,
        "coulomb": "full_2d_ewald",
        "coulomb_head_artifact": "librpa_2d_coulomb_head.dat",
        "headwing": "qavg",
        "head_only": False,
        "allow_abacus_rerun": False,
        "allow_pyatb_rerun": False,
    }
    if any(contract.get(key) != value for key, value in required_contract.items()):
        raise AdmissionManifestError("contract does not match the pinned strict-2D SOS-RPA route")

    levels = manifest.get("levels")
    if not isinstance(levels, list) or tuple(
        level.get("level") for level in levels if isinstance(level, dict)
    ) != ADMISSION_LEVELS:
        raise AdmissionManifestError("levels must be ordered L0 through L3")
    case_ids: set[str] = set()
    covered_routes: set[str] = set()
    gates: set[str] = set()
    for level in levels:
        cases = level.get("cases")
        if not isinstance(cases, list) or not cases:
            raise AdmissionManifestError(f"levels.{level['level']}.cases must be non-empty")
        for case in cases:
            case_id = _require_non_empty_string(case, "case_id", "case")
            if case_id in case_ids:
                raise AdmissionManifestError(f"duplicate case_id: {case_id}")
            case_ids.add(case_id)
            covered_routes.add(str(case.get("route_id")))
            case_gates = case.get("gates")
            if not isinstance(case_gates, list) or not case_gates:
                raise AdmissionManifestError(f"case {case_id} gates must be non-empty")
            gates.update(str(gate) for gate in case_gates)
    if covered_routes != {"strict_2d_sos_rpa"}:
        raise AdmissionManifestError("route coverage must contain only strict_2d_sos_rpa")
    required_gates = {
        "exact_librpa_revision",
        "executable_sha256",
        "partition_normal",
        "work_paths_under_work1",
        "abacus_rerun_prohibited",
        "pyatb_rerun_prohibited",
        "source_tests_pass",
        "producer_complete",
        "reader_v1",
        "full_2d_ewald",
        "coulomb_head_artifact",
        "duplicate_job_check",
        "mpi_world_size_4",
        "mpi_ppn_1",
        "omp_mkl_30",
        "qavg_record_count",
        "qavg_weight_sum",
        "finite_energies",
        "negligible_imaginary_energy",
        "qsum_matches_total",
        "lu_info_zero",
        "antihermitian_residual",
        "mpi_singleton_consistency",
        "k_mesh_validation_scope",
    }
    missing_gates = sorted(required_gates - gates)
    if missing_gates:
        raise AdmissionManifestError(f"strict-2D SOS-RPA gates are incomplete: {missing_gates}")

    validated_cases = manifest.get("validated_cases")
    if (
        not isinstance(validated_cases, list)
        or len(validated_cases) != 4
        or not all(isinstance(case, dict) for case in validated_cases)
        or {case.get("mesh") for case in validated_cases} != {8, 10, 12, 16}
    ):
        raise AdmissionManifestError(
            "validated_cases must contain the N8, N10, N12, and N16 validations"
        )
    if any(case.get("status") != "PASS" for case in validated_cases):
        raise AdmissionManifestError("validated_cases must pass every recorded gate")
    expected_validated_cases = {
        8: (
            21833983,
            "77b55f6c252c8de2d99c0cf96dae1b398aeaddbcd9ab4b32bfb80b7bc16653b2",
            -0.06924276799691,
            -1.268385066102,
        ),
        10: (
            21836052,
            "43700709662f46924212bdee5f8655af5be8ef93e5f281b34639df8023c6d361",
            -0.04430281538195,
            -1.250904354656,
        ),
        12: (
            21834156,
            "fec00d16bed5a9067e0d846d2a975b5b5c4068363e6ebf1c84f343cee206d99b",
            -0.03075665041071,
            -1.242737105060,
        ),
        16: (
            21836055,
            "717b4ec716465af0eed96dea5c20a6611b02d054efc1898b1e91b7b242b0da18",
            -0.01729559985264,
            -1.235513727806,
        ),
    }
    for case in validated_cases:
        expected = expected_validated_cases[case["mesh"]]
        actual = (
            case.get("job_id"),
            case.get("validation_sha256"),
            case.get("gamma_hartree"),
            case.get("total_hartree"),
        )
        if actual != expected:
            raise AdmissionManifestError(
                f"validated case N{case['mesh']} does not match the immutable remote receipt"
            )

    validation_controls = manifest.get("validation_controls")
    if (
        not isinstance(validation_controls, list)
        or len(validation_controls) != 4
        or not all(isinstance(case, dict) for case in validation_controls)
        or {case.get("mesh") for case in validation_controls} != {8, 10, 12, 16}
    ):
        raise AdmissionManifestError(
            "validation_controls must contain N8, N10, N12, and N16 no-head/wing cases"
        )
    if any(
        case.get("route") != "diagnostic_no_headwing"
        or case.get("physical_route") is not False
        or case.get("status") != "PASS_FINITE_Q_CONTROL_RAW_GAMMA_COMPLEX"
        for case in validation_controls
    ):
        raise AdmissionManifestError(
            "no-head/wing cases are diagnostic controls, not the physical route"
        )
    expected_controls = {
        8: (
            21836051,
            "aaf088689c18bde12a81f8894e978b21494318a744a7e23dbfb7ba48f553467b",
            -0.06874078563292,
            0.001177389900275,
            -1.267883084,
        ),
        10: (
            21836053,
            "cecd1f66e9c2527f8db7c194f481f3ea53575e67329a4cbe99d3b9d22291d0bf",
            -0.0440523269055,
            0.0004836568334641,
            -1.250653866,
        ),
        12: (
            21836121,
            "40207b14af5adcbc9a2ebe7b2731ac44a6c09deaa22f13fb3232c9d584b0aeb2",
            -0.03072700387026,
            0.0008455291320996,
            -1.242707459,
        ),
        16: (
            21836057,
            "58deba977fba09021bbf51a07778c0a187d36d6ab610ca48c6a9dc0d857a0fb5",
            -0.01729769618594,
            0.0004161330175857,
            -1.235515824,
        ),
    }
    for case in validation_controls:
        expected = expected_controls[case["mesh"]]
        actual = (
            case.get("job_id"),
            case.get("validation_sha256"),
            case.get("gamma_real_hartree"),
            case.get("gamma_imag_hartree"),
            case.get("total_hartree"),
        )
        if actual != expected:
            raise AdmissionManifestError(
                f"diagnostic control N{case['mesh']} does not match the immutable remote receipt"
            )

    k_mesh_claim = _require_mapping(manifest, "k_mesh_claim", "manifest")
    if (
        k_mesh_claim.get("scope") != "four_mesh_functional_and_numerical_not_asymptotic"
        or k_mesh_claim.get("convergence_exponent_established") is not False
        or k_mesh_claim.get("mesh_count") != 4
        or k_mesh_claim.get("minimum_meshes_for_exponent_fit") != 3
        or k_mesh_claim.get("asymptotic_fit_stable") is not False
        or k_mesh_claim.get("comparison_sha256")
        != "5c5d8b1d17a17480fc33693bc67fea0f55e78e83eb7064d3348b095de60dbd8b"
        or k_mesh_claim.get("observed_free_power") != 2.642
        or k_mesh_claim.get("fixed_n_minus_3_rms_millihartree") != 0.399888
        or k_mesh_claim.get("extrapolated_limit_span_millihartree") != 2.092244
    ):
        raise AdmissionManifestError(
            "four meshes validate the route but do not establish asymptotic convergence"
        )


def validate_admission_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("manifest_schema") != "oml.admission-manifest.v1":
        raise AdmissionManifestError("manifest_schema must be oml.admission-manifest.v1")
    if manifest.get("profile_id") == STRICT_2D_SOS_RPA_PROFILE_ID:
        _validate_strict_2d_sos_rpa_manifest(manifest)
        return
    if manifest.get("profile_id") != V2_PROFILE_ID:
        raise AdmissionManifestError(f"profile_id must be {V2_PROFILE_ID}")
    _require_non_empty_string(manifest, "campaign_id", "manifest")

    profile = load_profile(profile_id=V2_PROFILE_ID)
    sources = _require_mapping(manifest, "sources", "manifest")
    if set(sources) != {"abacus", "librpa", "pyatb"}:
        raise AdmissionManifestError("sources must contain abacus, librpa, and pyatb")
    for name, expected in profile["components"].items():
        actual = _require_mapping(sources, name, "sources")
        for key in ("repository", "ref", "revision"):
            if actual.get(key) != expected[key]:
                raise AdmissionManifestError(
                    f"sources.{name}.{key} must match profile {V2_PROFILE_ID}"
                )

    host = _require_mapping(manifest, "host", "manifest")
    _require_non_empty_string(host, "alias", "host")
    remote_root = _require_non_empty_string(host, "remote_root", "host")
    if not remote_root.startswith("/"):
        raise AdmissionManifestError("host.remote_root must be absolute")

    limits = _require_mapping(manifest, "limits", "manifest")
    expected_limits = profile["admission"]["fisherd_limits"]
    for key in ("compile_jobs_max", "execution_threads_max"):
        if limits.get(key) != expected_limits[key]:
            raise AdmissionManifestError(
                f"limits.{key} must be {expected_limits[key]} for Fisherd"
            )

    contract = _require_mapping(manifest, "contract", "manifest")
    if contract.get("reader_format") != "v1":
        raise AdmissionManifestError("contract.reader_format must be v1")
    if contract.get("symmetry_source") != "stru_out":
        raise AdmissionManifestError("contract.symmetry_source must be stru_out")
    if contract.get("copy_legacy_symmetry_sidecars") != []:
        raise AdmissionManifestError("contract.copy_legacy_symmetry_sidecars must be empty")

    builds = _require_mapping(manifest, "builds", "manifest")
    if set(builds) != {"abacus", "librpa", "pyatb"}:
        raise AdmissionManifestError("builds must contain abacus, librpa, and pyatb")
    for name, build in builds.items():
        if not isinstance(build, dict):
            raise AdmissionManifestError(f"builds.{name} must be an object")
        jobs = build.get("compile_jobs", 0)
        if isinstance(jobs, bool) or not isinstance(jobs, int) or not 0 <= jobs <= 16:
            raise AdmissionManifestError(f"builds.{name}.compile_jobs exceeds the limit")
    abacus_build = builds["abacus"]
    dependencies = _require_mapping(abacus_build, "dependency_sources", "builds.abacus")
    for name, expected in ABACUS_DEPENDENCY_SOURCES.items():
        actual = _require_mapping(dependencies, name, "builds.abacus.dependency_sources")
        for key, value in expected.items():
            if actual.get(key) != value:
                raise AdmissionManifestError(
                    f"builds.abacus.dependency_sources.{name}.{key} must match pinned LibRPA"
                )
    required_dependency_options = {
        f"-DLIBRI_DIR={remote_root}/src/librpa/thirdparty/LibRI",
        f"-DLIBCOMM_DIR={remote_root}/src/librpa/thirdparty/LibComm",
    }
    cmake_options = abacus_build.get("cmake_options")
    if not isinstance(cmake_options, list) or not required_dependency_options.issubset(cmake_options):
        raise AdmissionManifestError(
            "builds.abacus.cmake_options must select pinned LibRPA LibRI and LibComm"
        )

    levels = manifest.get("levels")
    if not isinstance(levels, list):
        raise AdmissionManifestError("levels must be an array")
    if tuple(level.get("level") for level in levels if isinstance(level, dict)) != ADMISSION_LEVELS:
        raise AdmissionManifestError("levels must be ordered L0 through L3")

    seen_case_ids: set[str] = set()
    covered_routes: set[str] = set()
    for level in levels:
        cases = level.get("cases")
        if not isinstance(cases, list) or not cases:
            raise AdmissionManifestError(f"levels.{level['level']}.cases must be non-empty")
        for case in cases:
            if not isinstance(case, dict):
                raise AdmissionManifestError("each admission case must be an object")
            case_id = _require_non_empty_string(case, "case_id", "case")
            if case_id in seen_case_ids:
                raise AdmissionManifestError(f"duplicate case_id: {case_id}")
            seen_case_ids.add(case_id)
            route_id = case.get("route_id")
            if route_id is not None:
                if route_id not in V2_CAPABILITIES:
                    raise AdmissionManifestError(f"unknown route_id: {route_id}")
                covered_routes.add(route_id)
            threads = case.get("execution_threads", 1)
            if (
                isinstance(threads, bool)
                or not isinstance(threads, int)
                or not 1 <= threads <= limits["execution_threads_max"]
            ):
                raise AdmissionManifestError(
                    f"case {case_id} execution_threads exceeds the limit"
                )

    if covered_routes != V2_CAPABILITIES:
        missing = sorted(V2_CAPABILITIES - covered_routes)
        raise AdmissionManifestError(f"route coverage is incomplete: {missing}")


def load_admission_manifest(
    path: str | Path | None = None,
    *,
    manifest_id: str | None = None,
) -> dict[str, Any]:
    if path is not None and manifest_id is not None:
        raise AdmissionManifestError("path and manifest_id are mutually exclusive")
    manifest_path = (
        Path(path)
        if path is not None
        else _registered_manifest_path(manifest_id)
        if manifest_id is not None
        else default_admission_manifest_path()
    )
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AdmissionManifestError(f"admission manifest not found: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise AdmissionManifestError(f"invalid admission manifest JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise AdmissionManifestError("admission manifest root must be an object")
    validate_admission_manifest(data)
    return copy.deepcopy(data)
