"""Fast, reference-free Coulomb diagnostics for the periodic 3D GW path.

This module reads the ABACUS reader-v1 full-Coulomb matrix family and reports
whether each q block is (a) Hermitian to roundoff and (b) positive-semidefinite
relative to its own numerical scale. It deliberately does NOT reuse the
Sternheimer response metric machinery (which is gated behind a dedicated
response family) because the periodic 3D GW producer writes only the ordinary
``v1_coulomb_full_iq_*`` family. It reuses the same reader-v1 block-layout
contract so both paths agree on what a Coulomb v1 block means.

The gates are diagnostic-only and reference-free: an unproven matrix yields
NOT_EVALUATED, never a silent pass. A matrix that is Hermitian to roundoff and
has no materially negative eigenvalue passes; a matrix that is strongly
indefinite or non-Hermitian fails with a repair hint. The failure surface is
intentionally the same one the ``strict2d-direct-coulomb`` experience records:
never clip eigenvalues, never substitute cut Coulomb, and never let a bad
matrix ride through to GW.
"""

from __future__ import annotations

import math
import re
import struct
from pathlib import Path
from typing import Any

import numpy as np

from .models import GateResult

COULOMB_MARKER = -20129433

# Default relative tolerances. The Hermitian residual and the negative
# eigenvalue floor are both judged against the largest |eigenvalue| so that a
# large-norm matrix (many auxiliary functions) does not trip a scale-naive
# absolute threshold.
DEFAULT_HERMITIAN_RELATIVE_TOLERANCE = 1.0e-9
DEFAULT_NEGATIVE_EIGENVALUE_RELATIVE_FLOOR = 1.0e-8


def _pass(gate_id: str, message: str, *evidence: str) -> GateResult:
    return GateResult(gate_id, "PASS", message, tuple(evidence))


def _fail(gate_id: str, message: str, evidence: list[str], repair: str) -> GateResult:
    return GateResult(gate_id, "FAIL", message, tuple(evidence), repair)


def _block_pair(index: int, natoms: int) -> tuple[int, int]:
    """Map a reader-v1 Coulomb atom-pair index to the (first, second) atom pair."""
    remaining = index
    for first in range(natoms):
        row_size = natoms - first
        if remaining < row_size:
            return first, first + remaining
        remaining -= row_size
    raise ValueError(f"invalid atom-pair index {index}")


