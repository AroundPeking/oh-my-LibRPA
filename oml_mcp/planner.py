from __future__ import annotations

from pathlib import Path
from typing import Any

from .intake import ingest_case
from .models import CasePlan, GateResult
from .profiles import STRICT_2D_SOS_RPA_PROFILE_ID, load_profile
from .provenance import digest_json, execution_input_manifest, source_manifest_digest


class PlanError(ValueError):
    """Raised when a case cannot be assigned a safe initial route."""


ROUTE_STAGES = {
    "molecular_gw": ("scf", "librpa"),
    "periodic_gw": ("scf", "pyatb", "nscf", "preprocess", "librpa"),
    "periodic_gw_symmetry": ("scf", "pyatb", "nscf", "preprocess", "librpa"),
    "periodic_gw_no_headwing": ("scf", "nscf", "preprocess", "librpa"),
    "periodic_gw_symmetry_no_headwing": ("scf", "nscf", "preprocess", "librpa"),
    "strict_2d_gw_deferred": (),
    "strict_2d_gw": ("scf", "pyatb", "nscf", "preprocess", "librpa"),
    "rpa": ("scf", "librpa"),
    "molecular_delta_st_rpa": ("ground_state", "sternheimer", "librpa"),
    "solid_delta_st_rpa": ("ground_state", "sternheimer", "librpa"),
    "strict_2d_sos_rpa": ("librpa",),
}


def _capability_id(route: str) -> str | None:
    if route in {
        "periodic_gw",
        "periodic_gw_symmetry",
        "periodic_gw_no_headwing",
        "periodic_gw_symmetry_no_headwing",
    }:
        return "periodic_3d_gw"
    if route == "strict_2d_gw":
        return "strict_2d_gw"
    if route == "molecular_delta_st_rpa":
        return "molecular_delta_st_rpa"
    if route == "solid_delta_st_rpa":
        return "solid_delta_st_rpa"
    if route == "strict_2d_sos_rpa":
        return "strict_2d_sos_rpa"
    return None


def _plan_rpa_route(
    *,
    normalized_system: str,
    response_method: str,
    is_v2: bool,
    profile_id: str,
    headwing: bool | None,
    assumptions: list[str],
) -> str:
    strict_2d_sos_rpa = profile_id == STRICT_2D_SOS_RPA_PROFILE_ID
    if strict_2d_sos_rpa:
        if normalized_system not in {"2d", "two-dimensional"}:
            raise PlanError("strict-2D SOS-RPA requires system_type=2d")
        if response_method != "sos":
            raise PlanError("strict-2D SOS-RPA requires the SOS response method")
        if headwing is False:
            raise PlanError("strict-2D SOS-RPA requires analytic head/wing q averaging")
        assumptions.extend(
            (
                "reuse the validated reader-v1 ABACUS and PyATB producer without rerunning either producer",
                "use full 2D Ewald Coulomb with analytic Gamma head/wing q averaging",
                (
                    "the N=8, N=10, N=12, and N=16 mesh series validates function "
                    "and numerics only; a stable asymptotic regime is still required "
                    "for a convergence claim"
                ),
            )
        )
        return "strict_2d_sos_rpa"
    if response_method == "sternheimer":
        if not is_v2:
            raise PlanError("Delta-Sternheimer RPA requires the v2 compatibility profile")
        if normalized_system in {"molecule", "molecular", "atom"}:
            route = "molecular_delta_st_rpa"
        elif normalized_system in {"solid", "periodic"}:
            route = "solid_delta_st_rpa"
        else:
            raise PlanError(
                f"unsupported Delta-Sternheimer RPA system_type: {normalized_system}"
            )
        assumptions.append("Delta-Sternheimer response is an explicit producer stage")
        return route
    if response_method != "sos":
        raise PlanError(f"unsupported RPA response_method: {response_method}")
    if is_v2:
        raise PlanError("the v2 profile currently registers only Delta-Sternheimer RPA routes")
    if headwing is True:
        assumptions.append("RPA ignores the caller headwing value and does not use PyATB")
    assumptions.append("RPA correlation route does not require PyATB or NSCF band preprocessing")
    return "rpa"


def _plan_gw_route(
    *,
    normalized_system: str,
    use_symmetry: bool,
    soc: bool,
    headwing: bool | None,
    is_v2: bool,
    assumptions: list[str],
) -> tuple[str, bool]:
    if normalized_system in {"molecule", "molecular", "atom"}:
        if is_v2:
            raise PlanError("the v2 profile does not register a molecular GW admission route")
        if use_symmetry:
            raise PlanError("molecular GW does not support the periodic spatial-symmetry lane")
        if headwing is True:
            raise PlanError("molecular GW requires head/wing replacement to be disabled")
        assumptions.append("isolated-system short route without PyATB or band-path NSCF")
        return "molecular_gw", use_symmetry
    if normalized_system in {"2d", "two-dimensional"}:
        if headwing is False:
            raise PlanError("strict 2D GW requires head/wing replacement")
        if is_v2:
            assumptions.append("strict 2D uses full-Ewald Coulomb and analytic Gamma head/wing")
            return "strict_2d_gw", use_symmetry
        assumptions.append(
            "strict 2D remains blocked until a corrected LibRPA profile and 2D gates are installed"
        )
        return "strict_2d_gw_deferred", use_symmetry
    if normalized_system not in {"solid", "periodic"}:
        raise PlanError(f"unsupported GW system_type: {normalized_system}")
    if soc and use_symmetry:
        assumptions.append("SOC disables the current periodic spatial-symmetry lane")
        use_symmetry = False
    if headwing is False and use_symmetry:
        route = "periodic_gw_symmetry_no_headwing"
        assumptions.append("explicit diagnostic route disables PyATB head/wing replacement")
    elif headwing is False:
        route = "periodic_gw_no_headwing"
        assumptions.append("explicit diagnostic route disables PyATB head/wing replacement")
    elif use_symmetry:
        route = "periodic_gw_symmetry"
        assumptions.append("PyATB head/wing data stays on the full regular k-grid")
    else:
        route = "periodic_gw"
        assumptions.append("periodic GW uses full-grid PyATB, NSCF, and preprocessing")
    return route, use_symmetry


