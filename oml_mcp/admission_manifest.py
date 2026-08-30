from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .profiles import V2_CAPABILITIES, V2_PROFILE_ID, load_profile


DEFAULT_MANIFEST_NAME = "fisherd-v2-2026-08-30.json"
ADMISSION_LEVELS = ("L0", "L1", "L2", "L3")


class AdmissionManifestError(ValueError):
    """Raised when an admission campaign drifts from its pinned profile."""


def _packaged_manifest_path() -> Path:
    return Path(__file__).resolve().parent / "admission_manifests" / DEFAULT_MANIFEST_NAME


def _repository_manifest_path() -> Path:
    return Path(__file__).resolve().parents[1] / "admission" / DEFAULT_MANIFEST_NAME


def default_admission_manifest_path() -> Path:
    packaged = _packaged_manifest_path()
    return packaged if packaged.is_file() else _repository_manifest_path()


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


def validate_admission_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("manifest_schema") != "oml.admission-manifest.v1":
        raise AdmissionManifestError("manifest_schema must be oml.admission-manifest.v1")
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


def load_admission_manifest(path: str | Path | None = None) -> dict[str, Any]:
    manifest_path = Path(path) if path is not None else default_admission_manifest_path()
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
