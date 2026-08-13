from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any, Iterable

from .scientific_definition import CONVERGENCE_AXES


REGISTRY_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
PACKAGED_BENCHMARK_ROOT = Path(__file__).with_name("scientific_benchmarks")


class ScientificRegistryError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


def _validate_identifier(identifier: str) -> str:
    if not isinstance(identifier, str) or REGISTRY_ID_PATTERN.fullmatch(identifier) is None:
        raise ScientificRegistryError(
            "REGISTRY_ID_INVALID",
            "registry identifiers may contain only lowercase letters, digits, hyphens, and underscores",
            details={"identifier": identifier},
        )
    return identifier


def _registry_roots(roots: Iterable[str | Path] | None) -> tuple[Path, ...]:
    if roots is not None:
        private = tuple(Path(root).expanduser().resolve() for root in roots)
    else:
        configured = os.environ.get("OML_SCIENCE_REGISTRY_ROOTS", "")
        private = tuple(
            Path(root).expanduser().resolve()
            for root in configured.split(os.pathsep)
            if root.strip()
        )
    return (*private, PACKAGED_BENCHMARK_ROOT.resolve())


def _load_registered_json(
    identifier: str,
    *,
    roots: Iterable[str | Path] | None,
    missing_code: str,
) -> dict[str, Any]:
    name = _validate_identifier(identifier)
    for root in _registry_roots(roots):
        candidate = root / f"{name}.json"
        if not candidate.is_file():
            continue
        try:
            value = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ScientificRegistryError(
                missing_code.replace("NOT_FOUND", "INVALID"),
                f"cannot read registry entry {candidate}: {exc}",
            ) from exc
        if not isinstance(value, dict):
            raise ScientificRegistryError(
                missing_code.replace("NOT_FOUND", "INVALID"),
                f"registry entry must be a JSON object: {candidate}",
            )
        return value
    raise ScientificRegistryError(missing_code, f"registry entry is not available: {name}")


def _positive_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def _validate_benchmark(value: dict[str, Any], benchmark_id: str) -> dict[str, Any]:
    required_axes = value.get("required_axes")
    window = value.get("state_window")
    reference_status = value.get("reference_status")
    valid = (
        value.get("schema_version") == 1
        and value.get("benchmark_id") == benchmark_id
        and value.get("system_type") == "solid"
        and _positive_finite(value.get("regression_tolerance_ev"))
        and _positive_finite(value.get("convergence_tolerance_ev"))
        and isinstance(window, dict)
        and isinstance(window.get("below_vbm"), int)
        and not isinstance(window.get("below_vbm"), bool)
        and window["below_vbm"] >= 0
        and isinstance(window.get("above_cbm"), int)
        and not isinstance(window.get("above_cbm"), bool)
        and window["above_cbm"] >= 0
        and isinstance(required_axes, list)
        and required_axes
        and len(required_axes) == len(set(required_axes))
        and all(axis in CONVERGENCE_AXES for axis in required_axes)
        and reference_status in {"AVAILABLE", "NOT_AVAILABLE"}
        and isinstance(value.get("require_positive_gw_gap"), bool)
        and (
            (reference_status == "NOT_AVAILABLE" and value.get("reference") is None)
            or (reference_status == "AVAILABLE" and isinstance(value.get("reference"), dict))
        )
    )
    if not valid:
        raise ScientificRegistryError(
            "BENCHMARK_INVALID",
            f"benchmark policy failed schema validation: {benchmark_id}",
        )
    return value


def load_benchmark(
    benchmark_id: str,
    *,
    roots: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    value = _load_registered_json(
        benchmark_id,
        roots=roots,
        missing_code="BENCHMARK_NOT_FOUND",
    )
    return _validate_benchmark(value, benchmark_id)


def load_convergence_bundle(
    bundle_id: str,
    *,
    roots: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    value = _load_registered_json(
        bundle_id,
        roots=roots,
        missing_code="CONVERGENCE_BUNDLE_NOT_FOUND",
    )
    run_ids = value.get("run_ids")
    valid = (
        value.get("schema_version") == 1
        and value.get("bundle_id") == bundle_id
        and isinstance(value.get("benchmark_id"), str)
        and REGISTRY_ID_PATTERN.fullmatch(value["benchmark_id"]) is not None
        and value.get("axis") in CONVERGENCE_AXES
        and isinstance(run_ids, list)
        and len(run_ids) == 2
        and len(set(run_ids)) == 2
        and all(isinstance(run_id, str) and REGISTRY_ID_PATTERN.fullmatch(run_id) for run_id in run_ids)
    )
    if not valid:
        raise ScientificRegistryError(
            "CONVERGENCE_BUNDLE_INVALID",
            f"convergence bundle failed schema validation: {bundle_id}",
        )
    return value