def _plan_gate(
    *,
    route: str,
    profile: dict[str, Any],
    source_path: str,
    capability: dict[str, Any] | None,
) -> GateResult:
    if route == "strict_2d_gw_deferred":
        blocked = profile["capabilities"]["strict_2d_gw"]
        return GateResult(
            gate_id="plan.route",
            status="WARN",
            message="strict 2D GW is discoverable but blocked for the pinned LibRPA profile",
            evidence=(blocked["reason_code"], blocked["component_revision"]),
            repair="pin a corrected LibRPA revision and implement the declared strict-2D gates",
            measurements={"stages": 0},
        )
    if capability is not None and capability["status"] == "TESTABLE":
        return GateResult(
            gate_id="plan.route",
            status="WARN",
            message=f"selected testable admission route {route}",
            evidence=(profile["profile_id"], capability["status"]),
            repair="execute only through the registered admission harness until L3 is reviewed",
            measurements={
                "stages": len(ROUTE_STAGES[route]),
                "admission_level": capability["admission_level"],
            },
        )
    return GateResult(
        gate_id="plan.route",
        status="PASS",
        message=f"selected deterministic route {route}",
        evidence=(source_path,),
        measurements={"stages": len(ROUTE_STAGES[route])},
    )


def plan_case(
    path: str | Path,
    *,
    task: str,
    system_type: str,
    use_symmetry: bool = False,
    soc: bool = False,
    headwing: bool | None = None,
    profile_id: str | None = None,
    response_method: str = "sos",
) -> CasePlan:
    intake = ingest_case(path)
    if intake.stack == "mixed":
        raise PlanError("cannot plan a mixed ABACUS/FHI-aims case")
    if intake.stack != "abacus_librpa":
        raise PlanError(f"Phase 1 supports ABACUS cases, got {intake.stack}")

    profile = load_profile(profile_id=profile_id) if profile_id is not None else load_profile()
    is_v2 = profile["schema_version"] == 2
    normalized_task = task.strip().lower()
    normalized_system = system_type.strip().lower()
    normalized_response = response_method.strip().lower()
    assumptions: list[str] = []
    if (
        profile["profile_id"] == STRICT_2D_SOS_RPA_PROFILE_ID
        and normalized_task != "rpa"
    ):
        raise PlanError("the selected profile only admits strict-2D SOS-RPA")
    if normalized_task == "rpa":
        route = _plan_rpa_route(
            normalized_system=normalized_system,
            response_method=normalized_response,
            is_v2=is_v2,
            profile_id=profile["profile_id"],
            headwing=headwing,
            assumptions=assumptions,
        )
    elif normalized_task == "gw":
        route, use_symmetry = _plan_gw_route(
            normalized_system=normalized_system,
            use_symmetry=use_symmetry,
            soc=soc,
            headwing=headwing,
            is_v2=is_v2,
            assumptions=assumptions,
        )
    else:
        raise PlanError(f"unsupported task: {task}")

    source_manifest = execution_input_manifest(path)
    source_digest = source_manifest_digest(source_manifest)
    source_path = str(Path(path).expanduser().resolve())
    options: dict[str, Any] = {
        "task": normalized_task,
        "system_type": normalized_system,
        "use_symmetry": use_symmetry,
        "soc": soc,
        "headwing": route
        in {"periodic_gw", "periodic_gw_symmetry", "strict_2d_gw"},
    }
    capability: dict[str, Any] | None = None
    if route == "strict_2d_gw_deferred":
        options["headwing"] = True
        options["capability"] = profile["capabilities"]["strict_2d_gw"]
    if is_v2:
        capability_id = _capability_id(route)
        if capability_id is None:
            raise PlanError(f"route is not registered by the v2 profile: {route}")
        capability = profile["capabilities"][capability_id]
        options.update(
            {
                "response_method": normalized_response,
                "reader_format": "v1",
                "capability_id": capability_id,
                "capability": capability,
            }
        )
        if route == "strict_2d_sos_rpa":
            route_contract = profile["contract"]["strict_2d_sos_rpa"]
            options.update(
                {
                    "nfreq": route_contract["nfreq"],
                    "headwing": route_contract["headwing"],
                    "head_only": route_contract["head_only"],
                    "coulomb": route_contract["coulomb"],
                    "allow_abacus_rerun": route_contract["allow_abacus_rerun"],
                    "allow_pyatb_rerun": route_contract["allow_pyatb_rerun"],
                    "execution": profile["admission"]["df_dcu_limits"],
                }
            )

    plan_payload = {
        "schema_version": 2 if is_v2 else 1,
        "profile_id": profile["profile_id"],
        "route": route,
        "stages": ROUTE_STAGES[route],
        "options": options,
        "source_digest": source_digest,
    }
    plan_digest = digest_json(plan_payload)
    plan_id = f"plan-{digest_json({'digest': plan_digest, 'source_path': source_path})[:16]}"
    gate = _plan_gate(
        route=route,
        profile=profile,
        source_path=source_path,
        capability=capability,
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
