from __future__ import annotations

from pathlib import Path

from .intake import ingest_case
from .models import CasePlan, GateResult
from .profiles import load_profile
from .provenance import digest_json, execution_input_manifest, source_manifest_digest


class PlanError(ValueError):
    """Raised when a case cannot be assigned a safe initial route."""


ROUTE_STAGES = {
    "molecular_gw": ("scf", "librpa"),
    "periodic_gw": ("scf", "pyatb", "nscf", "preprocess", "librpa"),
    "periodic_gw_symmetry": ("scf", "pyatb", "nscf", "preprocess", "librpa"),
    "rpa": ("scf", "librpa"),
}


def plan_case(
    path: str | Path,
    *,
    task: str,
    system_type: str,
    use_symmetry: bool = False,
    soc: bool = False,
    headwing: bool | None = None,
) -> CasePlan:
    intake = ingest_case(path)
    if intake.stack == "mixed":
        raise PlanError("cannot plan a mixed ABACUS/FHI-aims case")
    if intake.stack != "abacus_librpa":
        raise PlanError(f"Phase 1 supports ABACUS cases, got {intake.stack}")

    normalized_task = task.strip().lower()
    normalized_system = system_type.strip().lower()
    assumptions: list[str] = []
    if normalized_task == "rpa":
        if headwing is True:
            assumptions.append("RPA ignores the caller headwing value and does not use PyATB")
        route = "rpa"
        assumptions.append("RPA correlation route does not require PyATB or NSCF band preprocessing")
    elif normalized_task == "gw":
        if normalized_system in {"molecule", "molecular", "atom"}:
            if use_symmetry:
                raise PlanError("molecular GW does not support the periodic spatial-symmetry lane")
            if headwing is True:
                raise PlanError("molecular GW requires head/wing replacement to be disabled")
            route = "molecular_gw"
            assumptions.append("isolated-system short route without PyATB or band-path NSCF")
        elif normalized_system in {"solid", "periodic", "2d", "two-dimensional"}:
            if headwing is False:
                raise PlanError("periodic GW requires PyATB head/wing replacement in this profile")
            if soc and use_symmetry:
                assumptions.append("SOC disables the current periodic spatial-symmetry lane")
                use_symmetry = False
            if use_symmetry:
                route = "periodic_gw_symmetry"
                assumptions.append("PyATB head/wing data stays on the full regular k-grid")
            else:
                route = "periodic_gw"
                assumptions.append("periodic GW uses full-grid PyATB, NSCF, and preprocessing")
        else:
            raise PlanError(f"unsupported GW system_type: {system_type}")
    else:
        raise PlanError(f"unsupported task: {task}")

    profile = load_profile()
    source_manifest = execution_input_manifest(path)
    source_digest = source_manifest_digest(source_manifest)
    source_path = str(Path(path).expanduser().resolve())
    options = {
        "task": normalized_task,
        "system_type": normalized_system,
        "use_symmetry": use_symmetry,
        "soc": soc,
        "headwing": route in {"periodic_gw", "periodic_gw_symmetry"},
    }
    plan_payload = {
        "schema_version": 1,
        "profile_id": profile["profile_id"],
        "route": route,
        "stages": ROUTE_STAGES[route],
        "options": options,
        "source_digest": source_digest,
    }
    plan_digest = digest_json(plan_payload)
    plan_id = f"plan-{digest_json({'digest': plan_digest, 'source_path': source_path})[:16]}"
    gate = GateResult(
        gate_id="plan.route",
        status="PASS",
        message=f"selected deterministic route {route}",
        evidence=(str(Path(path).expanduser().resolve()),),
        measurements={"stages": len(ROUTE_STAGES[route])},
    )
    return CasePlan(
        plan_id=plan_id,
        digest=plan_digest,
        source_digest=source_digest,
        route=route,
        stages=ROUTE_STAGES[route],
        profile_id=profile["profile_id"],
        options=options,
        source_manifest=source_manifest,
        assumptions=tuple(assumptions),
        gates=(gate,),
    )
