from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .errors import OMLError
from .provenance import digest_json


PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SLURM_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SSH_HOST_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,254}$")
REMOTE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9_./-]+$")
REQUIRED_RUNTIME_STRINGS = ("python", "mpi_launcher", "abacus", "librpa")
REQUIRED_RUNTIME_INTS = ("mpi_ranks", "pyatb_mpi_ranks", "omp_threads")
PLACEHOLDER_FRAGMENTS = ("/path/to/", "your-", "replace-me", "example.invalid")


@dataclass(frozen=True)
class ExecutionProfile:
    profile_id: str
    source_path: Path
    transport: str
    allowed_source_roots: tuple[Path, ...]
    allowed_run_roots: tuple[Path, ...]
    state_db: Path
    scheduler: dict[str, str]
    resources: dict[str, str | int]
    runtime: dict[str, str | int]
    sources: dict[str, str]
    ssh: dict[str, str] | None = None


def execution_profile_payload(profile: ExecutionProfile) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "profile_id": profile.profile_id,
        "transport": profile.transport,
        "allowed_source_roots": [str(path) for path in profile.allowed_source_roots],
        "allowed_run_roots": [str(path) for path in profile.allowed_run_roots],
        "state_db": str(profile.state_db),
        "scheduler": dict(profile.scheduler),
        "resources": dict(profile.resources),
        "runtime": dict(profile.runtime),
        "sources": dict(profile.sources),
        "ssh": dict(profile.ssh) if profile.ssh is not None else None,
    }


def execution_profile_receipt(
    profile: ExecutionProfile,
    version_evidence: dict[str, Any],
) -> dict[str, Any]:
    payload = execution_profile_payload(profile)
    return {
        "schema_version": 1,
        "execution_profile": payload,
        "execution_profile_digest": digest_json(payload),
        "version_evidence": version_evidence,
    }


def default_profile_roots() -> tuple[Path, ...]:
    configured = os.environ.get("OML_EXECUTION_PROFILE_ROOTS", "")
    roots = [Path(item).expanduser().resolve() for item in configured.split(os.pathsep) if item]
    packaged = Path(__file__).resolve().parents[1] / "registry" / "execution-profiles"
    roots.append(packaged)
    return tuple(dict.fromkeys(roots))


def _profile_error(message: str, path: Path | None = None) -> OMLError:
    return OMLError(
        "PROFILE_INVALID",
        message,
        evidence=((str(path),) if path is not None else ()),
        recovery="repair the administrator-managed execution profile before enabling controlled execution",
    )


def _absolute_paths(data: dict[str, Any], key: str, path: Path) -> tuple[Path, ...]:
    values = data.get(key)
    if not isinstance(values, list) or not values:
        raise _profile_error(f"{key} must be a non-empty array", path)
    resolved: list[Path] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise _profile_error(f"{key} entries must be non-empty strings", path)
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise _profile_error(f"{key} entries must be absolute paths", path)
        resolved.append(candidate.resolve())
    return tuple(resolved)


def _contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(fragment in lowered for fragment in PLACEHOLDER_FRAGMENTS)
    if isinstance(value, dict):
        return any(_contains_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_placeholder(item) for item in value)
    return False


def _validate_programs(mapping: Any, keys: Iterable[str], label: str, path: Path) -> dict[str, str]:
    if not isinstance(mapping, dict):
        raise _profile_error(f"{label} must be an object", path)
    result: dict[str, str] = {}
    for key in keys:
        value = mapping.get(key)
        if not isinstance(value, str) or not value:
            raise _profile_error(f"{label}.{key} must be a non-empty string", path)
        if not Path(value).is_absolute():
            raise _profile_error(f"{label}.{key} must be an absolute executable path", path)
        result[key] = value
    return result


