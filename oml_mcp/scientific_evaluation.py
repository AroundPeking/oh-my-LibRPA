from __future__ import annotations

import math
from typing import Any

from .scientific_definition import ScientificDefinitionError, compare_definitions


QUANTITIES = ("ks", "exx", "gw")
KS_DEGENERACY_TOLERANCE_EV = 1e-5
OCCUPATION_TOLERANCE = 1e-8
NUMERICAL_EPSILON_EV = 1e-12


class ScientificEvaluationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


def _state_key(state: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(state["spin"]),
        *(round(float(value), 8) for value in state["kpoint"]),
        int(state["band"]),
    )


def _state_map(result: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, Any]]:
    states = result.get("window", {}).get("states", [])
    return {_state_key(state): state for state in states}


def _failed_diagnostics(result: dict[str, Any]) -> bool:
    diagnostics = result.get("diagnostics", {})
    return diagnostics.get("accepted") is False or int(diagnostics.get("failure_count", 0)) > 0


def _diagnostic_reason(result: dict[str, Any]) -> str:
    failures = result.get("diagnostics", {}).get("failures", [])
    if failures and isinstance(failures[0], dict) and failures[0].get("reason_code"):
        return str(failures[0]["reason_code"])
    return "QPE_DIAGNOSTIC_FAILURE"


def _identity(key: tuple[Any, ...]) -> dict[str, Any]:
    return {"spin": key[0], "kpoint": list(key[1:4]), "band": key[4]}


def _degenerate_partition(
    states: dict[tuple[Any, ...], dict[str, Any]],
    *,
    tolerance_ev: float,
) -> dict[tuple[Any, ...], tuple[tuple[Any, ...], ...]]:
    buckets: dict[tuple[Any, ...], list[tuple[float, tuple[Any, ...]]]] = {}
    for key, state in states.items():
        bucket = (*key[:4], round(float(state["occupation"]), 8))
        buckets.setdefault(bucket, []).append((float(state["ks_ev"]), key))

    partition: dict[tuple[Any, ...], tuple[tuple[Any, ...], ...]] = {}
    for bucket_states in buckets.values():
        ordered = sorted(bucket_states, key=lambda item: (item[0], item[1]))
        groups: list[list[tuple[float, tuple[Any, ...]]]] = []
        for energy, key in ordered:
            if (
                not groups
                or energy - groups[-1][0][0]
                > tolerance_ev + NUMERICAL_EPSILON_EV
            ):
                groups.append([])
            groups[-1].append((energy, key))
        for group in groups:
            identity = tuple(sorted(key for _, key in group))
            for _, key in group:
                partition[key] = identity
    return partition


def _degenerate_gauge_diagnostic(
    candidate_states: dict[tuple[Any, ...], dict[str, Any]],
    reference_states: dict[tuple[Any, ...], dict[str, Any]],
    quantities: dict[str, Any],
    *,
    regression_tolerance_ev: float,
    degeneracy_tolerance_ev: float,
) -> dict[str, Any] | None:
    if not quantities["ks"]["accepted"]:
        return None
    if any(
        abs(
            float(candidate_states[key]["occupation"])
            - float(reference_states[key]["occupation"])
        )
        > OCCUPATION_TOLERANCE
        for key in candidate_states
    ):
        return None

    candidate_partition = _degenerate_partition(
        candidate_states, tolerance_ev=degeneracy_tolerance_ev
    )
    reference_partition = _degenerate_partition(
        reference_states, tolerance_ev=degeneracy_tolerance_ev
    )
    if candidate_partition != reference_partition:
        return None

    affected: dict[tuple[tuple[Any, ...], ...], set[str]] = {}
    affected_states: set[tuple[Any, ...]] = set()
    for quantity in ("exx", "gw"):
        for key in sorted(candidate_states):
            error = abs(
                float(candidate_states[key][f"{quantity}_ev"])
                - float(reference_states[key][f"{quantity}_ev"])
            )
            if error <= regression_tolerance_ev + NUMERICAL_EPSILON_EV:
                continue
            group = candidate_partition[key]
            if len(group) < 2:
                return None
            affected.setdefault(group, set()).add(quantity)
            affected_states.add(key)
    if not affected:
        return None

    affected_groups = []
    for group in sorted(affected):
        group_quantities: dict[str, Any] = {}
        for quantity in sorted(affected[group]):
            candidate_values = [
                float(candidate_states[key][f"{quantity}_ev"]) for key in group
            ]
            reference_values = [
                float(reference_states[key][f"{quantity}_ev"]) for key in group
            ]
            candidate_mean = sum(candidate_values) / len(candidate_values)
            reference_mean = sum(reference_values) / len(reference_values)
            mean_error = abs(candidate_mean - reference_mean)
            if mean_error > regression_tolerance_ev + NUMERICAL_EPSILON_EV:
                return None
            group_quantities[quantity] = {
                "max_abs_statewise_error_ev": max(
                    abs(candidate - reference)
                    for candidate, reference in zip(
                        candidate_values, reference_values, strict=True
                    )
                ),
                "candidate_mean_ev": candidate_mean,
                "reference_mean_ev": reference_mean,
                "mean_abs_error_ev": mean_error,
            }

        first = group[0]
        candidate_ks = [float(candidate_states[key]["ks_ev"]) for key in group]
        reference_ks = [float(reference_states[key]["ks_ev"]) for key in group]
        affected_groups.append(
            {
                "spin": first[0],
                "kpoint": list(first[1:4]),
                "bands": [key[4] for key in group],
                "state_count": len(group),
                "candidate_ks_spread_ev": max(candidate_ks) - min(candidate_ks),
                "reference_ks_spread_ev": max(reference_ks) - min(reference_ks),
                "quantities": group_quantities,
            }
        )

    return {
        "classification": "CONSISTENT_WITH_GAUGE_ROTATION",
        "ks_degeneracy_tolerance_ev": degeneracy_tolerance_ev,
        "group_mean_tolerance_ev": regression_tolerance_ev,
        "affected_group_count": len(affected_groups),
        "affected_state_count": len(affected_states),
        "affected_groups": affected_groups,
        "subspace_verification_required": True,
        "gauge_invariant_acceptance": False,
    }