def read_coulomb_block(path: Path) -> dict[str, Any]:
    """Read one reader-v1 Coulomb block into a dense Hermitian matrix.

    Returns a dict with ``path``, ``metadata`` (header fields), and ``values``
    (a dense ``naux x naux`` complex matrix). Raises ``ValueError`` on a
    malformed block so the caller can attach a repair hint.
    """
    data = path.read_bytes()
    if len(data) < 24:
        raise ValueError("Coulomb v1 file is smaller than its header")
    marker, iq, naux, value_flag, natoms, nblocks = struct.unpack_from("=6i", data)
    if marker != COULOMB_MARKER:
        raise ValueError(f"Coulomb marker {marker} != expected {COULOMB_MARKER}")
    if iq <= 0 or naux <= 0 or natoms <= 0 or nblocks < 0:
        raise ValueError("Coulomb v1 header dimensions must be positive")
    if value_flag not in {0, 1}:
        raise ValueError(f"unsupported Coulomb v1 value flag {value_flag}")

    atom_naux = struct.unpack_from(f"={natoms}i", data, 24)
    if any(value <= 0 for value in atom_naux) or sum(atom_naux) != naux:
        raise ValueError("Coulomb v1 per-atom auxiliary sizes do not sum to naux")
    npairs = natoms * (natoms + 1) // 2
    if nblocks != npairs:
        raise ValueError(
            f"Coulomb v1 matrix has {nblocks} blocks but requires {npairs}"
        )

    table_end = 24 + 4 * natoms
    records = [
        struct.unpack_from("=iq", data, table_end + 12 * block)
        for block in range(nblocks)
    ]
    if len({pair for pair, _ in records}) != nblocks:
        raise ValueError("Coulomb v1 matrix has duplicate atom-pair blocks")

    offsets = np.cumsum((0, *atom_naux))
    matrix = np.zeros((naux, naux), dtype=np.complex128)
    dtype = np.dtype(np.complex128 if value_flag == 1 else np.float64)
    intervals: list[tuple[int, int]] = []
    for pair_index, byte_offset in records:
        first, second = _block_pair(pair_index, natoms)
        nfirst = atom_naux[first]
        nsecond = atom_naux[second]
        payload_bytes = nfirst * nsecond * dtype.itemsize
        if byte_offset < table_end or byte_offset + payload_bytes > len(data):
            raise ValueError(
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
            raise ValueError("Coulomb v1 matrix payload blocks overlap")
    if not np.isfinite(matrix).all():
        raise ValueError("Coulomb v1 matrix contains non-finite values")

    metadata = {
        "iq": iq,
        "naux": naux,
        "value_flag": value_flag,
        "natoms": natoms,
        "nblocks": nblocks,
        "atom_naux": tuple(int(value) for value in atom_naux),
    }
    return {"path": path, "metadata": metadata, "values": matrix}


def _hermitian_relative_residual(matrix: np.ndarray) -> float:
    norm = float(np.max(np.abs(matrix))) if matrix.size else 0.0
    if norm == 0.0:
        return 0.0
    return float(np.max(np.abs(matrix - matrix.conj().T))) / norm


def inspect_coulomb_psd_hermitian(
    root: str | Path,
    *,
    hermitian_relative_tolerance: float = DEFAULT_HERMITIAN_RELATIVE_TOLERANCE,
    negative_eigenvalue_relative_floor: float = DEFAULT_NEGATIVE_EIGENVALUE_RELATIVE_FLOOR,
) -> dict[str, Any]:
    """Run the PSD/Hermitian gate over every reader-v1 full-Coulomb q block.

    Returns a report dict with ``accepted``, ``status``, ``counts``, and a
    ``gates`` list. Missing families produce a FAIL gate with a repair hint.
    Unreadable or non-finite blocks produce a FAIL gate. A block that is
    Hermitian to roundoff and has no materially negative eigenvalue passes;
    otherwise it fails and never silently clips.
    """
    for label, value in {
        "hermitian_relative_tolerance": hermitian_relative_tolerance,
        "negative_eigenvalue_relative_floor": negative_eigenvalue_relative_floor,
    }.items():
        if not math.isfinite(value) or value < 0.0:
            raise ValueError(f"{label} must be finite and non-negative")

    directory = Path(root).expanduser().resolve()
    paths = sorted(directory.glob("v1_coulomb_full_iq_*_rank*.dat"))
    if not paths:
        return {
            "accepted": False,
            "status": "FAIL",
            "gate_id": "coulomb.psd_hermitian",
            "counts": {"PASS": 0, "WARN": 0, "FAIL": 1, "SKIP": 0},
            "gates": [
                _fail(
                    "coulomb.psd_hermitian",
                    "no reader-v1 full-Coulomb q blocks were found",
                    [str(directory)],
                    "regenerate the reader-v1 full Coulomb family with ABACUS "
                    "out_librpa_reader_version = 1",
                ).to_dict()
            ],
        }

    gates: list[GateResult] = []
    by_iq: dict[int, list[Path]] = {}
    for path in paths:
        # Normalize rank-0 versus multi-rank filenames to a single block per q.
        iq_match = re.search(r"_iq_(\d+)_rank", path.name)
        if not iq_match:
            continue
        iq = int(iq_match.group(1))
        by_iq.setdefault(iq, []).append(path)

    if not by_iq:
        return {
            "accepted": False,
            "status": "FAIL",
            "gate_id": "coulomb.psd_hermitian",
            "counts": {"PASS": 0, "WARN": 0, "FAIL": 1, "SKIP": 0},
            "gates": [
                _fail(
                    "coulomb.psd_hermitian",
                    "no Coulomb q block names matched the reader-v1 convention",
                    [str(directory)],
                    "regenerate the reader-v1 full Coulomb family with ABACUS "
                    "out_librpa_reader_version = 1",
                ).to_dict()
            ],
        }

    for iq in sorted(by_iq):
        # Prefer the rank-0 file for a given q; ignore other ranks.
        rank0 = next(
            (p for p in by_iq[iq] if "_rank0" in p.name),
            by_iq[iq][0],
        )
        gate_id = f"coulomb.psd_hermitian.iq_{iq}"
        try:
            block = read_coulomb_block(rank0)
        except (OSError, ValueError, struct.error) as exc:
            gates.append(
                _fail(
                    gate_id,
                    "Coulomb q block is malformed or unreadable",
                    [str(rank0), str(exc)],
                    "regenerate the reader-v1 full Coulomb family with ABACUS "
                    "out_librpa_reader_version = 1",
                )
            )
            continue

        matrix = block["values"]
        hermitian = _hermitian_relative_residual(matrix)
        hermitian_matrix = 0.5 * (matrix + matrix.conj().T)
        eigenvalues = np.linalg.eigvalsh(hermitian_matrix)
        largest = float(np.max(np.abs(eigenvalues))) if eigenvalues.size else 0.0
        floor = negative_eigenvalue_relative_floor * max(largest, 1.0)
        negative_count = int(np.sum(eigenvalues < -floor))
        min_eigenvalue = float(eigenvalues[0]) if eigenvalues.size else 0.0
        max_eigenvalue = float(eigenvalues[-1]) if eigenvalues.size else 0.0

        measurements = {
            "iq": iq,
            "naux": int(block["metadata"]["naux"]),
            "hermitian_relative_residual": hermitian,
            "eigenvalue_min": min_eigenvalue,
            "eigenvalue_max": max_eigenvalue,
            "negative_eigenvalue_count": negative_count,
            "negative_eigenvalue_relative_floor": floor,
            "largest_abs_eigenvalue": largest,
        }

        if not np.isfinite(matrix).all():
            gates.append(
                _fail(
                    gate_id,
                    "Coulomb q block contains non-finite values",
                    [str(rank0), "nan/inf detected"],
                    "regenerate the reader-v1 full Coulomb family with ABACUS "
                    "out_librpa_reader_version = 1",
                )
            )
            continue
        if hermitian > hermitian_relative_tolerance:
            gates.append(
                _fail(
                    gate_id,
                    "Coulomb q block is not Hermitian to roundoff",
                    [str(rank0), f"hermitian_relative_residual={hermitian:.3e}"],
                    "regenerate the reader-v1 full Coulomb family with ABACUS "
                    "out_librpa_reader_version = 1; check that symmetry and the "
                    "producer definition are not mixed",
                )
            )
            continue
        if negative_count > 0:
            gates.append(
                _fail(
                    gate_id,
                    "Coulomb q block is not positive-semidefinite",
                    [
                        str(rank0),
                        f"negative_eigenvalue_count={negative_count}",
                        f"eigenvalue_min={min_eigenvalue:.3e}",
                    ],
                    "do not clip eigenvalues or substitute cut Coulomb. If this is a "
                    "strict-2D full-Ewald case, switch to the direct_mixed_fourier "
                    "positive-Gram output; otherwise regenerate the reader-v1 full "
                    "Coulomb family and verify the auxiliary-basis and symmetry "
                    "definition before GW.",
                )
            )
            continue
        gates.append(
            _pass(
                gate_id,
                "Coulomb q block is Hermitian and positive-semidefinite",
                str(rank0),
                f"hermitian_relative_residual={hermitian:.3e}",
                f"eigenvalue_min={min_eigenvalue:.3e}",
            )
        )

    counts = {status: sum(gate.status == status for gate in gates) for status in ("PASS", "WARN", "FAIL", "SKIP")}
    accepted = counts["FAIL"] == 0
    return {
        "accepted": accepted,
        "status": "PASS" if accepted else "FAIL",
        "gate_id": "coulomb.psd_hermitian",
        "counts": counts,
        "gates": [gate.to_dict() for gate in gates],
    }
