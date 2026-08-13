from __future__ import annotations

import math
from typing import Any

from .scientific_definition import ScientificDefinitionError, compare_definitions


QUANTITIES = ("ks", "exx", "gw")


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


def _identity(key: tuple[Any, ...]) -> dict[str, Any]:
    return {"spin": key[0], "kpoint": list(key[1:4]), "band": key[4]}


def evaluate_regression(
    candidate: dict[str, Any],
    reference: dict[str, Any] | None,
    *,
    tolerance_ev: float,
) -> dict[str, Any]:
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
    if _failed_diagnostics(candidate) or _failed_diagnostics(reference):
        return {
            "status": "FAIL",
            "reason_code": "QPE_DIAGNOSTIC_FAILURE",
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
        quantity_accepted = worst_error <= tolerance_ev + 1e-12
        accepted = accepted and quantity_accepted
        quantities[quantity] = {
            "accepted": quantity_accepted,
            "max_abs_error_ev": worst_error,
            "rms_error_ev": rms_error,
            "worst_state": _identity(worst_key),
            "candidate_ev": float(candidate_states[worst_key][f"{quantity}_ev"]),
            "reference_ev": float(reference_states[worst_key][f"{quantity}_ev"]),
        }

    return {
        "status": "PASS" if accepted else "FAIL",
        "reason_code": "WITHIN_TOLERANCE" if accepted else "REGRESSION_TOLERANCE_EXCEEDED",
        "tolerance_ev": tolerance_ev,
        "state_count": len(candidate_states),
        "quantities": quantities,
    }


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
    accepted = gw_change <= tolerance_ev + 1e-12 and gap_change <= tolerance_ev + 1e-12
    return {
        "axis": axis,
        "status": "PASS" if accepted else "FAIL",
        "reason_code": "WITHIN_TOLERANCE" if accepted else "CONVERGENCE_TOLERANCE_EXCEEDED",
        "tolerance_ev": tolerance_ev,
        "state_count": len(coarse_states),
        "max_abs_gw_change_ev": gw_change,
        "gap_change_ev": round(gap_change, 12),
        "quantities": quantities,
    }


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
