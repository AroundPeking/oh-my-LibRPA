from __future__ import annotations

import math
from typing import Any

from .material_class import (
    MaterialClassError,
    load_material_class,
    validate_material_class,
)
from .scientific_bands import (
    ScientificBandError,
    select_spin_resolved_window,
)
from .scientific_evaluation import (
    ScientificEvaluationError,
    evaluate_regression,
)


class MaterialClassEvaluationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


def _gate(
    gate_id: str,
    passed: bool,
    *,
    measured: Any,
    threshold: Any,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "status": "PASS" if passed else "FAIL",
        "measured": measured,
        "threshold": threshold,
        "evidence": evidence or [],
    }


def _asset_group(value: Any, label: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MaterialClassEvaluationError(f"{label} must be an object")
    return {str(name): str(digest) for name, digest in value.items()}


def _asset_subset_matches(
    run_group: dict[str, str],
    identity_group: dict[str, str],
) -> tuple[bool, dict[str, Any]]:
    """Every frozen identity asset must be present in the run with the same hash.

    The run may carry additional assets (e.g. a generated ABFS not yet frozen);
    those are not required to match. Returns (ok, report).
    """
    missing = [name for name in identity_group if name not in run_group]
    mismatched = [
        {"asset": name, "expected": identity_group[name], "actual": run_group[name]}
        for name in identity_group
        if name in run_group and run_group[name] != identity_group[name]
    ]
    return (not missing and not mismatched), {
        "identity_asset_count": len(identity_group),
        "run_asset_count": len(run_group),
        "missing_assets": missing,
        "mismatched_assets": mismatched,
    }


def _window_for_run(
    run: dict[str, Any],
    *,
    default_occupied_value: float,
) -> dict[str, Any]:
    window = run.get("window")
    if not isinstance(window, dict):
        raise MaterialClassEvaluationError("run.window must be an object")
    # Re-validate the occupation pattern from the raw states so a submitted
    # window cannot be gamed: the spin-resolved selector is the only authority.
    states = window.get("states")
    if not isinstance(states, list) or not states:
        raise MaterialClassEvaluationError("run.window.states must be a non-empty list")
    return select_spin_resolved_window(
        {
            "spins": window.get("spins", [1]),
            "nbands": int(window.get("nbands", 0)),
            "states": states,
        },
        occupied_value=float(run.get("occupied_value", default_occupied_value)),
        padding=int(run.get("padding", 3)),
    )


def evaluate_material_class(
    material_class_id: str,
    run: dict[str, Any],
    *,
    tolerance_ev: float = 1e-3,
) -> dict[str, Any]:
    """Validate a produced GW run against a frozen material-class identity.

    Gates (non-compensating):
      - identity.assets   : run PP/NAO/ABFS hashes match the frozen identity.
      - identity.software : run software identity matches when a reference is frozen.
      - contract.spin     : run nspin/SOC matches the identity magnetic order.
      - window.valid      : the spin-resolved state window is insulating and finite.
      - reference.status  : regression vs the frozen reference, or REFERENCE_PENDING.
    """
    try:
        identity = load_material_class(material_class_id, hydrate_reference=True)
        validate_material_class(identity)
    except MaterialClassError as exc:
        raise MaterialClassEvaluationError(
            "MATERIAL_CLASS_IDENTITY_INVALID", str(exc)
        ) from exc

    gates: list[dict[str, Any]] = []
    material = identity["material"]
    run_assets = run.get("assets", {})
    if not isinstance(run_assets, dict):
        raise MaterialClassEvaluationError("run.assets must be an object")
    run_pp = _asset_group(run_assets.get("pseudopotentials"), "run.assets.pseudopotentials")
    run_orb = _asset_group(run_assets.get("orbitals"), "run.assets.orbitals")
    run_abfs = _asset_group(run_assets.get("auxiliary_bases"), "run.assets.auxiliary_bases")

    identity_pp = _asset_group(material.get("pseudopotentials"), "identity.pseudopotentials")
    identity_orb = _asset_group(material.get("orbitals"), "identity.orbitals")
    identity_abfs = _asset_group(material.get("auxiliary_bases"), "identity.auxiliary_bases")

    asset_report: dict[str, Any] = {}
    for group_label, run_group, identity_group in (
        ("pseudopotentials", run_pp, identity_pp),
        ("orbitals", run_orb, identity_orb),
        ("auxiliary_bases", run_abfs, identity_abfs),
    ):
        ok, report = _asset_subset_matches(run_group, identity_group)
        asset_report[group_label] = report
        gates.append(
            _gate(
                f"identity.assets.{group_label}",
                ok,
                measured=report,
                threshold="run must carry every frozen identity asset with a matching hash",
            )
        )
    # At least one frozen asset group must be present so a pending identity is not
    # trivially satisfied by an empty run.
    has_any_asset = bool(identity_pp or identity_orb or identity_abfs)
    gates.append(
        _gate(
            "identity.assets.present",
            has_any_asset and any(
                asset_report[group]["identity_asset_count"] > 0
                for group in asset_report
            ),
            measured={
                group: asset_report[group]["identity_asset_count"] for group in asset_report
            },
            threshold="the identity must freeze at least one asset group",
        )
    )

    # Software identity is only fully frozen once a reference exists.
    identity_software = identity.get("software_identity", {})
    reference_status = identity.get("reference_status")
    run_software = run.get("software", {})
    if reference_status == "REFERENCE_AVAILABLE":
        expected_revisions = {
            key: identity_software.get(key)
            for key in ("abacus_revision", "librpa_revision", "pyatb_revision")
        }
        run_revisions = run_software.get("revisions", {}) if isinstance(run_software, dict) else {}
        revision_ok = all(
            expected is None or run_revisions.get(key) == expected
            for key, expected in expected_revisions.items()
        )
        expected_hashes = {
            key: identity_software.get(key)
            for key in ("abacus_executable_sha256", "librpa_executable_sha256")
        }
        run_hashes = run_software.get("executables", {}) if isinstance(run_software, dict) else {}
        hash_ok = all(
            expected is None or run_hashes.get(key) == expected
            for key, expected in expected_hashes.items()
        )
        gates.append(
            _gate(
                "identity.software",
                revision_ok and hash_ok,
                measured={
                    "revisions": run_revisions,
                    "executables": run_hashes,
                },
                threshold={
                    "revisions": expected_revisions,
                    "executables": expected_hashes,
                },
            )
        )
    else:
        gates.append(
            _gate(
                "identity.software",
                True,
                measured="pending identity has no frozen software requirement",
                threshold="software identity is frozen only when a reference is available",
                evidence=["REFERENCE_PENDING entries pin software identity with the reference run"],
            )
        )

    # Spin / SOC contract.
    identity_order = material.get("magnetic_order", {})
    identity_nspin = int(identity_order.get("nspin", 1))
    identity_soc = identity_order.get("type") == "soc"
    run_nspin = int(run.get("nspin", 1))
    run_soc = bool(run.get("soc", False))
    spin_ok = run_nspin == identity_nspin and run_soc == identity_soc
    gates.append(
        _gate(
            "contract.spin",
            spin_ok,
            measured={"nspin": run_nspin, "soc": run_soc},
            threshold={
                "nspin": identity_nspin,
                "soc": identity_soc,
                "magnetic_order_type": identity_order.get("type"),
            },
        )
    )

    # Spin-resolved window validity. The default occupation value is derived from
    # the frozen identity (nspin=1 -> 2.0, nspin>=2 -> 1.0) so a submitted run
    # cannot silently relabel a metallic state as an insulator.
    default_occupied_value = 2.0 if identity_nspin == 1 else 1.0
    try:
        window = _window_for_run(run, default_occupied_value=default_occupied_value)
    except ScientificBandError as exc:
        raise MaterialClassEvaluationError("WINDOW_INVALID", str(exc)) from exc
    window_valid = (
        window.get("fundamental_gw_gap_ev", float("nan"))
        == window.get("fundamental_gw_gap_ev", float("nan"))
        and math.isfinite(float(window["fundamental_gw_gap_ev"]))
        and int(window["state_count"]) > 0
    )
    gates.append(
        _gate(
            "window.valid",
            window_valid,
            measured={
                "spins": window.get("spins"),
                "state_count": window.get("state_count"),
                "fundamental_gw_gap_ev": window.get("fundamental_gw_gap_ev"),
                "vbm_band_by_spin": window.get("vbm_band_by_spin"),
                "cbm_band_by_spin": window.get("cbm_band_by_spin"),
            },
            threshold="finite spin-resolved insulating window with a well-defined fundamental gap",
        )
    )

    # Reference regression, when frozen.
    reference = identity.get("reference")
    if reference_status == "REFERENCE_AVAILABLE" and isinstance(reference, dict):
        try:
            regression = evaluate_regression(
                run.get("candidate", {}),
                reference.get("candidate", {}),
                tolerance_ev=tolerance_ev,
            )
        except ScientificEvaluationError as exc:
            raise MaterialClassEvaluationError(
                "REFERENCE_EVALUATION_INVALID", str(exc)
            ) from exc
        reference_ok = regression.get("status") == "PASS"
        gates.append(
            _gate(
                "reference.status",
                reference_ok,
                measured=regression,
                threshold="within tolerance_ev of the frozen reference",
            )
        )
        reference_verdict = {
            "status": "PASS" if reference_ok else "FAIL",
            "scientific_status": "PASS" if reference_ok else "FAIL",
            "promotion_eligibility": "ENABLED" if reference_ok else "BLOCKED",
        }
    else:
        gates.append(
            _gate(
                "reference.status",
                False,
                measured="REFERENCE_PENDING",
                threshold="a frozen numerical reference is required for acceptance",
                evidence=["identity asset and spin contract are frozen; the numerical reference is not yet produced"],
            )
        )
        reference_verdict = {
            "status": "REFERENCE_PENDING",
            "scientific_status": "NOT_EVALUATED",
            "promotion_eligibility": "BLOCKED",
        }

    non_gate_failures = [
        gate for gate in gates if gate["gate_id"] != "reference.status" and gate["status"] == "FAIL"
    ]
    if non_gate_failures:
        verdict = {
            "status": "FAIL",
            "scientific_status": "FAIL",
            "promotion_eligibility": "BLOCKED",
        }
    else:
        verdict = reference_verdict

    return {
        "schema": "oml.material-class-result.v1",
        "material_class_id": material_class_id,
        "material_class_formula": material.get("formula"),
        "status": verdict["status"],
        "scientific_status": verdict["scientific_status"],
        "promotion_eligibility": verdict["promotion_eligibility"],
        "reference_status": reference_status,
        "gates": gates,
        "window": {
            "spins": window.get("spins"),
            "vbm_band_by_spin": window.get("vbm_band_by_spin"),
            "cbm_band_by_spin": window.get("cbm_band_by_spin"),
            "state_count": window.get("state_count"),
            "fundamental_gw_gap_ev": window.get("fundamental_gw_gap_ev"),
            "spin_windows": window.get("spin_windows"),
        },
        "verdict": verdict,
    }


def evaluate_registered_material_class(
    *,
    material_class_id: str,
    run: dict[str, Any],
    tolerance_ev: float = 1e-3,
) -> dict[str, Any]:
    return evaluate_material_class(
        material_class_id, run, tolerance_ev=tolerance_ev
    )