def evaluate_regression(
    candidate: dict[str, Any],
    reference: dict[str, Any] | None,
    *,
    tolerance_ev: float,
) -> dict[str, Any]:
    if _failed_diagnostics(candidate):
        return {
            "status": "FAIL",
            "reason_code": _diagnostic_reason(candidate),
            "tolerance_ev": tolerance_ev,
            "candidate_diagnostics": candidate.get("diagnostics"),
        }
    if reference is None:
        return {
            "status": "NOT_EVALUATED",
            "reason_code": "REFERENCE_NOT_AVAILABLE",
            "tolerance_ev": tolerance_ev,
        }
    differences = compare_definitions(candidate["definition"], reference["definition"])
    if differences:
        return {
            "status": "NOT_EVALUATED",
            "reason_code": "DEFINITION_MISMATCH",
            "tolerance_ev": tolerance_ev,
            "definition_differences": differences,
        }
    if _failed_diagnostics(reference):
        return {
            "status": "FAIL",
            "reason_code": _diagnostic_reason(reference),
            "tolerance_ev": tolerance_ev,
            "candidate_diagnostics": candidate.get("diagnostics"),
            "reference_diagnostics": reference.get("diagnostics"),
        }

    candidate_states = _state_map(candidate)
    reference_states = _state_map(reference)
    if set(candidate_states) != set(reference_states):
        missing = sorted(set(reference_states) - set(candidate_states))
        extra = sorted(set(candidate_states) - set(reference_states))
        return {
            "status": "FAIL",
            "reason_code": "STATE_SET_MISMATCH",
            "tolerance_ev": tolerance_ev,
            "missing_states": [_identity(key) for key in missing],
            "extra_states": [_identity(key) for key in extra],
        }

    quantities: dict[str, Any] = {}
    accepted = True
    for quantity in QUANTITIES:
        errors = []
        for key in sorted(candidate_states):
            error = abs(
                float(candidate_states[key][f"{quantity}_ev"])
                - float(reference_states[key][f"{quantity}_ev"])
            )
            errors.append((error, key))
        worst_error, worst_key = max(errors)
        rms_error = math.sqrt(sum(error * error for error, _ in errors) / len(errors))
        quantity_accepted = worst_error <= tolerance_ev + NUMERICAL_EPSILON_EV
        accepted = accepted and quantity_accepted
        quantities[quantity] = {
            "accepted": quantity_accepted,
            "max_abs_error_ev": worst_error,
            "rms_error_ev": rms_error,
            "worst_state": _identity(worst_key),
            "candidate_ev": float(candidate_states[worst_key][f"{quantity}_ev"]),
            "reference_ev": float(reference_states[worst_key][f"{quantity}_ev"]),
        }

    report = {
        "status": "PASS" if accepted else "FAIL",
        "reason_code": "WITHIN_TOLERANCE" if accepted else "REGRESSION_TOLERANCE_EXCEEDED",
        "tolerance_ev": tolerance_ev,
        "state_count": len(candidate_states),
        "quantities": quantities,
    }
    if not accepted:
        degenerate_gauge = _degenerate_gauge_diagnostic(
            candidate_states,
            reference_states,
            quantities,
            regression_tolerance_ev=tolerance_ev,
            degeneracy_tolerance_ev=KS_DEGENERACY_TOLERANCE_EV,
        )
        if degenerate_gauge is not None:
            report["reason_code"] = "BLOCKED_DEGENERATE_GAUGE_MISMATCH"
            report["degenerate_gauge"] = degenerate_gauge
    return report


