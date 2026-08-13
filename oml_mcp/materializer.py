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
from .parsers import ParseError, parse_abacus_input, parse_bool, parse_int, parse_librpa_input
from .planner import PlanError, plan_case
from .profiles import load_profile
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
            system_type=system_type,
            use_symmetry=use_symmetry,
            soc=False,
            headwing=True,
        )
        for system_type in ("solid", "2d")
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


def _verify_controlled_scope(source: Path, plan: Any) -> None:
    system_type = str(plan.options["system_type"]).strip().lower()
    if system_type in {"2d", "two-dimensional"}:
        raise OMLError(
            "ROUTE_NOT_EXECUTABLE",
            "strict 2D GW is outside the current controlled-execution scope",
            evidence=(system_type,),
            recovery="keep strict 2D on its reviewed workflow until its end-to-end gates are implemented",
        )
    unsafe_paths = []
    for input_name in ("INPUT_scf", "INPUT_nscf"):
        try:
            input_document = parse_abacus_input(source / input_name)
        except ParseError as exc:
            raise OMLError(
                "RUN_PATH_UNSAFE",
                f"cannot inspect ABACUS asset directories: {exc}",
                evidence=(str(source / input_name),),
                recovery=f"repair {input_name} and create a new immutable plan",
            ) from exc
        try:
            nspin = parse_int(input_document.value("nspin", "1"), name="nspin")
            noncolin = parse_bool(input_document.value("noncolin", "false"))
            lspinorb = parse_bool(input_document.value("lspinorb", "false"))
        except ParseError as exc:
            raise OMLError(
                "ROUTE_NOT_EXECUTABLE",
                f"cannot establish the controlled spin scope: {exc}",
                evidence=(str(source / input_name),),
                recovery=f"repair {input_name} and create a new immutable plan",
            ) from exc
        if nspin != 1 or noncolin or lspinorb:
            raise OMLError(
                "ROUTE_NOT_EXECUTABLE",
                "magnetic, noncollinear, and SOC calculations are outside the current controlled-execution scope",
                evidence=(
                    input_name,
                    f"nspin={nspin}",
                    f"noncolin={noncolin}",
                    f"lspinorb={lspinorb}",
                ),
                recovery="keep this calculation on its reviewed magnetic or SOC workflow",
            )
        if input_name == "INPUT_nscf":
            try:
                symmetry = parse_int(
                    input_document.value("symmetry", "0"), name="symmetry"
                )
            except ParseError as exc:
                raise OMLError(
                    "ROUTE_NOT_EXECUTABLE",
                    f"cannot establish the controlled NSCF symmetry scope: {exc}",
                    evidence=(str(source / input_name),),
                    recovery="set INPUT_nscf symmetry = -1 and create a new immutable plan",
                ) from exc
            if symmetry != -1:
                raise OMLError(
                    "ROUTE_NOT_EXECUTABLE",
                    "controlled periodic GW requires a full-grid NSCF calculation with symmetry disabled",
                    evidence=(input_name, f"symmetry={symmetry}"),
                    recovery="set INPUT_nscf symmetry = -1 and create a new immutable plan",
                )
        for key in ("pseudo_dir", "orbital_dir"):
            value = (input_document.value(key, ".") or ".").strip().strip("'\"")
            candidate = Path(value)
            if candidate.is_absolute() or ".." in candidate.parts:
                unsafe_paths.append(f"{input_name} {key}={value}")
    try:
        librpa = parse_librpa_input(source / "librpa.in")
    except ParseError as exc:
        raise OMLError(
            "RUN_PATH_UNSAFE",
            f"cannot establish the LibRPA input directory: {exc}",
            evidence=(str(source / "librpa.in"),),
            recovery="repair librpa.in and create a new immutable plan",
        ) from exc
    input_dir = (librpa.value("input_dir", ".") or ".").strip().strip("'\"")
    candidate = Path(input_dir)
    if input_dir not in {".", "./"}:
        unsafe_paths.append(f"librpa.in input_dir={input_dir}")
    if unsafe_paths:
        raise OMLError(
            "RUN_PATH_UNSAFE",
            "controlled input and asset directories must stay inside the immutable run bundle",
            evidence=tuple(unsafe_paths),
            recovery="copy required inputs into the source bundle and use relative in-bundle directories",
        )
    _verify_stru_assets(source)


