from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


COULOMB_MARKER = -20129433
CHI0_MARKER = -41073291


class SternheimerDiagnosticError(ValueError):
    """Raised when a Sternheimer diagnostic matrix violates reader-v1."""


@dataclass(frozen=True)
class _BlockMatrix:
    path: Path
    metadata: dict[str, Any]
    values: np.ndarray


def _pair_from_index(index: int, natoms: int) -> tuple[int, int]:
    remaining = index
    for first in range(natoms):
        row_size = natoms - first
        if remaining < row_size:
            return first, first + remaining
        remaining -= row_size
    raise SternheimerDiagnosticError(f"invalid atom-pair index {index}")


def _read_block_matrix(path: Path, *, response: bool) -> _BlockMatrix:
    data = path.read_bytes()
    try:
        if response:
            if len(data) < 44:
                raise SternheimerDiagnosticError("response file is smaller than its v1 header")
            marker, iq, ifreq, naux, value_flag, natoms = struct.unpack_from("=6i", data)
            omega, weight = struct.unpack_from("=2d", data, 24)
            (nblocks,) = struct.unpack_from("=i", data, 40)
            position = 44
            metadata: dict[str, Any] = {
                "marker": marker,
                "iq": iq,
                "ifreq": ifreq,
                "naux": naux,
                "value_flag": value_flag,
                "natoms": natoms,
                "omega": omega,
                "weight": weight,
                "nblocks": nblocks,
            }
            if marker != CHI0_MARKER:
                raise SternheimerDiagnosticError(
                    f"response marker {marker} != expected {CHI0_MARKER}"
                )
        else:
            if len(data) < 24:
                raise SternheimerDiagnosticError("Coulomb file is smaller than its v1 header")
            marker, iq, naux, value_flag, natoms, nblocks = struct.unpack_from("=6i", data)
            position = 24
            metadata = {
                "marker": marker,
                "iq": iq,
                "naux": naux,
                "value_flag": value_flag,
                "natoms": natoms,
                "nblocks": nblocks,
            }
            if marker != COULOMB_MARKER:
                raise SternheimerDiagnosticError(
                    f"Coulomb marker {marker} != expected {COULOMB_MARKER}"
                )

        if iq <= 0 or naux <= 0 or natoms <= 0 or nblocks < 0:
            raise SternheimerDiagnosticError("reader-v1 header dimensions must be positive")
        if response and ifreq <= 0:
            raise SternheimerDiagnosticError("response frequency index must be positive")
        if value_flag not in {0, 1}:
            raise SternheimerDiagnosticError(f"unsupported reader-v1 value flag {value_flag}")

        atom_naux = struct.unpack_from(f"={natoms}i", data, position)
        position += 4 * natoms
        if any(value <= 0 for value in atom_naux) or sum(atom_naux) != naux:
            raise SternheimerDiagnosticError("per-atom auxiliary sizes do not sum to naux")
        npairs = natoms * (natoms + 1) // 2
        if nblocks != npairs:
            raise SternheimerDiagnosticError(
                f"reader-v1 matrix has {nblocks} blocks but requires {npairs}"
            )

        records = [struct.unpack_from("=iq", data, position + 12 * block) for block in range(nblocks)]
        table_end = position + 12 * nblocks
        if len({pair for pair, _ in records}) != nblocks:
            raise SternheimerDiagnosticError("reader-v1 matrix has duplicate atom-pair blocks")

        offsets = np.cumsum((0, *atom_naux))
        matrix = np.zeros((naux, naux), dtype=np.complex128)
        dtype = np.dtype(np.complex128 if value_flag == 1 else np.float64)
        intervals: list[tuple[int, int]] = []
        for pair_index, byte_offset in records:
            first, second = _pair_from_index(pair_index, natoms)
            nfirst = atom_naux[first]
            nsecond = atom_naux[second]
            payload_bytes = nfirst * nsecond * dtype.itemsize
            if byte_offset < table_end or byte_offset + payload_bytes > len(data):
                raise SternheimerDiagnosticError(
                    f"invalid payload bounds for atom-pair block {pair_index}"
                )
            intervals.append((byte_offset, byte_offset + payload_bytes))
            block = np.frombuffer(
                data,
                dtype=dtype,
                count=nfirst * nsecond,
                offset=byte_offset,
            ).reshape((nfirst, nsecond))
            first_slice = slice(offsets[first], offsets[first + 1])
            second_slice = slice(offsets[second], offsets[second + 1])
            matrix[first_slice, second_slice] = block
            if first != second:
                matrix[second_slice, first_slice] = block.conj().T

        intervals.sort()
        for previous, current in zip(intervals, intervals[1:]):
            if current[0] < previous[1]:
                raise SternheimerDiagnosticError("reader-v1 matrix payload blocks overlap")
        if not np.isfinite(matrix).all():
            raise SternheimerDiagnosticError("reader-v1 matrix contains non-finite values")
    except (struct.error, ValueError) as exc:
        if isinstance(exc, SternheimerDiagnosticError):
            raise
        raise SternheimerDiagnosticError(f"cannot parse reader-v1 matrix: {exc}") from exc

    metadata["atom_naux"] = tuple(int(value) for value in atom_naux)
    return _BlockMatrix(path=path, metadata=metadata, values=matrix)


