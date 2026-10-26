"""Reference-free health checks for the full Coulomb matrices.

ABACUS constructs the full auxiliary Coulomb matrices in two algorithms per
dimensionality (``ewald`` and the direct Gram construction). A broken matrix is
a common root cause of large-scale EXX/GW band errors, so the loop checks
Hermiticity, positive semidefiniteness, and cross-algorithm agreement before
blaming the basis or the screening thresholds.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class CoulombGateError(ValueError):
    """Raised when Coulomb inputs are not square matrices of the same shape."""


def _matrix(values: Any) -> np.ndarray:
    matrix = np.asarray(values)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise CoulombGateError("Coulomb input must be a square matrix")
    return matrix.astype(complex)


def hermitian_residual(values: Any) -> float:
    matrix = _matrix(values)
    scale = max(1.0, float(np.max(np.abs(matrix))))
    return float(np.max(np.abs(matrix - matrix.conj().T)) / scale)


def check_hermitian(values: Any, *, tolerance: float = 1e-8) -> dict[str, Any]:
    residual = hermitian_residual(values)
    return {"pass": residual <= tolerance, "residual": residual, "tolerance": tolerance}


def check_positive_semidefinite(
    values: Any,
    *,
    tolerance: float = 1e-10,
    max_negative_eigenvalues: int = 10,
) -> dict[str, Any]:
    matrix = _matrix(values)
    hermitian_part = (matrix + matrix.conj().T) / 2.0
    eigenvalues = np.linalg.eigvalsh(hermitian_part)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))))
    negative = [float(value) for value in eigenvalues if value < -tolerance * scale]
    near_null = [float(value) for value in eigenvalues if abs(value) <= tolerance * scale]
    return {
        "pass": len(negative) <= max_negative_eigenvalues,
        "tolerated_negative_count": min(len(negative), max_negative_eigenvalues),
        "max_negative_eigenvalues": max_negative_eigenvalues,
        "min_eigenvalue": float(eigenvalues.min()),
        "max_eigenvalue": float(eigenvalues.max()),
        "negative": negative[:20],
        "negative_count": len(negative),
        "near_null_count": len(near_null),
        "tolerance": tolerance,
    }


def compare_constructions(
    left: Any,
    right: Any,
    *,
    atol: float = 1e-10,
) -> dict[str, Any]:
    first = _matrix(left)
    second = _matrix(right)
    if first.shape != second.shape:
        raise CoulombGateError("compared Coulomb matrices must have the same shape")
    difference = float(np.max(np.abs(first - second))) if first.size else 0.0
    scale = max(1.0, float(np.max(np.abs(first))), float(np.max(np.abs(second))))
    return {
        "agree": difference <= atol * scale,
        "max_abs_diff": difference,
        "relative_diff": difference / scale,
        "atol": atol,
    }


def coulomb_health(
    values: Any,
    *,
    other_construction: Any | None = None,
    hermitian_tolerance: float = 1e-8,
    psd_tolerance: float = 1e-10,
    max_negative_eigenvalues: int = 10,
) -> dict[str, Any]:
    """Return the fullcoul verdict plus the findings that drove it."""
    hermitian = check_hermitian(values, tolerance=hermitian_tolerance)
    psd = check_positive_semidefinite(
        values,
        tolerance=psd_tolerance,
        max_negative_eigenvalues=max_negative_eigenvalues,
    )
    cross = (
        compare_constructions(values, other_construction)
        if other_construction is not None
        else None
    )
    findings: list[str] = []
    if not hermitian["pass"]:
        findings.append(
            f"Coulomb matrix is not Hermitian (residual {hermitian['residual']:.3e})"
        )
    if not psd["pass"]:
        findings.append(
            f"Coulomb matrix has {psd['negative_count']} negative eigenvalues "
            f"(maximum allowed {max_negative_eigenvalues}, "
            f"minimum {psd['min_eigenvalue']:.3e})"
        )
    if cross is not None and not cross["agree"]:
        findings.append(
            "ewald and direct constructions disagree "
            f"(relative difference {cross['relative_diff']:.3e})"
        )
    verdict = "PASS" if not findings else "FAIL"
    return {
        "verdict": verdict,
        "hermitian": hermitian,
        "psd": psd,
        "cross_check": cross,
        "findings": findings,
    }
