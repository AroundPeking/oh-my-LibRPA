from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from typing import Any

from .admission_manifest import load_admission_manifest


STRICT2D_SOS_RPA_MOS2_BENCHMARK_ID = "strict2d-sos-rpa-mos2-qavg-v1"
ROUTE_BENCHMARK_NAMES = {
    STRICT2D_SOS_RPA_MOS2_BENCHMARK_ID: f"{STRICT2D_SOS_RPA_MOS2_BENCHMARK_ID}.json",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RouteBenchmarkError(ValueError):
    """Raised when a route benchmark is malformed or cannot be evaluated."""


def _packaged_benchmark_dir() -> Path:
    return Path(__file__).resolve().parent / "route_benchmarks"


def _repository_benchmark_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "routes"


def list_route_benchmarks() -> tuple[str, ...]:
    return tuple(ROUTE_BENCHMARK_NAMES)


def _benchmark_path(benchmark_id: str) -> Path:
    try:
        name = ROUTE_BENCHMARK_NAMES[benchmark_id]
    except KeyError as exc:
        raise RouteBenchmarkError(f"unknown route benchmark: {benchmark_id}") from exc
    packaged = _packaged_benchmark_dir() / name
    return packaged if packaged.is_file() else _repository_benchmark_dir() / name


def _positive_finite(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise RouteBenchmarkError(f"{label} must be a positive finite number")
    return float(value)


def _finite(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise RouteBenchmarkError(f"{label} must be finite")
    return float(value)


def _power_fit(
    meshes: list[int],
    energies: list[float],
    power: float,
) -> tuple[float, float]:
    x_values = [mesh ** (-power) for mesh in meshes]
    x_mean = sum(x_values) / len(x_values)
    energy_mean = sum(energies) / len(energies)
    denominator = sum((value - x_mean) ** 2 for value in x_values)
    if denominator <= 0.0:
        raise RouteBenchmarkError("k-mesh fit is singular")
    coefficient = sum(
        (x_value - x_mean) * (energy - energy_mean)
        for x_value, energy in zip(x_values, energies, strict=True)
    ) / denominator
    limit = energy_mean - coefficient * x_mean
    rms_millihartree = (
        sum(
            (energy - (limit + coefficient * x_value)) ** 2
            for x_value, energy in zip(x_values, energies, strict=True)
        )
        / len(energies)
    ) ** 0.5 * 1000.0
    return limit, rms_millihartree


def _free_power_fit(
    meshes: list[int],
    energies: list[float],
    lower: float,
    upper: float,
) -> tuple[float, float]:
    golden_ratio = (math.sqrt(5.0) - 1.0) / 2.0
    left = lower
    right = upper
    inner_left = right - golden_ratio * (right - left)
    inner_right = left + golden_ratio * (right - left)
    for _ in range(96):
        left_rms = _power_fit(meshes, energies, inner_left)[1]
        right_rms = _power_fit(meshes, energies, inner_right)[1]
        if left_rms < right_rms:
            right = inner_right
            inner_right = inner_left
            inner_left = right - golden_ratio * (right - left)
        else:
            left = inner_left
            inner_left = inner_right
            inner_right = left + golden_ratio * (right - left)
    power = (left + right) / 2.0
    return power, _power_fit(meshes, energies, power)[0]


def _validate_sha_tree(value: Any, label: str) -> None:
    if isinstance(value, dict):
        if not value:
            raise RouteBenchmarkError(f"{label} must not be empty")
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise RouteBenchmarkError(f"{label} contains an invalid key")
            _validate_sha_tree(child, f"{label}.{key}")
        return
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise RouteBenchmarkError(f"{label} must contain SHA-256 digests")


def validate_route_benchmark(benchmark: dict[str, Any]) -> None:
    if benchmark.get("schema") != "oml.route-benchmark.v1":
        raise RouteBenchmarkError("route benchmark schema must be oml.route-benchmark.v1")
    if benchmark.get("benchmark_id") != STRICT2D_SOS_RPA_MOS2_BENCHMARK_ID:
        raise RouteBenchmarkError("benchmark_id is not registered")
    if benchmark.get("route_id") != "strict_2d_sos_rpa":
        raise RouteBenchmarkError("route_id must be strict_2d_sos_rpa")
    if benchmark.get("acceptance_model") != "reference_bounded_four_mesh":
        raise RouteBenchmarkError("acceptance_model must be reference_bounded_four_mesh")
    if benchmark.get("required_meshes") != [8, 10, 12, 16]:
        raise RouteBenchmarkError("required_meshes must be N=8,10,12,16")
    if benchmark.get("fit_policy") != {
        "model": "least_squares_e_infinity_plus_a_n_minus_p",
        "fixed_power": 3.0,
        "free_power_bounds": [1.0, 6.0],
    }:
        raise RouteBenchmarkError("fit_policy has drifted")

    material = benchmark.get("material")
    if not isinstance(material, dict) or material.get("formula") != "MoS2":
        raise RouteBenchmarkError("material must identify the MoS2 reference")
    _validate_sha_tree(material.get("identity_sha256"), "material.identity_sha256")
    mesh_identity = benchmark.get("mesh_identity_sha256")
    if not isinstance(mesh_identity, dict) or set(mesh_identity) != {"8", "10", "12", "16"}:
        raise RouteBenchmarkError("mesh_identity_sha256 must cover N=8,10,12,16")
    _validate_sha_tree(mesh_identity, "mesh_identity_sha256")

    software = benchmark.get("software_identity")
    if not isinstance(software, dict):
        raise RouteBenchmarkError("software_identity must be an object")
    for key in (
        "abacus_revision",
        "librpa_revision",
        "librpa_executable_sha256",
        "pyatb_revision",
    ):
        value = software.get(key)
        expected_length = 64 if key.endswith("sha256") else 40
        if (
            not isinstance(value, str)
            or len(value) != expected_length
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise RouteBenchmarkError(f"software_identity.{key} is invalid")

    references = benchmark.get("reference_series")
    if (
        not isinstance(references, list)
        or len(references) != 4
        or {entry.get("mesh") for entry in references if isinstance(entry, dict)}
        != {8, 10, 12, 16}
    ):
        raise RouteBenchmarkError("reference_series must cover N=8,10,12,16")
    for entry in references:
        _finite(entry.get("gamma_hartree"), "reference gamma energy")
        _finite(entry.get("total_hartree"), "reference total energy")

    tolerances = benchmark.get("tolerances")
    if not isinstance(tolerances, dict):
        raise RouteBenchmarkError("tolerances must be an object")
    for key in (
        "reference_gamma_abs_hartree",
        "reference_total_abs_hartree",
        "gamma_area_scaled_relative_span_max",
        "endpoint_total_delta_millihartree_max",
        "fixed_n_minus_3_rms_millihartree_max",
        "extrapolated_limit_span_millihartree_max",
        "finite_q_control_max_abs_delta_hartree",
        "reported_free_power_abs",
        "reported_fit_metric_millihartree_abs",
    ):
        _positive_finite(tolerances.get(key), f"tolerances.{key}")

    boundary = benchmark.get("claim_boundary")
    expected_boundary = {
        "operational_k_mesh_convergence": True,
        "forbid_asymptotic_exponent_claim": True,
        "strict_2d_sos_rpa": True,
        "strict_2d_gw": False,
    }
    if boundary != expected_boundary:
        raise RouteBenchmarkError("claim_boundary exceeds strict-2D SOS-RPA")


def load_route_benchmark(benchmark_id: str) -> dict[str, Any]:
    path = _benchmark_path(benchmark_id)
    try:
        benchmark = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RouteBenchmarkError(f"cannot read route benchmark {path}: {exc}") from exc
    if not isinstance(benchmark, dict):
        raise RouteBenchmarkError("route benchmark root must be an object")
    validate_route_benchmark(benchmark)
    return copy.deepcopy(benchmark)


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


def _mesh_map(entries: Any, label: str) -> dict[int, dict[str, Any]]:
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise RouteBenchmarkError(f"{label} must be an array of objects")
    result = {entry.get("mesh"): entry for entry in entries}
    if any(isinstance(mesh, bool) or not isinstance(mesh, int) for mesh in result):
        raise RouteBenchmarkError(f"{label} contains an invalid mesh")
    return result


def evaluate_route_benchmark(
    benchmark: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    validate_route_benchmark(benchmark)
    tolerances = benchmark["tolerances"]
    required_meshes = benchmark["required_meshes"]
    references = _mesh_map(benchmark["reference_series"], "reference_series")
    actual = _mesh_map(manifest.get("validated_cases"), "validated_cases")
    controls = _mesh_map(manifest.get("validation_controls"), "validation_controls")

    software = benchmark["software_identity"]
    sources = manifest.get("sources", {})
    librpa_source = sources.get("librpa", {}) if isinstance(sources, dict) else {}
    identity_checks = (
        manifest.get("manifest_id") == benchmark["manifest_id"],
        manifest.get("profile_id") == benchmark["profile_id"],
        manifest.get("route", {}).get("route_id") == benchmark["route_id"],
        sources.get("abacus", {}).get("revision") == software["abacus_revision"],
        librpa_source.get("revision") == software["librpa_revision"],
        librpa_source.get("executable_sha256") == software["librpa_executable_sha256"],
        sources.get("pyatb", {}).get("revision") == software["pyatb_revision"],
        manifest.get("contract") == benchmark["required_contract"],
    )
    gates = [
        _gate(
            "identity.reference",
            all(identity_checks),
            measured={
                "manifest_id": manifest.get("manifest_id"),
                "profile_id": manifest.get("profile_id"),
            },
            threshold={
                "manifest_id": benchmark["manifest_id"],
                "profile_id": benchmark["profile_id"],
            },
        )
    ]

    meshes_complete = set(actual) == set(required_meshes) and set(controls) == set(required_meshes)
    gates.append(
        _gate(
            "mesh.completeness",
            meshes_complete,
            measured={"physical": sorted(actual), "controls": sorted(controls)},
            threshold=required_meshes,
        )
    )
    evidence_status = meshes_complete and all(
        actual[mesh].get("status") == "PASS" for mesh in required_meshes
    ) and all(
        controls[mesh].get("status") == "PASS_FINITE_Q_CONTROL_RAW_GAMMA_COMPLEX"
        and controls[mesh].get("route") == "diagnostic_no_headwing"
        and controls[mesh].get("physical_route") is False
        for mesh in required_meshes
    )
    gates.append(
        _gate(
            "evidence.status",
            evidence_status,
            measured={
                "physical": [actual[mesh].get("status") for mesh in sorted(actual)],
                "controls": [controls[mesh].get("status") for mesh in sorted(controls)],
            },
            threshold={
                "physical": "PASS",
                "controls": "PASS_FINITE_Q_CONTROL_RAW_GAMMA_COMPLEX",
            },
        )
    )

    comparable_meshes = sorted(set(required_meshes) & set(actual))
    gamma_deltas = [
        abs(_finite(actual[mesh].get("gamma_hartree"), "actual gamma energy") - references[mesh]["gamma_hartree"])
        for mesh in comparable_meshes
    ]
    total_deltas = [
        abs(_finite(actual[mesh].get("total_hartree"), "actual total energy") - references[mesh]["total_hartree"])
        for mesh in comparable_meshes
    ]
    max_gamma_delta = max(gamma_deltas, default=math.inf)
    max_total_delta = max(total_deltas, default=math.inf)
    gates.extend(
        (
            _gate(
                "reference.gamma_energy",
                meshes_complete and max_gamma_delta <= tolerances["reference_gamma_abs_hartree"],
                measured=max_gamma_delta,
                threshold=tolerances["reference_gamma_abs_hartree"],
            ),
            _gate(
                "reference.total_energy",
                meshes_complete and max_total_delta <= tolerances["reference_total_abs_hartree"],
                measured=max_total_delta,
                threshold=tolerances["reference_total_abs_hartree"],
            ),
        )
    )

    gamma_scaled = [abs(actual[mesh]["gamma_hartree"]) * mesh * mesh for mesh in comparable_meshes]
    gamma_mean = sum(gamma_scaled) / len(gamma_scaled) if gamma_scaled else math.nan
    gamma_span = (
        (max(gamma_scaled) - min(gamma_scaled)) / gamma_mean
        if gamma_scaled and gamma_mean > 0
        else math.inf
    )
    endpoint_delta = (
        abs(actual[16]["total_hartree"] - actual[12]["total_hartree"]) * 1000.0
        if 12 in actual and 16 in actual
        else math.inf
    )
    gates.extend(
        (
            _gate(
                "convergence.gamma_area_scaling",
                meshes_complete
                and gamma_span <= tolerances["gamma_area_scaled_relative_span_max"],
                measured=gamma_span,
                threshold=tolerances["gamma_area_scaled_relative_span_max"],
            ),
            _gate(
                "convergence.endpoint_delta",
                meshes_complete
                and endpoint_delta <= tolerances["endpoint_total_delta_millihartree_max"],
                measured=endpoint_delta,
                threshold=tolerances["endpoint_total_delta_millihartree_max"],
            ),
        )
    )

    claim = manifest.get("k_mesh_claim", {})
    claim_boundary_ok = (
        claim.get("convergence_exponent_established") is False
        and benchmark["claim_boundary"]["forbid_asymptotic_exponent_claim"] is True
    )
    gates.append(
        _gate(
            "claim.boundary",
            claim_boundary_ok,
            measured={
                "convergence_exponent_established": claim.get(
                    "convergence_exponent_established"
                )
            },
            threshold={"convergence_exponent_established": False},
        )
    )
    reported_power = _finite(
        claim.get("observed_free_power"),
        "k_mesh_claim.observed_free_power",
    )
    reported_fixed_rms = _finite(
        claim.get("fixed_n_minus_3_rms_millihartree"),
        "k_mesh_claim.fixed_n_minus_3_rms_millihartree",
    )
    reported_limit_span = _finite(
        claim.get("extrapolated_limit_span_millihartree"),
        "k_mesh_claim.extrapolated_limit_span_millihartree",
    )
    if meshes_complete:
        fit_meshes = list(required_meshes)
        fit_energies = [
            _finite(actual[mesh].get("total_hartree"), "actual total energy")
            for mesh in fit_meshes
        ]
        fixed_limit, fixed_rms = _power_fit(
            fit_meshes,
            fit_energies,
            benchmark["fit_policy"]["fixed_power"],
        )
        free_power, free_limit = _free_power_fit(
            fit_meshes,
            fit_energies,
            *benchmark["fit_policy"]["free_power_bounds"],
        )
        limit_span = abs(fixed_limit - free_limit) * 1000.0
    else:
        fixed_rms = math.inf
        free_power = math.inf
        limit_span = math.inf
    receipt_matches = meshes_complete and (
        abs(reported_power - free_power) <= tolerances["reported_free_power_abs"]
        and abs(reported_fixed_rms - fixed_rms)
        <= tolerances["reported_fit_metric_millihartree_abs"]
        and abs(reported_limit_span - limit_span)
        <= tolerances["reported_fit_metric_millihartree_abs"]
    )
    gates.append(
        _gate(
            "receipt.derived_metrics",
            receipt_matches,
            measured={
                "free_power": reported_power,
                "fixed_n_minus_3_rms_millihartree": reported_fixed_rms,
                "extrapolated_limit_span_millihartree": reported_limit_span,
            },
            threshold={
                "recomputed_free_power": free_power,
                "recomputed_fixed_n_minus_3_rms_millihartree": fixed_rms,
                "recomputed_extrapolated_limit_span_millihartree": limit_span,
            },
        )
    )
    gates.extend(
        (
            _gate(
                "convergence.fixed_n_minus_3_rms",
                fixed_rms <= tolerances["fixed_n_minus_3_rms_millihartree_max"],
                measured=fixed_rms,
                threshold=tolerances["fixed_n_minus_3_rms_millihartree_max"],
            ),
            _gate(
                "convergence.extrapolated_limit_span",
                limit_span <= tolerances["extrapolated_limit_span_millihartree_max"],
                measured=limit_span,
                threshold=tolerances["extrapolated_limit_span_millihartree_max"],
            ),
        )
    )

    finite_q_deltas = []
    for mesh in comparable_meshes:
        if mesh not in controls:
            continue
        physical_non_gamma = actual[mesh]["total_hartree"] - actual[mesh]["gamma_hartree"]
        control_non_gamma = controls[mesh]["total_hartree"] - controls[mesh]["gamma_real_hartree"]
        finite_q_deltas.append(abs(physical_non_gamma - control_non_gamma))
    max_finite_q_delta = max(finite_q_deltas, default=math.inf)
    gates.append(
        _gate(
            "control.finite_q_agreement",
            meshes_complete
            and max_finite_q_delta <= tolerances["finite_q_control_max_abs_delta_hartree"],
            measured=max_finite_q_delta,
            threshold=tolerances["finite_q_control_max_abs_delta_hartree"],
            evidence=["diagnostic no-head/wing Gamma values are not physical results"],
        )
    )

    passed = all(gate["status"] == "PASS" for gate in gates)
    return {
        "schema": "oml.route-benchmark-result.v1",
        "benchmark_id": benchmark["benchmark_id"],
        "manifest_id": manifest.get("manifest_id"),
        "route_id": benchmark["route_id"],
        "status": "PASS" if passed else "FAIL",
        "scientific_status": "PASS" if passed else "FAIL",
        "promotion_eligibility": "ENABLED" if passed else "BLOCKED",
        "gates": gates,
        "metrics": {
            "reference_gamma_max_abs_delta_hartree": max_gamma_delta,
            "reference_total_max_abs_delta_hartree": max_total_delta,
            "gamma_area_scaled_relative_span": gamma_span,
            "endpoint_total_delta_millihartree": endpoint_delta,
            "fixed_n_minus_3_rms_millihartree": fixed_rms,
            "observed_free_power": free_power,
            "extrapolated_limit_span_millihartree": limit_span,
            "finite_q_control_max_abs_delta_hartree": max_finite_q_delta,
        },
        "claims": {
            "operational_k_mesh_convergence": passed,
            "asymptotic_exponent_established": False,
            "strict_2d_sos_rpa": passed,
            "strict_2d_gw": False,
        },
    }


def evaluate_registered_route_benchmark(
    *,
    benchmark_id: str,
    manifest_id: str,
) -> dict[str, Any]:
    benchmark = load_route_benchmark(benchmark_id)
    if manifest_id != benchmark["manifest_id"]:
        raise RouteBenchmarkError(
            f"benchmark {benchmark_id} requires manifest {benchmark['manifest_id']}"
        )
    manifest = load_admission_manifest(manifest_id=manifest_id)
    return evaluate_route_benchmark(benchmark, manifest)