def _verify_stru_assets(source: Path) -> None:
    path = source / "STRU"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise OMLError(
            "RUN_PATH_UNSAFE",
            f"cannot inspect STRU asset references: {exc}",
            evidence=(str(path),),
            recovery="repair STRU and create a new immutable plan",
        ) from exc
    failures = []
    for line_number, raw in enumerate(lines, start=1):
        for token in raw.split("#", 1)[0].split():
            value = token.strip("'\"")
            candidate = Path(value)
            if candidate.suffix.lower() not in {".upf", ".orb", ".abfs"}:
                continue
            if candidate.is_absolute() or ".." in candidate.parts:
                failures.append(f"STRU:{line_number}: unsafe asset path {value}")
                continue
            asset = source / candidate
            if asset.is_symlink() or not asset.is_file():
                failures.append(f"STRU:{line_number}: missing or linked asset {value}")
    if failures:
        raise OMLError(
            "RUN_PATH_UNSAFE",
            "STRU asset references must resolve to regular files inside the immutable source bundle",
            evidence=tuple(failures),
            recovery="copy the referenced PP, NAO, and ABFS files into the source bundle and update STRU",
        )


def _verify_workflow_helpers(source: Path) -> None:
    approved = load_profile()["contract"]["workflow_helpers"]
    failures = []
    for name, expected in approved.items():
        path = source / name
        if path.is_symlink() or not path.is_file():
            failures.append(f"{name}: missing or linked")
        else:
            actual = sha256_file(path)
            if actual != expected:
                failures.append(f"{name}: sha256={actual}, expected={expected}")
    if failures:
        raise OMLError(
            "HELPER_MISMATCH",
            "periodic GW helper scripts do not match the approved OML bundle",
            evidence=tuple(failures),
            recovery="restore the helper quartet from the pinned OML template and create a new plan",
        )


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
            Path(".oml/plan.json"),
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
    except PlanError as exc:
        raise OMLError(
            "STALE_PLAN",
            f"current source can no longer reproduce the approved plan: {exc}",
            evidence=(str(source), plan_digest),
            recovery="review the source classification and create a new immutable plan",
        ) from exc
    except ProvenanceError as exc:
        raise OMLError(
            "SOURCE_UNSAFE",
            str(exc),
            evidence=(str(source),),
            recovery="replace escaped links with regular immutable source files",
        ) from exc
    if plan.route == "strict_2d_gw_deferred":
        capability = plan.options["capability"]
        raise OMLError(
            "CAPABILITY_BLOCKED",
            "strict 2D GW is blocked for the pinned LibRPA 0.7.0 profile",
            evidence=(
                plan.profile_id,
                capability["reason_code"],
                capability["component_revision"],
            ),
            recovery="pin a corrected LibRPA profile and add the required strict-2D gates before execution",
        )
    if plan.route not in {"periodic_gw", "periodic_gw_symmetry"} or plan.options["soc"]:
        raise OMLError(
            "ROUTE_NOT_EXECUTABLE",
            "Phase 2 controlled execution supports only non-SOC periodic GW routes",
            evidence=(plan.route,),
            recovery="keep this route on the existing workflow until a dedicated executor is approved",
        )
    _verify_controlled_scope(source, plan)
    _verify_workflow_helpers(source)
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
            render_env(
                profile.runtime,
                environment=profile.environment,
                run_id=run_id,
                plan_digest=plan.digest,
            ),
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
    try:
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
    except Exception:
        if final_dir.is_dir():
            shutil.rmtree(final_dir)
        raise
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
