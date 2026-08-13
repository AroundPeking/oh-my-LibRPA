from __future__ import annotations

import math
from typing import Any

from .scientific_definition import compare_definitions


QUANTITIES = ("ks", "exx", "gw")


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
        }

    return {
        "status": "PASS" if accepted else "FAIL",
        "reason_code": "WITHIN_TOLERANCE" if accepted else "REGRESSION_TOLERANCE_EXCEEDED",
        "tolerance_ev": tolerance_ev,
        "state_count": len(candidate_states),
        "quantities": quantities,
    }
