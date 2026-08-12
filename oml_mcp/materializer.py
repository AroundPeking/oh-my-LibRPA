from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import OMLError
from .execution_profiles import ExecutionProfile
from .planner import plan_case
from .provenance import ProvenanceError, digest_json, sha256_file
from .stage_templates import CONTROLLED_PERIODIC_STAGES, render_env, render_stage_script
from .state import StateStore
from .validators import validate_case


def _utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _is_under(path: Path, roots: tuple[Path, ...]) -> bool:
    return any(path.is_relative_to(root) for root in roots)


def _match_periodic_plan(source: Path, plan_digest: str):
    candidates = tuple(
        plan_case(
            source,
            task="gw",
            system_type="solid",
            use_symmetry=use_symmetry,
            soc=False,
            headwing=True,
        )
        for use_symmetry in (False, True)
    )
    matches = tuple(plan for plan in candidates if plan.digest == plan_digest)
    if len(matches) != 1:
        raise OMLError(
            "STALE_PLAN",
            "current execution inputs and approved periodic routes do not match the supplied plan digest",
            evidence=(plan_digest, *(plan.digest for plan in candidates)),
            recovery="call plan_case again and review the new digest before preparing a run",
        )
    return matches[0]


def _plan_receipt(source: Path, plan: Any) -> dict[str, Any]:
    data = plan.to_dict()
    data["source_path"] = str(source)
    return data


def _copy_manifest(source: Path, target: Path, manifest: tuple[dict[str, Any], ...]) -> None:
    for item in manifest:
        relative = Path(str(item["path"]))
        source_path = source / relative
        resolved = source_path.resolve()
        if not resolved.is_relative_to(source) or source_path.is_symlink():
            raise OMLError(
                "SOURCE_UNSAFE",
                "execution input is a symlink or escapes the approved source root",
                evidence=(str(source_path), str(resolved)),
                recovery="replace the link with an immutable regular file inside the source directory",
            )
        if sha256_file(resolved) != item["sha256"]:
            raise OMLError(
                "STALE_PLAN",
                "execution input changed while preparing the run",
                evidence=(str(source_path),),
                recovery="re-plan from a stable source snapshot",
            )
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved, destination, follow_symlinks=False)


def _materialized_manifest(run_dir: Path) -> tuple[dict[str, Any], ...]:
    items = []
    for path in sorted(run_dir.rglob("*"), key=lambda item: item.relative_to(run_dir).as_posix()):
        relative = path.relative_to(run_dir)
        controlled_metadata = relative in {
            Path(".oml/env.sh"),
            Path(".oml/execution.json"),
        } or relative.parts[:2] == (".oml", "stages")
        if not path.is_file() or (relative.parts[:1] == (".oml",) and not controlled_metadata):
            continue
        stat = path.stat()
        items.append(
            {
                "path": relative.as_posix(),
                "size": stat.st_size,
                "sha256": sha256_file(path),
            }
        )
    return tuple(items)