def _read_grid_coulomb(path: Path) -> np.ndarray:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not lines or len(lines[0].split()) != 2 or lines[0].split()[0] != "naux":
        raise SternheimerDiagnosticError("grid Coulomb diagnostic is missing its naux header")
    try:
        naux = int(lines[0].split()[1])
    except ValueError as exc:
        raise SternheimerDiagnosticError("grid Coulomb naux must be an integer") from exc
    if naux <= 0:
        raise SternheimerDiagnosticError("grid Coulomb naux must be positive")

    matrix = np.zeros((naux, naux), dtype=np.complex128)
    seen = np.zeros((naux, naux), dtype=np.bool_)
    for line_number, line in enumerate(lines[1:], start=2):
        fields = line.split()
        if len(fields) != 4:
            raise SternheimerDiagnosticError(
                f"grid Coulomb line {line_number} must contain row, column, real, and imaginary"
            )
        try:
            row, column = int(fields[0]), int(fields[1])
            value = complex(float(fields[2]), float(fields[3]))
        except ValueError as exc:
            raise SternheimerDiagnosticError(
                f"grid Coulomb line {line_number} contains an invalid numeric value"
            ) from exc
        if not (0 <= row < naux and 0 <= column < naux):
            raise SternheimerDiagnosticError(
                f"grid Coulomb line {line_number} has an out-of-range matrix index"
            )
        if seen[row, column]:
            raise SternheimerDiagnosticError(
                f"grid Coulomb line {line_number} duplicates matrix entry ({row}, {column})"
            )
        matrix[row, column] = value
        seen[row, column] = True
    if not seen.all():
        raise SternheimerDiagnosticError("grid Coulomb diagnostic does not contain every matrix entry")
    if not np.isfinite(matrix).all():
        raise SternheimerDiagnosticError("grid Coulomb diagnostic contains non-finite values")
    return matrix