def load_execution_profile(
    profile_id: str,
    *,
    roots: Iterable[str | Path] | None = None,
) -> ExecutionProfile:
    if not PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise OMLError(
            "PROFILE_ID_INVALID",
            f"invalid execution profile ID: {profile_id}",
            evidence=(profile_id,),
            recovery="use a registered lowercase profile ID, not a file path",
        )
    search_roots = tuple(Path(root).expanduser().resolve() for root in (roots or default_profile_roots()))
    candidates = [root / f"{profile_id}.json" for root in search_roots]
    profile_path = next((path for path in candidates if path.is_file()), None)
    if profile_path is None:
        raise OMLError(
            "PROFILE_NOT_FOUND",
            f"execution profile {profile_id!r} is not registered",
            evidence=tuple(str(path) for path in candidates),
            recovery="install an approved execution profile in OML_EXECUTION_PROFILE_ROOTS",
        )
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _profile_error(f"cannot parse execution profile: {exc}", profile_path) from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise _profile_error("schema_version must be 1", profile_path)
    if data.get("profile_id") != profile_id:
        raise _profile_error("profile_id does not match the requested ID", profile_path)
    if data.get("enabled") is not True:
        raise OMLError(
            "PROFILE_DISABLED",
            f"execution profile {profile_id!r} is disabled",
            evidence=(str(profile_path),),
            recovery="have an administrator review and enable this profile",
        )
    if _contains_placeholder(data):
        raise _profile_error("profile contains unresolved placeholder values", profile_path)

    transport = data.get("transport")
    if transport not in {"local", "ssh"}:
        raise _profile_error("transport must be local or ssh", profile_path)
    allowed_source_roots = _absolute_paths(data, "allowed_source_roots", profile_path)
    allowed_run_roots = _absolute_paths(data, "allowed_run_roots", profile_path)
    state_db_raw = data.get("state_db")
    if not isinstance(state_db_raw, str) or not Path(state_db_raw).expanduser().is_absolute():
        raise _profile_error("state_db must be an absolute path", profile_path)
    state_db = Path(state_db_raw).expanduser().resolve()
    scheduler = _validate_programs(
        data.get("scheduler"),
        ("submit_program", "status_program", "history_program"),
        "scheduler",
        profile_path,
    )
    resources_raw = data.get("resources")
    if not isinstance(resources_raw, dict):
        raise _profile_error("resources must be an object", profile_path)
    partition = resources_raw.get("partition")
    if not isinstance(partition, str) or not SLURM_NAME_PATTERN.fullmatch(partition):
        raise _profile_error("resources.partition contains unsafe characters", profile_path)
    resources: dict[str, str | int] = {"partition": partition}
    for key in (
        "nodes",
        "ntasks_per_node",
        "cpus_per_task",
        "memory_mb",
        "walltime_minutes",
    ):
        value = resources_raw.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise _profile_error(f"resources.{key} must be a positive integer", profile_path)
        resources[key] = value

    runtime_raw = data.get("runtime")
    if not isinstance(runtime_raw, dict):
        raise _profile_error("runtime must be an object", profile_path)
    runtime: dict[str, str | int] = {}
    for key in REQUIRED_RUNTIME_STRINGS:
        value = runtime_raw.get(key)
        if not isinstance(value, str) or not value or not Path(value).is_absolute():
            raise _profile_error(f"runtime.{key} must be an absolute path", profile_path)
        runtime[key] = value
    for key in REQUIRED_RUNTIME_INTS:
        value = runtime_raw.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise _profile_error(f"runtime.{key} must be a positive integer", profile_path)
        runtime[key] = value

    sources = _validate_programs(
        data.get("sources"),
        ("git_program", "abacus", "librpa", "pyatb"),
        "sources",
        profile_path,
    )

    ssh: dict[str, str] | None = None
    if transport == "ssh":
        ssh_raw = data.get("ssh")
        if not isinstance(ssh_raw, dict):
            raise _profile_error("ssh transport requires an ssh object", profile_path)
        ssh = {}
        for key in ("host", "remote_run_root"):
            value = ssh_raw.get(key)
            if not isinstance(value, str) or not value:
                raise _profile_error(f"ssh.{key} must be a non-empty string", profile_path)
            ssh[key] = value
        if not Path(ssh["remote_run_root"]).is_absolute():
            raise _profile_error("ssh.remote_run_root must be absolute", profile_path)
        if not SSH_HOST_PATTERN.fullmatch(ssh["host"]):
            raise _profile_error("ssh.host contains unsafe characters", profile_path)
        remote_parts = Path(ssh["remote_run_root"]).parts
        if (
            not REMOTE_PATH_PATTERN.fullmatch(ssh["remote_run_root"])
            or ".." in remote_parts
        ):
            raise _profile_error("ssh.remote_run_root contains unsafe characters", profile_path)
        for component in ("abacus", "librpa", "pyatb"):
            if not REMOTE_PATH_PATTERN.fullmatch(sources[component]) or ".." in Path(
                sources[component]
            ).parts:
                raise _profile_error(f"sources.{component} contains unsafe characters", profile_path)
        ssh.update(
            _validate_programs(
                ssh_raw,
                ("ssh_program", "rsync_program"),
                "ssh",
                profile_path,
            )
        )

    return ExecutionProfile(
        profile_id=profile_id,
        source_path=profile_path,
        transport=transport,
        allowed_source_roots=allowed_source_roots,
        allowed_run_roots=allowed_run_roots,
        state_db=state_db,
        scheduler=scheduler,
        resources=resources,
        runtime=runtime,
        sources=sources,
        ssh=ssh,
    )