def evaluate_convergence_axis(
    coarse: dict[str, Any],
    fine: dict[str, Any],
    *,
    axis: str,
    tolerance_ev: float,
) -> dict[str, Any]:
    try:
        compare_definitions(
            coarse["definition"],
            fine["definition"],
            allowed_axis=axis,
        )
    except ScientificDefinitionError as exc:
        raise ScientificEvaluationError(
            exc.code,
            exc.message,
            details={"fields": list(exc.fields), **exc.details},
        ) from exc

    if _failed_diagnostics(coarse) or _failed_diagnostics(fine):
        return {
            "axis": axis,
            "status": "FAIL",
            "reason_code": "QPE_DIAGNOSTIC_FAILURE",
            "tolerance_ev": tolerance_ev,
            "coarse_diagnostics": coarse.get("diagnostics"),
            "fine_diagnostics": fine.get("diagnostics"),
        }

    coarse_states = _state_map(coarse)
    fine_states = _state_map(fine)
    if set(coarse_states) != set(fine_states):
        missing = sorted(set(coarse_states) - set(fine_states))
        extra = sorted(set(fine_states) - set(coarse_states))
        return {
            "axis": axis,
            "status": "FAIL",
            "reason_code": "STATE_SET_MISMATCH",
            "tolerance_ev": tolerance_ev,
            "missing_states": [_identity(key) for key in missing],
            "extra_states": [_identity(key) for key in extra],
        }

    quantities: dict[str, Any] = {}
    for quantity in QUANTITIES:
        changes = []
        for key in sorted(coarse_states):
            change = abs(
                float(fine_states[key][f"{quantity}_ev"])
                - float(coarse_states[key][f"{quantity}_ev"])
            )
            changes.append((change, key))
        worst_change, worst_key = max(changes)
        quantities[quantity] = {
            "max_abs_change_ev": round(worst_change, 12),
            "rms_change_ev": round(
                math.sqrt(sum(change * change for change, _ in changes) / len(changes)),
                12,
            ),
            "worst_state": _identity(worst_key),
        }

    gw_change = float(quantities["gw"]["max_abs_change_ev"])
    gap_change = abs(
        float(fine["window"]["fundamental_gw_gap_ev"])
        - float(coarse["window"]["fundamental_gw_gap_ev"])
    )
    complete_basis_state_space = False
    if axis == "empty_states":
        coarse_space = coarse.get("state_space", {})
        fine_space = fine.get("state_space", {})
        if isinstance(coarse_space, dict) and isinstance(fine_space, dict):
            coarse_nbands = int(coarse_space.get("nbands", 0))
            fine_nbands = int(fine_space.get("nbands", 0))
            coarse_basis = int(coarse_space.get("basis_dimension", 0))
            fine_basis = int(fine_space.get("basis_dimension", 0))
            complete_basis_state_space = (
                coarse_basis > 0
                and coarse_basis == fine_basis
                and coarse_nbands < fine_nbands
                and fine_nbands == fine_basis
                and fine_space.get("complete") is True
            )
    accepted = complete_basis_state_space or (
        gw_change <= tolerance_ev + 1e-12 and gap_change <= tolerance_ev + 1e-12
    )
    report = {
        "axis": axis,
        "status": "PASS" if accepted else "FAIL",
        "reason_code": (
            "COMPLETE_BASIS_STATE_SPACE"
            if complete_basis_state_space
            else "WITHIN_TOLERANCE"
            if accepted
            else "CONVERGENCE_TOLERANCE_EXCEEDED"
        ),
        "tolerance_ev": tolerance_ev,
        "state_count": len(coarse_states),
        "max_abs_gw_change_ev": gw_change,
        "gap_change_ev": round(gap_change, 12),
        "quantities": quantities,
    }
    if axis == "empty_states":
        report.update(
            {
                "complete_basis_state_space": complete_basis_state_space,
                "coarse_state_space": coarse.get("state_space"),
                "fine_state_space": fine.get("state_space"),
            }
        )
    return report


def aggregate_convergence(
    reports: dict[str, dict[str, Any]],
    *,
    required_axes: tuple[str, ...],
) -> dict[str, Any]:
    missing = [axis for axis in required_axes if axis not in reports]
    if missing:
        return {
            "status": "NOT_EVALUATED",
            "reason_code": "CONVERGENCE_AXES_MISSING",
            "required_axes": list(required_axes),
            "missing_axes": missing,
            "axes": {axis: reports[axis] for axis in required_axes if axis in reports},
        }
    invalid = [
        axis
        for axis in required_axes
        if reports[axis].get("axis") != axis
        or reports[axis].get("status") not in {"PASS", "FAIL"}
    ]
    if invalid:
        return {
            "status": "NOT_EVALUATED",
            "reason_code": "CONVERGENCE_AXES_INVALID",
            "required_axes": list(required_axes),
            "invalid_axes": invalid,
            "axes": {axis: reports[axis] for axis in required_axes},
        }
    failed = [axis for axis in required_axes if reports[axis]["status"] == "FAIL"]
    return {
        "status": "FAIL" if failed else "PASS",
        "reason_code": "CONVERGENCE_FAILED" if failed else "CONVERGENCE_PASSED",
        "required_axes": list(required_axes),
        "failed_axes": failed,
        "axes": {axis: reports[axis] for axis in required_axes},
    }