def prepare_run(
    source_path: str | Path,
    plan_digest: str,
    profile: ExecutionProfile,
    *,
    execution_receipt: dict[str, Any],
) -> dict[str, Any]:
    source = Path(source_path).expanduser().resolve()
    if not source.is_dir() or not _is_under(source, profile.allowed_source_roots):
        raise OMLError(
            "SOURCE_NOT_ALLOWED",
            "source directory is outside the execution profile's allowed roots",
            evidence=(str(source), *(str(root) for root in profile.allowed_source_roots)),
            recovery="use a source directory under an administrator-approved source root",
        )

    try:
        plan = _match_periodic_plan(source, plan_digest)
    except ProvenanceError as exc:
        raise OMLError(
            "SOURCE_UNSAFE",
            str(exc),
            evidence=(str(source),),
            recovery="replace escaped links with regular immutable source files",
        ) from exc
    if plan.route not in {"periodic_gw", "periodic_gw_symmetry"} or plan.options["soc"]:
        raise OMLError(
            "ROUTE_NOT_EXECUTABLE",
            "Phase 2 controlled execution supports only non-SOC periodic GW routes",
            evidence=(plan.route,),
            recovery="keep this route on the existing workflow until a dedicated executor is approved",
        )
    report = validate_case(
        source,
        task="gw",
        system_type=str(plan.options["system_type"]),
        use_symmetry=bool(plan.options["use_symmetry"]),
        soc=False,
        stage="input",
    )
    if not report.accepted:
        failed = tuple(gate.gate_id for gate in report.gates if gate.status == "FAIL")
        raise OMLError(
            "GATE_FAILED",
            "input-level gates failed before run materialization",
            evidence=failed,
            recovery="apply the gate repair actions and create a new immutable plan",
            details={"validation": report.to_dict()},
        )

    run_root = profile.allowed_run_roots[0]
    run_id = f"run-{_utc_slug()}-{uuid.uuid4().hex[:10]}"
    final_dir = run_root / run_id
    temporary_dir = run_root / f".{run_id}.preparing"
    if final_dir.exists() or temporary_dir.exists():
        raise OMLError(
            "RUN_CONFLICT",
            "generated run directory already exists",
            evidence=(str(final_dir),),
            recovery="retry preparation to allocate a new run ID",
        )

    run_root.mkdir(parents=True, exist_ok=True)
    temporary_dir.mkdir(mode=0o700)
    try:
        _copy_manifest(source, temporary_dir, plan.source_manifest)
        oml_dir = temporary_dir / ".oml"
        stage_dir = oml_dir / "stages"
        stage_dir.mkdir(parents=True)
        plan_data = _plan_receipt(source, plan)
        (oml_dir / "plan.json").write_text(
            json.dumps(plan_data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (oml_dir / "execution.json").write_text(
            json.dumps(execution_receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        env_path = oml_dir / "env.sh"
        env_path.write_text(
            render_env(profile.runtime, run_id=run_id, plan_digest=plan.digest),
            encoding="utf-8",
        )
        os.chmod(env_path, 0o600)
        for stage in CONTROLLED_PERIODIC_STAGES:
            script = stage_dir / f"{stage}.slurm"
            script.write_text(
                render_stage_script(stage, run_id=run_id, resources=profile.resources),
                encoding="utf-8",
            )
            os.chmod(script, 0o700)
        copied_manifest = _materialized_manifest(temporary_dir)
        manifest_data = {
            "schema_version": 1,
            "run_id": run_id,
            "plan_id": plan.plan_id,
            "plan_digest": plan.digest,
            "source_digest": plan.source_digest,
            "files": copied_manifest,
        }
        manifest_digest = digest_json(manifest_data)
        manifest_data["manifest_digest"] = manifest_digest
        (oml_dir / "manifest.json").write_text(
            json.dumps(manifest_data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary_dir.rename(final_dir)
    except Exception:
        if temporary_dir.is_dir():
            shutil.rmtree(temporary_dir)
        raise

    remote_run_dir = None
    if profile.transport == "ssh" and profile.ssh is not None:
        remote_run_dir = str(Path(profile.ssh["remote_run_root"]) / run_id)
    store = StateStore(profile.state_db)
    plan_data = _plan_receipt(source, plan)
    store.register_plan(plan_data)
    store.create_run(
        run_id=run_id,
        plan_id=plan.plan_id,
        plan_digest=plan.digest,
        execution_profile_id=profile.profile_id,
        local_run_dir=str(final_dir),
        remote_run_dir=remote_run_dir,
        manifest_digest=manifest_digest,
    )
    return {
        "ok": True,
        "run_id": run_id,
        "plan_id": plan.plan_id,
        "plan_digest": plan.digest,
        "manifest_digest": manifest_digest,
        "execution_profile_id": profile.profile_id,
        "local_run_dir": str(final_dir),
        "remote_run_dir": remote_run_dir,
        "stages": list(CONTROLLED_PERIODIC_STAGES),
        "state": "RUN_PREPARED",
    }