def _gate(
    gate_id: str,
    status: str,
    message: str,
    paths: list[Path],
    *,
    repair: str | None = None,
    measurements: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gate = {
        "gate_id": gate_id,
        "status": status,
        "message": message,
        "evidence": [str(path) for path in paths],
    }
    if repair is not None:
        gate["repair"] = repair
    if measurements is not None:
        gate["measurements"] = measurements
    return gate


def _relative_norm(difference: np.ndarray, reference: np.ndarray) -> float:
    denominator = float(np.linalg.norm(reference))
    numerator = float(np.linalg.norm(difference))
    return numerator if denominator == 0.0 else numerator / denominator


def _hermitian_residual(matrix: np.ndarray) -> float:
    return _relative_norm(matrix - matrix.conj().T, matrix)


def _trace_log(
    coulomb_eigenvalues: np.ndarray,
    coulomb_eigenvectors: np.ndarray,
    response: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    active = coulomb_eigenvalues > threshold
    inverse_sqrt = np.zeros_like(coulomb_eigenvalues)
    inverse_sqrt[active] = 1.0 / np.sqrt(coulomb_eigenvalues[active])
    transform = (coulomb_eigenvectors * inverse_sqrt) @ coulomb_eigenvectors.conj().T
    pi = transform @ response @ transform
    pi = 0.5 * (pi + pi.conj().T)
    eigenvalues, eigenvectors = np.linalg.eigh(pi)
    integrand = np.sum(np.log(1.0 - eigenvalues.astype(np.complex128)) + eigenvalues)
    generalized_mode = transform @ eigenvectors[:, 0]
    generalized_mode_norm = float(np.vdot(generalized_mode, generalized_mode).real)
    if generalized_mode_norm > 0.0:
        coulomb_times_mode = coulomb_eigenvectors @ (
            coulomb_eigenvalues
            * (coulomb_eigenvectors.conj().T @ generalized_mode)
        )
        mode_coulomb_rayleigh = float(
            np.vdot(generalized_mode, coulomb_times_mode).real
            / generalized_mode_norm
        )
        mode_response_rayleigh = float(
            np.vdot(generalized_mode, response @ generalized_mode).real
            / generalized_mode_norm
        )
    else:
        mode_coulomb_rayleigh = None
        mode_response_rayleigh = None
    outlier_ratio = None
    if eigenvalues.size > 1 and abs(float(eigenvalues[1])) > 0.0:
        outlier_ratio = abs(float(eigenvalues[0] / eigenvalues[1]))
    return {
        "active_coulomb_channels": int(np.sum(active)),
        "pi_eigenvalue_min": float(eigenvalues[0]),
        "pi_eigenvalue_max": float(eigenvalues[-1]),
        "positive_pi_eigenvalues": int(np.sum(eigenvalues > 1.0e-10)),
        "most_negative_pi_eigenvalues": [
            float(value) for value in eigenvalues[: min(5, eigenvalues.size)]
        ],
        "most_negative_mode_outlier_ratio": outlier_ratio,
        "most_negative_mode_coulomb_rayleigh": mode_coulomb_rayleigh,
        "most_negative_mode_response_rayleigh": mode_response_rayleigh,
        "integrand_real": float(integrand.real),
        "integrand_imag": float(integrand.imag),
    }


def _coulomb_metric_comparison(
    response_coulomb: np.ndarray,
    comparison_coulomb: np.ndarray,
    *,
    sqrt_coulomb_threshold: float,
    hermitian_tolerance: float,
    responses: dict[str, np.ndarray] | None = None,
) -> dict[str, Any]:
    response_hermitian = 0.5 * (response_coulomb + response_coulomb.conj().T)
    comparison_hermitian = 0.5 * (
        comparison_coulomb + comparison_coulomb.conj().T
    )
    response_eigenvalues, response_eigenvectors = np.linalg.eigh(response_hermitian)
    comparison_eigenvalues, comparison_eigenvectors = np.linalg.eigh(comparison_hermitian)
    negative_comparison_eigenvalues = int(
        np.sum(comparison_eigenvalues < -hermitian_tolerance)
    )
    response_active = response_eigenvalues > sqrt_coulomb_threshold
    active_response_vectors = response_eigenvectors[:, response_active]
    active_response_values = response_eigenvalues[response_active]
    if active_response_values.size:
        generalized_coulomb = (
            active_response_vectors.conj().T
            @ comparison_hermitian
            @ active_response_vectors
        )
        inverse_sqrt = 1.0 / np.sqrt(active_response_values)
        generalized_coulomb = (
            inverse_sqrt[:, None]
            * generalized_coulomb
            * inverse_sqrt[None, :]
        )
        generalized_coulomb = 0.5 * (
            generalized_coulomb + generalized_coulomb.conj().T
        )
        generalized_eigenvalues = np.linalg.eigvalsh(generalized_coulomb)
        generalized_min = float(generalized_eigenvalues[0])
        generalized_max = float(generalized_eigenvalues[-1])
        generalized_deviation = float(
            np.max(np.abs(generalized_eigenvalues - 1.0))
        )
    else:
        generalized_min = None
        generalized_max = None
        generalized_deviation = None
    return {
        "relative_error_to_response_metric": _relative_norm(
            comparison_hermitian - response_hermitian, response_hermitian
        ),
        "maximum_absolute_difference": float(
            np.max(np.abs(comparison_hermitian - response_hermitian))
        ),
        "response_metric_hermitian_relative_residual": _hermitian_residual(response_coulomb),
        "comparison_metric_hermitian_relative_residual": _hermitian_residual(comparison_coulomb),
        "response_metric_eigenvalue_min": float(response_eigenvalues[0]),
        "response_metric_eigenvalue_max": float(response_eigenvalues[-1]),
        "comparison_metric_eigenvalue_min": float(comparison_eigenvalues[0]),
        "comparison_metric_eigenvalue_max": float(comparison_eigenvalues[-1]),
        "comparison_metric_negative_eigenvalues": negative_comparison_eigenvalues,
        "generalized_active_channels": int(active_response_values.size),
        "generalized_eigenvalue_min": generalized_min,
        "generalized_eigenvalue_max": generalized_max,
        "maximum_generalized_deviation_from_one": generalized_deviation,
        "trace_log": (
            {
                name: _trace_log(
                    comparison_eigenvalues,
                    comparison_eigenvectors,
                    response,
                    sqrt_coulomb_threshold,
                )
                for name, response in responses.items()
            }
            if responses is not None and negative_comparison_eigenvalues == 0
            else None
        ),
    }


def _standard_reader_measurements(
    response_metric: _BlockMatrix,
    standard_reader: _BlockMatrix,
    *,
    sqrt_coulomb_threshold: float,
    hermitian_tolerance: float,
) -> dict[str, Any]:
    comparable_dimensions = standard_reader.values.shape == response_metric.values.shape
    measurements: dict[str, Any] = {
        "present": True,
        "path": str(standard_reader.path),
        "role": "diagnostic_only",
        "comparable_dimensions": comparable_dimensions,
        "iq": int(standard_reader.metadata["iq"]),
        "naux": int(standard_reader.metadata["naux"]),
        "atom_naux": standard_reader.metadata["atom_naux"],
    }
    if comparable_dimensions:
        measurements.update(
            _coulomb_metric_comparison(
                response_metric.values,
                standard_reader.values,
                sqrt_coulomb_threshold=sqrt_coulomb_threshold,
                hermitian_tolerance=hermitian_tolerance,
            )
        )
    return measurements


def inspect_grid_coulomb_consistency(
    root: str | Path,
    *,
    iq: int,
    sqrt_coulomb_threshold: float = 0.0,
    hermitian_tolerance: float = 1.0e-10,
    metric_relative_tolerance: float = 1.0e-6,
) -> dict[str, Any]:
    if iq <= 0:
        raise SternheimerDiagnosticError("iq must be positive")
    for label, value in {
        "sqrt_coulomb_threshold": sqrt_coulomb_threshold,
        "hermitian_tolerance": hermitian_tolerance,
        "metric_relative_tolerance": metric_relative_tolerance,
    }.items():
        if not math.isfinite(value) or value < 0.0:
            raise SternheimerDiagnosticError(f"{label} must be finite and non-negative")

    directory = Path(root).expanduser().resolve()
    response_path = directory / f"v1_sternheimer_coulomb_iq_{iq}_rank0.dat"
    standard_reader_path = directory / f"v1_coulomb_full_iq_{iq}_rank0.dat"
    grid_path = directory / "STERNHEIMER_GRID_COULOMB.dat"
    if not response_path.is_file():
        return {
            "ok": False,
            "status": "INCOMPLETE",
            "root": str(directory),
            "iq": iq,
            "gates": [
                _gate(
                    "files",
                    "FAIL",
                    "the dedicated Sternheimer Coulomb v1 metric is required",
                    [response_path],
                    repair="rerun the pinned ABACUS Sternheimer producer before response production",
                )
            ],
        }
    try:
        response_metric = _read_block_matrix(response_path, response=False)
        grid = _read_grid_coulomb(grid_path) if grid_path.is_file() else None
    except (OSError, SternheimerDiagnosticError) as exc:
        required_paths = [response_path]
        if grid_path.is_file():
            required_paths.append(grid_path)
        return {
            "ok": False,
            "status": "CONTRACT_FAIL",
            "root": str(directory),
            "iq": iq,
            "gates": [
                _gate(
                    "format",
                    "FAIL",
                    str(exc),
                    required_paths,
                    repair="regenerate the Sternheimer response metric with the pinned ABACUS producer",
                )
            ],
        }

    standard_reader = None
    standard_reader_error = None
    if standard_reader_path.is_file():
        try:
            standard_reader = _read_block_matrix(standard_reader_path, response=False)
        except (OSError, SternheimerDiagnosticError) as exc:
            standard_reader_error = str(exc)

    evidence = [response_path]
    if grid is not None:
        evidence.append(grid_path)
    if standard_reader_path.is_file():
        evidence.append(standard_reader_path)
    gates = [
        _gate(
            "files",
            "PASS",
            "the dedicated Sternheimer Coulomb v1 metric is present",
            evidence,
        )
    ]
    metadata_match = (
        response_metric.metadata["iq"] == iq
        and (grid is None or grid.shape == response_metric.values.shape)
    )
    if not metadata_match:
        gates.append(
            _gate(
                "metadata",
                "FAIL",
                "the response metric and optional grid diagnostic dimensions do not match",
                evidence,
                repair="regenerate the metrics for the same q point and auxiliary basis",
            )
        )
        return {
            "ok": False,
            "status": "CONTRACT_FAIL",
            "root": str(directory),
            "iq": iq,
            "gates": gates,
        }
    gates.append(
        _gate(
            "metadata",
            "PASS",
            "the response metric and optional grid diagnostic metadata match",
            evidence,
        )
    )
    comparison = grid if grid is not None else response_metric.values
    measurements = _coulomb_metric_comparison(
        response_metric.values,
        comparison,
        sqrt_coulomb_threshold=sqrt_coulomb_threshold,
        hermitian_tolerance=hermitian_tolerance,
    )
    measurements["grid_diagnostic_present"] = grid is not None
    if standard_reader is not None:
        standard_measurements = _standard_reader_measurements(
            response_metric,
            standard_reader,
            sqrt_coulomb_threshold=sqrt_coulomb_threshold,
            hermitian_tolerance=hermitian_tolerance,
        )
        measurements["standard_reader_coulomb"] = standard_measurements
        gates.append(
            _gate(
                "standard_reader_coulomb",
                "PASS",
                "the ordinary reader-v1 Coulomb metric is recorded for comparison only",
                [standard_reader_path, response_path],
                measurements={
                    "comparable_dimensions": standard_measurements["comparable_dimensions"],
                    "relative_difference": standard_measurements.get(
                        "relative_error_to_response_metric"
                    ),
                },
            )
        )
    elif standard_reader_error is not None:
        measurements["standard_reader_coulomb"] = {
            "present": True,
            "path": str(standard_reader_path),
            "role": "diagnostic_only",
            "read_error": standard_reader_error,
        }
    else:
        measurements["standard_reader_coulomb"] = {"present": False}

    max_hermitian = max(
        measurements["response_metric_hermitian_relative_residual"],
        measurements["comparison_metric_hermitian_relative_residual"],
    )
    if max_hermitian > hermitian_tolerance:
        gates.append(
            _gate(
                "hermiticity",
                "FAIL",
                "the response metric or optional grid diagnostic exceeds the Hermiticity tolerance",
                evidence,
                repair="audit the Sternheimer Coulomb producer",
                measurements={"maximum_relative_residual": max_hermitian},
            )
        )
        return {
            "ok": False,
            "status": "NUMERICAL_FAIL",
            "root": str(directory),
            "iq": iq,
            "gates": gates,
            "measurements": measurements,
        }
    gates.append(
        _gate(
            "hermiticity",
            "PASS",
            "the response metric and optional grid diagnostic satisfy the Hermiticity tolerance",
            evidence,
        )
    )
    if (
        measurements["response_metric_eigenvalue_min"] < -hermitian_tolerance
        or measurements["comparison_metric_negative_eigenvalues"]
    ):
        gates.append(
            _gate(
                "positive_semidefinite",
                "FAIL",
                "the response metric or optional grid diagnostic is not positive semidefinite",
                evidence,
                repair="audit the Sternheimer Coulomb producer before response calculation",
            )
        )
        return {
            "ok": False,
            "status": "NUMERICAL_FAIL",
            "root": str(directory),
            "iq": iq,
            "gates": gates,
            "measurements": measurements,
        }
    gates.append(
        _gate(
            "positive_semidefinite",
            "PASS",
            "the response metric and optional grid diagnostic are positive semidefinite",
            evidence,
        )
    )
    relative_difference = measurements["relative_error_to_response_metric"]
    if grid is not None and relative_difference > metric_relative_tolerance:
        gates.append(
            _gate(
                "representation_consistency",
                "FAIL",
                "the dedicated response metric does not reproduce the grid-Poisson diagnostic",
                [response_path, grid_path],
                repair=(
                    "block response production until ABACUS writes the Coulomb metric used by "
                    "the Sternheimer perturbations"
                ),
                measurements={
                    "relative_difference": relative_difference,
                    "tolerance": metric_relative_tolerance,
                },
            )
        )
        return {
            "ok": False,
            "status": "CONTRACT_FAIL",
            "root": str(directory),
            "iq": iq,
            "gates": gates,
            "measurements": measurements,
        }
    gates.append(
        _gate(
            "representation_consistency",
            "PASS",
            (
                "the dedicated response metric reproduces the grid-Poisson diagnostic"
                if grid is not None
                else "the dedicated response metric satisfies the v1 handoff contract"
            ),
            [response_path, *([grid_path] if grid is not None else [])],
            measurements={
                "relative_difference": relative_difference,
                "tolerance": metric_relative_tolerance,
                "grid_diagnostic_present": grid is not None,
            },
        )
    )
    return {
        "ok": True,
        "status": "EVALUATED",
        "root": str(directory),
        "iq": iq,
        "gates": gates,
        "measurements": measurements,
    }


def inspect_sternheimer_comparison(
    root: str | Path,
    *,
    iq: int,
    ifreq: int,
    sqrt_coulomb_threshold: float = 0.0,
    hermitian_tolerance: float = 1.0e-10,
    reconstruction_tolerance: float = 1.0e-8,
    metric_relative_tolerance: float = 1.0e-6,
) -> dict[str, Any]:
    if iq <= 0 or ifreq <= 0:
        raise SternheimerDiagnosticError("iq and ifreq must be positive")
    for label, value in {
        "sqrt_coulomb_threshold": sqrt_coulomb_threshold,
        "hermitian_tolerance": hermitian_tolerance,
        "reconstruction_tolerance": reconstruction_tolerance,
        "metric_relative_tolerance": metric_relative_tolerance,
    }.items():
        if not math.isfinite(value) or value < 0.0:
            raise SternheimerDiagnosticError(f"{label} must be finite and non-negative")

    directory = Path(root).expanduser().resolve()
    paths = {
        "coulomb": directory / f"v1_sternheimer_coulomb_iq_{iq}_rank0.dat",
        "delta": directory / f"v1_sternheimer_chi0_iq_{iq}_ifreq_{ifreq}_rank0.dat",
        "lcao_sos": directory / f"v1_sternheimer_lcao_sos_iq_{iq}_ifreq_{ifreq}_rank0.dat",
        "in_sos": directory / f"v1_sternheimer_delta_in_sos_iq_{iq}_ifreq_{ifreq}_rank0.dat",
        "in_pulay": directory / f"v1_sternheimer_delta_in_pulay_iq_{iq}_ifreq_{ifreq}_rank0.dat",
        "out_grid": directory / f"v1_sternheimer_delta_out_grid_iq_{iq}_ifreq_{ifreq}_rank0.dat",
    }
    standard_reader_path = directory / f"v1_coulomb_full_iq_{iq}_rank0.dat"
    grid_coulomb_path = directory / "STERNHEIMER_GRID_COULOMB.dat"
    missing = [path for path in paths.values() if not path.is_file()]
    if missing:
        return {
            "ok": False,
            "status": "INCOMPLETE",
            "root": str(directory),
            "iq": iq,
            "ifreq": ifreq,
            "gates": [
                _gate(
                    "files",
                    "FAIL",
                    "required same-state Sternheimer diagnostic files are missing",
                    missing,
                    repair="rerun the pinned producer with LCAO-SOS and Delta component diagnostics enabled",
                )
            ],
        }

    try:
        matrices = {
            name: _read_block_matrix(path, response=name != "coulomb")
            for name, path in paths.items()
        }
        grid_coulomb = (
            _read_grid_coulomb(grid_coulomb_path)
            if grid_coulomb_path.is_file()
            else None
        )
    except (OSError, SternheimerDiagnosticError) as exc:
        format_paths = list(paths.values())
        if grid_coulomb_path.is_file():
            format_paths.append(grid_coulomb_path)
        return {
            "ok": False,
            "status": "CONTRACT_FAIL",
            "root": str(directory),
            "iq": iq,
            "ifreq": ifreq,
            "gates": [
                _gate(
                    "format",
                    "FAIL",
                    str(exc),
                    format_paths,
                    repair="regenerate the diagnostic family with the pinned reader-v1 producer",
                )
            ],
        }

    standard_reader = None
    standard_reader_error = None
    if standard_reader_path.is_file():
        try:
            standard_reader = _read_block_matrix(standard_reader_path, response=False)
        except (OSError, SternheimerDiagnosticError) as exc:
            standard_reader_error = str(exc)

    gates = [
        _gate(
            "files",
            "PASS",
            "all same-state Sternheimer diagnostic files are present",
            list(paths.values()),
        )
    ]
    coulomb_meta = matrices["coulomb"].metadata
    response_names = ("delta", "lcao_sos", "in_sos", "in_pulay", "out_grid")
    response_meta = matrices["delta"].metadata
    metadata_paths = list(paths.values())
    if grid_coulomb is not None:
        metadata_paths.append(grid_coulomb_path)
    common_response_keys = ("iq", "ifreq", "naux", "natoms", "atom_naux", "omega", "weight")
    metadata_match = (
        coulomb_meta["iq"] == iq
        and coulomb_meta["naux"] == response_meta["naux"]
        and coulomb_meta["natoms"] == response_meta["natoms"]
        and coulomb_meta["atom_naux"] == response_meta["atom_naux"]
        and all(
            all(matrices[name].metadata[key] == response_meta[key] for key in common_response_keys)
            for name in response_names
        )
        and (grid_coulomb is None or grid_coulomb.shape == matrices["coulomb"].values.shape)
    )
    if not metadata_match:
        gates.append(
            _gate(
                "metadata",
                "FAIL",
                "the response metric and response diagnostics do not describe one q/frequency state",
                metadata_paths,
                repair="regenerate all comparison matrices in one immutable producer attempt",
            )
        )
        return {
            "ok": False,
            "status": "CONTRACT_FAIL",
            "root": str(directory),
            "iq": iq,
            "ifreq": ifreq,
            "gates": gates,
        }
    gates.append(
        _gate(
            "metadata",
            "PASS",
            "the response metric and response diagnostics share q, frequency, dimensions, and weights",
            metadata_paths,
        )
    )

    hermitian_residuals = {
        name: _hermitian_residual(matrix.values) for name, matrix in matrices.items()
    }
    max_hermitian = max(hermitian_residuals.values())
    if max_hermitian > hermitian_tolerance:
        gates.append(
            _gate(
                "hermiticity",
                "FAIL",
                "at least one diagnostic matrix exceeds the Hermiticity tolerance",
                list(paths.values()),
                repair="inspect producer accumulation and reader-v1 block reconstruction",
                measurements={"maximum_relative_residual": max_hermitian},
            )
        )
        return {
            "ok": False,
            "status": "NUMERICAL_FAIL",
            "root": str(directory),
            "iq": iq,
            "ifreq": ifreq,
            "gates": gates,
        }
    gates.append(
        _gate(
            "hermiticity",
            "PASS",
            "all diagnostic matrices satisfy the Hermiticity tolerance",
            list(paths.values()),
            measurements={"relative_residuals": hermitian_residuals},
        )
    )

    values = {
        name: 0.5 * (matrix.values + matrix.values.conj().T)
        for name, matrix in matrices.items()
    }
    coulomb_eigenvalues, coulomb_eigenvectors = np.linalg.eigh(values["coulomb"])
    negative_coulomb = int(np.sum(coulomb_eigenvalues < -hermitian_tolerance))
    if negative_coulomb:
        gates.append(
            _gate(
                "coulomb_positive_semidefinite",
                "FAIL",
                "the full Coulomb matrix has negative eigenvalues",
                [paths["coulomb"]],
                repair="audit the full Coulomb producer before interpreting response matrices",
                measurements={"negative_eigenvalues": negative_coulomb},
            )
        )
        return {
            "ok": False,
            "status": "NUMERICAL_FAIL",
            "root": str(directory),
            "iq": iq,
            "ifreq": ifreq,
            "gates": gates,
        }
    gates.append(
        _gate(
            "coulomb_positive_semidefinite",
            "PASS",
            "the full Coulomb matrix is positive semidefinite",
            [paths["coulomb"]],
            measurements={
                "eigenvalue_min": float(coulomb_eigenvalues[0]),
                "eigenvalue_max": float(coulomb_eigenvalues[-1]),
            },
        )
    )

    reconstructed = values["in_sos"] + values["in_pulay"] + values["out_grid"]
    reconstruction_error = _relative_norm(values["delta"] - reconstructed, values["delta"])
    if reconstruction_error > reconstruction_tolerance:
        gates.append(
            _gate(
                "component_reconstruction",
                "FAIL",
                "Delta component matrices do not reconstruct the total response",
                [paths[name] for name in ("delta", "in_sos", "in_pulay", "out_grid")],
                repair="audit Delta component accumulation before changing physical inputs",
                measurements={"relative_error": reconstruction_error},
            )
        )
        return {
            "ok": False,
            "status": "NUMERICAL_FAIL",
            "root": str(directory),
            "iq": iq,
            "ifreq": ifreq,
            "gates": gates,
        }
    gates.append(
        _gate(
            "component_reconstruction",
            "PASS",
            "Delta in-SOS, Pulay, and out-grid matrices reconstruct the total response",
            [paths[name] for name in ("delta", "in_sos", "in_pulay", "out_grid")],
            measurements={"relative_error": reconstruction_error},
        )
    )

    component_norms = {
        name: float(np.linalg.norm(values[name])) for name in ("in_sos", "in_pulay", "out_grid")
    }
    lcao_norm = max(float(np.linalg.norm(values["lcao_sos"])), 1.0e-300)
    pulay_plus_out_grid = values["in_pulay"] + values["out_grid"]
    trace_log = {
        name: _trace_log(
            coulomb_eigenvalues,
            coulomb_eigenvectors,
            values[name],
            sqrt_coulomb_threshold,
        )
        for name in response_names
    }
    grid_coulomb_measurements: dict[str, Any] = {"present": False}
    if grid_coulomb is not None:
        grid_coulomb_measurements = {
            "present": True,
            "path": str(grid_coulomb_path),
            **_coulomb_metric_comparison(
                values["coulomb"],
                grid_coulomb,
                sqrt_coulomb_threshold=sqrt_coulomb_threshold,
                hermitian_tolerance=hermitian_tolerance,
                responses={name: values[name] for name in response_names},
            ),
        }
    standard_reader_measurements: dict[str, Any] = {"present": False}
    if standard_reader is not None:
        standard_reader_measurements = _standard_reader_measurements(
            matrices["coulomb"],
            standard_reader,
            sqrt_coulomb_threshold=sqrt_coulomb_threshold,
            hermitian_tolerance=hermitian_tolerance,
        )
        gates.append(
            _gate(
                "standard_reader_coulomb",
                "PASS",
                "the ordinary reader-v1 Coulomb metric is recorded for comparison only",
                [standard_reader_path, paths["coulomb"]],
                measurements={
                    "comparable_dimensions": standard_reader_measurements[
                        "comparable_dimensions"
                    ],
                    "relative_difference": standard_reader_measurements.get(
                        "relative_error_to_response_metric"
                    ),
                },
            )
        )
    elif standard_reader_error is not None:
        standard_reader_measurements = {
            "present": True,
            "path": str(standard_reader_path),
            "role": "diagnostic_only",
            "read_error": standard_reader_error,
        }
    measurements = {
        "matrix_dimension": int(response_meta["naux"]),
        "omega_ha": float(response_meta["omega"]),
        "weight_ha": float(response_meta["weight"]),
        "sqrt_coulomb_threshold": float(sqrt_coulomb_threshold),
        "component_reconstruction_relative_error": reconstruction_error,
        "delta_vs_lcao_relative_error": _relative_norm(
            values["delta"] - values["lcao_sos"], values["lcao_sos"]
        ),
        "delta_to_lcao_norm_ratio": float(
            np.linalg.norm(values["delta"]) / lcao_norm
        ),
        "in_sos_vs_lcao_relative_error": _relative_norm(
            values["in_sos"] - values["lcao_sos"], values["lcao_sos"]
        ),
        "matrix_norms": {name: float(np.linalg.norm(values[name])) for name in response_names},
        "component_norms": component_norms,
        "component_to_lcao_norm_ratios": {
            **{name: norm / lcao_norm for name, norm in component_norms.items()},
            "pulay_plus_out_grid": float(np.linalg.norm(pulay_plus_out_grid)) / lcao_norm,
        },
        "dominant_delta_component": max(component_norms, key=component_norms.get),
        "trace_log": trace_log,
        "grid_coulomb": grid_coulomb_measurements,
        "standard_reader_coulomb": standard_reader_measurements,
    }
    if grid_coulomb is not None:
        relative_difference = grid_coulomb_measurements["relative_error_to_response_metric"]
        if relative_difference > metric_relative_tolerance:
            gates.append(
                _gate(
                    "representation_consistency",
                    "FAIL",
                    "the dedicated response metric does not reproduce the grid-Poisson diagnostic",
                    [paths["coulomb"], grid_coulomb_path],
                    repair=(
                        "block downstream interpretation until ABACUS writes the Coulomb metric "
                        "used by the Sternheimer perturbations"
                    ),
                    measurements={
                        "relative_difference": relative_difference,
                        "tolerance": metric_relative_tolerance,
                    },
                )
            )
            return {
                "ok": False,
                "status": "CONTRACT_FAIL",
                "root": str(directory),
                "iq": iq,
                "ifreq": ifreq,
                "gates": gates,
                "measurements": measurements,
            }
        gates.append(
            _gate(
                "representation_consistency",
                "PASS",
                "the dedicated response metric reproduces the grid-Poisson diagnostic",
                [paths["coulomb"], grid_coulomb_path],
                measurements={
                    "relative_difference": relative_difference,
                    "tolerance": metric_relative_tolerance,
                },
            )
        )
    return {
        "ok": True,
        "status": "EVALUATED",
        "root": str(directory),
        "iq": iq,
        "ifreq": ifreq,
        "gates": gates,
        "measurements": measurements,
    }
