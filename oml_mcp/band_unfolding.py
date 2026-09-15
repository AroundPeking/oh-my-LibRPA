"""NAO translation-projector unfolding for exact diagonal supercells.

This module is intentionally narrower than a general band-unfolding package.
It supports exact periodic repetitions of a single-element cell with diagonal
integer supercell factors, an atom-contiguous equal-size NAO basis, and
nonmagnetic complex-LCAO ABACUS wavefunctions without SOC.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


HA2EV = 27.211386245988
RY2EV = HA2EV / 2.0


@dataclass(frozen=True)
class TranslationMap:
    """Atom permutation and boundary shifts for one primitive translation."""

    translation: tuple[int, int, int]
    target_atoms: np.ndarray
    cell_shifts: np.ndarray


@dataclass(frozen=True)
class OverlapRecords:
    """Sparse real-space overlap records read from an ABACUS CSR file."""

    dimension: int
    records: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]


def _diagonal_factors(factors: Sequence[int]) -> np.ndarray:
    raw = np.asarray(factors)
    integer = np.asarray(factors, dtype=int)
    if (
        raw.shape != (3,)
        or integer.shape != (3,)
        or np.any(integer <= 0)
        or not np.all(raw == integer)
    ):
        raise ValueError(
            "positive integer diagonal supercell factors must have length three"
        )
    return integer


def folded_primitive_points(
    supercell_k: Sequence[float],
    factors: Sequence[int],
) -> list[tuple[tuple[int, int, int], np.ndarray]]:
    """Return all primitive momenta represented by a supercell momentum."""

    supercell_k_array = np.asarray(supercell_k, dtype=float)
    diagonal_factors = _diagonal_factors(factors)
    if supercell_k_array.shape != (3,) or not np.isfinite(supercell_k_array).all():
        raise ValueError("supercell_k must contain three finite coordinates")

    result = []
    for sector in itertools.product(
        *(range(int(value)) for value in diagonal_factors)
    ):
        primitive_k = np.mod(
            (supercell_k_array + np.asarray(sector)) / diagonal_factors,
            1.0,
        )
        result.append((sector, primitive_k))
    return result


def _periodic_distance(first: np.ndarray, second: np.ndarray) -> float:
    delta = first - second
    delta -= np.rint(delta)
    return float(np.linalg.norm(delta))


def primitive_translation_maps(
    positions: Sequence[Sequence[float]],
    species: Sequence[str],
    factors: Sequence[int],
    *,
    tolerance: float = 1.0e-8,
) -> list[TranslationMap]:
    """Build primitive-translation matrices from the supercell structure.

    Coordinates are fractional in the supercell lattice. For every finite-group
    translation, each atom must map uniquely to a same-species atom.
    """

    positions_array = np.mod(np.asarray(positions, dtype=float), 1.0)
    diagonal_factors = _diagonal_factors(factors)
    if positions_array.ndim != 2 or positions_array.shape[1] != 3:
        raise ValueError("positions must have shape (natom, 3)")
    if not np.isfinite(positions_array).all():
        raise ValueError("positions must be finite")
    if len(species) != len(positions_array):
        raise ValueError("species and positions have inconsistent lengths")
    if tolerance <= 0.0 or not math.isfinite(tolerance):
        raise ValueError("translation matching tolerance must be positive and finite")

    maps = []
    for translation in itertools.product(
        *(range(int(value)) for value in diagonal_factors)
    ):
        shift_fractional = np.asarray(translation, dtype=float) / diagonal_factors
        target_atoms = np.empty(len(positions_array), dtype=int)
        cell_shifts = np.empty((len(positions_array), 3), dtype=int)
        for source, (position, source_species) in enumerate(
            zip(positions_array, species, strict=True)
        ):
            unwrapped = position + shift_fractional
            cell_shift = np.floor(unwrapped + tolerance).astype(int)
            wrapped = np.mod(unwrapped, 1.0)
            candidates = [
                index
                for index, target_species in enumerate(species)
                if target_species == source_species
                and _periodic_distance(positions_array[index], wrapped) < tolerance
            ]
            if len(candidates) != 1:
                raise ValueError(
                    f"translation {translation} maps atom {source} "
                    f"to {len(candidates)} candidates"
                )
            target_atoms[source] = candidates[0]
            cell_shifts[source] = cell_shift
        if sorted(target_atoms.tolist()) != list(range(len(positions_array))):
            raise ValueError(f"translation {translation} is not an atom permutation")
        maps.append(
            TranslationMap(
                translation=tuple(int(value) for value in translation),
                target_atoms=target_atoms,
                cell_shifts=cell_shifts,
            )
        )
    return maps


def apply_translation(
    coefficients: np.ndarray,
    mapping: TranslationMap,
    supercell_k: Sequence[float],
    orbitals_per_atom: int,
) -> np.ndarray:
    """Apply one structure-derived translation to row-major NAO states."""

    original = np.asarray(coefficients, dtype=np.complex128)
    is_vector = original.ndim == 1
    rows = original[np.newaxis, :] if is_vector else original
    natoms = len(mapping.target_atoms)
    supercell_k_array = np.asarray(supercell_k, dtype=float)
    if (
        rows.ndim != 2
        or orbitals_per_atom <= 0
        or rows.shape[1] != natoms * orbitals_per_atom
    ):
        raise ValueError("coefficient dimension does not match equal per-atom NAO layout")
    if supercell_k_array.shape != (3,):
        raise ValueError("supercell_k must have length three")

    translated = np.empty_like(rows)
    for source, target in enumerate(mapping.target_atoms):
        phase = np.exp(
            -2j * math.pi * np.dot(supercell_k_array, mapping.cell_shifts[source])
        )
        source_slice = slice(
            source * orbitals_per_atom,
            (source + 1) * orbitals_per_atom,
        )
        target_slice = slice(
            target * orbitals_per_atom,
            (target + 1) * orbitals_per_atom,
        )
        translated[:, target_slice] = phase * rows[:, source_slice]
    return translated[0] if is_vector else translated


def translation_expectations(
    coefficients: np.ndarray,
    overlap: np.ndarray,
    supercell_k: Sequence[float],
    mappings: Sequence[TranslationMap],
    orbitals_per_atom: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return norms and all overlap-metric translation expectations."""

    state_coefficients = np.asarray(coefficients, dtype=np.complex128)
    if state_coefficients.ndim == 1:
        state_coefficients = state_coefficients[np.newaxis, :]
    overlap_matrix = np.asarray(overlap, dtype=np.complex128)
    if overlap_matrix.shape != (
        state_coefficients.shape[1],
        state_coefficients.shape[1],
    ):
        raise ValueError("overlap and coefficient dimensions do not match")

    overlap_states = (overlap_matrix @ state_coefficients.T).T
    complex_norms = np.sum(
        np.conjugate(state_coefficients) * overlap_states,
        axis=1,
    )
    if np.max(np.abs(complex_norms.imag), initial=0.0) > 1.0e-8:
        raise ValueError("wavefunction norms have a significant imaginary component")
    norms = complex_norms.real
    if np.any(~np.isfinite(norms)) or np.any(norms <= 0.0):
        raise ValueError("wavefunction norms must be finite and positive")

    expectations = np.empty(
        (len(state_coefficients), len(mappings)),
        dtype=np.complex128,
    )
    for index, mapping in enumerate(mappings):
        translated = apply_translation(
            state_coefficients,
            mapping,
            supercell_k,
            orbitals_per_atom,
        )
        expectations[:, index] = np.sum(
            np.conjugate(overlap_states) * translated,
            axis=1,
        )
    return norms, expectations


def projector_weights_from_expectations(
    expectations: np.ndarray,
    norms: np.ndarray,
    primitive_points: Iterable[Sequence[float]],
    mappings: Sequence[TranslationMap],
) -> np.ndarray:
    """Evaluate primitive-sector weights from translation expectations."""

    translations = np.asarray(
        [mapping.translation for mapping in mappings],
        dtype=float,
    )
    point_array = np.asarray(list(primitive_points), dtype=float)
    if point_array.ndim != 2 or point_array.shape[1] != 3:
        raise ValueError("primitive_points must have shape (npoint, 3)")
    characters = np.exp(2j * math.pi * point_array @ translations.T)
    weights = (np.asarray(expectations) @ characters.T) / len(mappings)
    weights = weights / np.asarray(norms)[:, np.newaxis]
    if np.max(np.abs(weights.imag), initial=0.0) > 5.0e-7:
        raise ValueError("projector weights have a significant imaginary component")
    return weights.real


def projector_weights(
    coefficients: np.ndarray,
    overlap: np.ndarray,
    supercell_k: Sequence[float],
    primitive_points: Iterable[Sequence[float]],
    mappings: Sequence[TranslationMap],
    orbitals_per_atom: int,
) -> np.ndarray:
    """Return all requested primitive-sector weights for every state."""

    norms, expectations = translation_expectations(
        coefficients,
        overlap,
        supercell_k,
        mappings,
        orbitals_per_atom,
    )
    return projector_weights_from_expectations(
        expectations,
        norms,
        primitive_points,
        mappings,
    )


def projector_weight(
    coefficients: np.ndarray,
    overlap: np.ndarray,
    supercell_k: Sequence[float],
    primitive_k: Sequence[float],
    mappings: Sequence[TranslationMap],
    orbitals_per_atom: int,
) -> float:
    """Return one state's spectral weight in one primitive momentum sector."""

    weights = projector_weights(
        coefficients,
        overlap,
        supercell_k,
        [primitive_k],
        mappings,
        orbitals_per_atom,
    )
    return float(weights[0, 0])


def read_overlap_records(path: str | Path) -> OverlapRecords:
    """Read nonempty records from an ABACUS text CSR overlap file."""

    file_path = Path(path)
    with file_path.open("r", encoding="ascii") as handle:
        step_line = handle.readline()
        dimension_line = handle.readline()
        count_line = handle.readline()
        if not step_line.startswith("STEP:"):
            raise ValueError(f"not an ABACUS CSR matrix file: {file_path}")
        try:
            dimension = int(dimension_line.split()[-1])
            record_count = int(count_line.split()[-1])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"invalid CSR header in {file_path}") from exc
        if dimension <= 0 or record_count < 0:
            raise ValueError(f"invalid CSR dimensions in {file_path}")

        records = []
        for _ in range(record_count):
            header = handle.readline().split()
            if len(header) != 4:
                raise ValueError(f"invalid CSR R-record header in {file_path}")
            real_space_cell = np.asarray(
                [int(value) for value in header[:3]],
                dtype=int,
            )
            nonzero_count = int(header[3])
            if nonzero_count < 0:
                raise ValueError(f"negative CSR record size in {file_path}")
            if nonzero_count == 0:
                continue
            values = np.fromstring(handle.readline(), sep=" ", dtype=float)
            columns = np.fromstring(handle.readline(), sep=" ", dtype=int)
            row_pointer = np.fromstring(handle.readline(), sep=" ", dtype=int)
            if (
                len(values) != nonzero_count
                or len(columns) != nonzero_count
                or len(row_pointer) != dimension + 1
                or row_pointer[0] != 0
                or row_pointer[-1] != nonzero_count
                or np.any(columns < 0)
                or np.any(columns >= dimension)
            ):
                raise ValueError(
                    f"inconsistent CSR record for R={real_space_cell} "
                    f"in {file_path}"
                )
            records.append(
                (real_space_cell, values, columns, row_pointer)
            )
    return OverlapRecords(dimension=dimension, records=records)


def fourier_overlap(
    records: OverlapRecords,
    supercell_k: Sequence[float],
) -> np.ndarray:
    """Fourier transform S(R) using the ABACUS positive phase convention."""

    supercell_k_array = np.asarray(supercell_k, dtype=float)
    if supercell_k_array.shape != (3,) or not np.isfinite(supercell_k_array).all():
        raise ValueError("supercell_k must contain three finite coordinates")
    result = np.zeros(
        (records.dimension, records.dimension),
        dtype=np.complex128,
    )
    for real_space_cell, values, columns, row_pointer in records.records:
        phase = np.exp(
            2j * math.pi * np.dot(supercell_k_array, real_space_cell)
        )
        for row in range(records.dimension):
            begin, end = row_pointer[row], row_pointer[row + 1]
            result[row, columns[begin:end]] += phase * values[begin:end]
    return result


def build_overlap_k(
    path: str | Path,
    supercell_k: Sequence[float],
) -> np.ndarray:
    """Read an ABACUS S(R) CSR file and construct S(K)."""

    return fourier_overlap(read_overlap_records(path), supercell_k)


def _read_exact(handle, byte_count: int, *, label: str, path: Path) -> bytes:
    data = handle.read(byte_count)
    if len(data) != byte_count:
        raise ValueError(f"truncated {label} in {path}")
    return data


def read_abacus_wfc_binary(
    path: str | Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Read one complex wfs1k*_nao.dat file written by ABACUS."""

    file_path = Path(path)
    with file_path.open("rb") as handle:
        point_index = struct.unpack(
            "=i",
            _read_exact(handle, 4, label="k-point index", path=file_path),
        )[0]
        supercell_k = np.frombuffer(
            _read_exact(handle, 24, label="k-point", path=file_path),
            dtype=np.float64,
        ).copy()
        band_count = struct.unpack(
            "=i",
            _read_exact(handle, 4, label="band count", path=file_path),
        )[0]
        basis_count = struct.unpack(
            "=i",
            _read_exact(handle, 4, label="basis count", path=file_path),
        )[0]
        if point_index < 1 or band_count <= 0 or basis_count <= 0:
            raise ValueError(f"invalid wavefunction header in {file_path}")

        eigenvalues_ry = np.empty(band_count, dtype=float)
        occupations = np.empty(band_count, dtype=float)
        coefficients = np.empty(
            (band_count, basis_count),
            dtype=np.complex128,
        )
        for band in range(band_count):
            band_index = struct.unpack(
                "=i",
                _read_exact(handle, 4, label="band index", path=file_path),
            )[0]
            if band_index != band + 1:
                raise ValueError(f"unexpected band index in {file_path}")
            energy_occupation = np.frombuffer(
                _read_exact(
                    handle,
                    16,
                    label="band energy and occupation",
                    path=file_path,
                ),
                dtype=np.float64,
            )
            eigenvalues_ry[band], occupations[band] = energy_occupation
            raw = np.frombuffer(
                _read_exact(
                    handle,
                    16 * basis_count,
                    label="wavefunction coefficients",
                    path=file_path,
                ),
                dtype=np.float64,
            )
            coefficients[band] = raw[0::2] + 1j * raw[1::2]
        if handle.read(1):
            raise ValueError(f"unexpected trailing bytes in {file_path}")

    return supercell_k, eigenvalues_ry, occupations, coefficients


def resolve_abacus_wfc_binary(
    output_directory: str | Path,
    point_index: int,
) -> Path:
    """Resolve current or legacy ABACUS complex-LCAO wavefunction names."""

    root = Path(output_directory)
    candidates = (
        root / f"wfs1k{point_index}_nao.dat",
        root / f"wfk{point_index}_nao.dat",
    )
    matches = [candidate for candidate in candidates if candidate.is_file()]
    if len(matches) != 1:
        raise FileNotFoundError(
            f"expected one binary wavefunction for k={point_index}, "
            f"found {matches}"
        )
    return matches[0]


def read_kpt_info_direct(path: str | Path) -> np.ndarray:
    """Read sequential Direct-coordinate points from ABACUS KPT.info."""

    file_path = Path(path)
    lines = file_path.read_text(encoding="ascii").splitlines()
    if not any("DIRECT COORDINATES" in line.upper() for line in lines):
        raise ValueError("only Direct-coordinate KPT.info files are supported")
    points = []
    for line in lines:
        fields = line.split()
        if len(fields) < 5:
            continue
        try:
            point_index = int(fields[0])
            point = [float(value) for value in fields[1:4]]
            float(fields[4])
        except ValueError:
            continue
        if point_index != len(points) + 1:
            raise ValueError(f"nonsequential k-point index in {file_path}")
        points.append(point)
    if not points:
        raise ValueError(f"no Direct-coordinate k points found in {file_path}")
    return np.asarray(points, dtype=float)


def read_stru_positions(path: str | Path) -> tuple[list[str], np.ndarray]:
    """Read atom labels and Direct fractional positions from a STRU file."""

    file_path = Path(path)
    lines = [
        line.split("#", 1)[0].strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
    ]
    lines = [line for line in lines if line]
    try:
        start = lines.index("ATOMIC_POSITIONS")
    except ValueError as exc:
        raise ValueError("STRU has no ATOMIC_POSITIONS section") from exc
    if start + 1 >= len(lines) or lines[start + 1].lower() != "direct":
        raise ValueError("only Direct-coordinate STRU files are supported")

    cursor = start + 2
    species = []
    positions = []
    while cursor < len(lines):
        label = lines[cursor]
        cursor += 1
        if cursor + 1 >= len(lines):
            raise ValueError(f"truncated atomic block in {file_path}")
        cursor += 1  # starting magnetization
        try:
            atom_count = int(lines[cursor].split()[0])
        except ValueError as exc:
            raise ValueError(f"invalid atom count in {file_path}") from exc
        cursor += 1
        if cursor + atom_count > len(lines):
            raise ValueError(f"truncated atomic coordinates in {file_path}")
        for _ in range(atom_count):
            fields = lines[cursor].split()
            if len(fields) < 3:
                raise ValueError(f"invalid atomic coordinate in {file_path}")
            positions.append([float(value) for value in fields[:3]])
            species.append(label)
            cursor += 1
    return species, np.asarray(positions, dtype=float)


def read_path_table(path: str | Path) -> list[dict[str, str]]:
    """Read a primitive/supercell path mapping CSV."""

    with Path(path).open("r", newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    required = {"distance", "kx", "ky", "kz", "Kx", "Ky", "Kz"}
    if not rows:
        raise ValueError("path table is empty")
    if not required.issubset(rows[0]):
        raise ValueError(
            "path table must contain distance, primitive k, and supercell K columns"
        )
    return rows


def _find_target_sector(
    sectors: Sequence[tuple[tuple[int, int, int], np.ndarray]],
    target: np.ndarray,
) -> int:
    distances = [
        np.linalg.norm((point - target) - np.rint(point - target))
        for _, point in sectors
    ]
    index = int(np.argmin(distances))
    if distances[index] > 1.0e-8:
        raise ValueError("target primitive k is absent from folded sectors")
    return index


def unfold_path(
    *,
    path_table: str | Path,
    stru: str | Path,
    overlap: str | Path,
    wfc_dir: str | Path,
    factors: Sequence[int],
    orbitals_per_atom: int,
    output: str | Path,
    summary: str | Path,
    kpt_info: str | Path | None = None,
    nspin: int = 1,
    lspinorb: bool = False,
) -> dict[str, float | int]:
    """Unfold one exact-supercell ABACUS path and write spectral weights."""

    if nspin != 1:
        raise ValueError("NAO unfolding currently supports only nspin=1")
    if lspinorb:
        raise ValueError("NAO unfolding currently does not support SOC")
    if orbitals_per_atom <= 0:
        raise ValueError("orbitals_per_atom must be a positive explicit value")

    rows = read_path_table(path_table)
    species, positions = read_stru_positions(stru)
    if len(set(species)) != 1:
        raise ValueError(
            "NAO unfolding currently requires a single-species supercell "
            "because the wavefunction binary has no per-atom NAO metadata"
        )
    diagonal_factors = _diagonal_factors(factors)
    mappings = primitive_translation_maps(
        positions,
        species,
        diagonal_factors,
    )
    expected_translation_count = int(np.prod(diagonal_factors))
    if len(mappings) != expected_translation_count:
        raise ValueError("translation-map count does not match supercell factors")

    overlap_records = read_overlap_records(overlap)
    wfc_root = Path(wfc_dir)
    kpt_path = Path(kpt_info) if kpt_info else wfc_root / "KPT.info"
    direct_kpoints = read_kpt_info_direct(kpt_path)
    if len(direct_kpoints) != len(rows):
        raise ValueError("path table and KPT.info have different point counts")

    expected_basis_count = len(positions) * orbitals_per_atom
    if overlap_records.dimension != expected_basis_count:
        raise ValueError(
            "overlap dimension does not match the explicit equal per-atom NAO layout"
        )

    output_rows: list[dict[str, object]] = []
    max_norm_error = 0.0
    max_sector_sum_error = 0.0
    min_projector_weight = math.inf
    max_projector_weight = -math.inf
    max_overlap_antihermitian = 0.0
    band_count: int | None = None

    for point_index, row in enumerate(rows, start=1):
        target_k = np.asarray(
            [float(row[name]) for name in ("kx", "ky", "kz")],
            dtype=float,
        )
        expected_supercell_k = np.asarray(
            [float(row[name]) for name in ("Kx", "Ky", "Kz")],
            dtype=float,
        )
        supercell_k = direct_kpoints[point_index - 1]
        if not np.allclose(
            np.mod(supercell_k, 1.0),
            np.mod(expected_supercell_k, 1.0),
            atol=1.0e-8,
        ):
            raise ValueError(
                f"KPT.info differs from path table at point {point_index}"
            )

        wfc_path = resolve_abacus_wfc_binary(wfc_root, point_index)
        wfc_k, eigenvalues_ry, occupations, coefficients = (
            read_abacus_wfc_binary(wfc_path)
        )
        if not np.allclose(
            np.mod(wfc_k, 1.0),
            np.mod(supercell_k, 1.0),
            atol=1.0e-8,
        ):
            raise ValueError(
                f"wavefunction header differs from KPT.info at point {point_index}"
            )
        if coefficients.shape[1] != expected_basis_count:
            raise ValueError(
                "wavefunction dimension does not match the explicit equal "
                "per-atom NAO layout"
            )
        if band_count is None:
            band_count = len(eigenvalues_ry)
        elif len(eigenvalues_ry) != band_count:
            raise ValueError("wavefunction band count changes along the path")

        overlap_k = fourier_overlap(overlap_records, supercell_k)
        antihermitian = float(
            np.max(np.abs(overlap_k - overlap_k.conjugate().T), initial=0.0)
        )
        norms, expectations = translation_expectations(
            coefficients,
            overlap_k,
            supercell_k,
            mappings,
            orbitals_per_atom,
        )
        sectors = folded_primitive_points(supercell_k, diagonal_factors)
        weights = projector_weights_from_expectations(
            expectations,
            norms,
            [point for _, point in sectors],
            mappings,
        )
        target_sector = _find_target_sector(sectors, target_k)

        max_norm_error = max(
            max_norm_error,
            float(np.max(np.abs(norms - 1.0), initial=0.0)),
        )
        max_sector_sum_error = max(
            max_sector_sum_error,
            float(
                np.max(
                    np.abs(np.sum(weights, axis=1) - 1.0),
                    initial=0.0,
                )
            ),
        )
        min_projector_weight = min(
            min_projector_weight,
            float(np.min(weights)),
        )
        max_projector_weight = max(
            max_projector_weight,
            float(np.max(weights)),
        )
        max_overlap_antihermitian = max(
            max_overlap_antihermitian,
            antihermitian,
        )

        for band in range(len(eigenvalues_ry)):
            strongest = int(np.argmax(weights[band]))
            output_rows.append(
                {
                    "point": point_index,
                    "distance": float(row["distance"]),
                    "band": band + 1,
                    "energy_eV": float(eigenvalues_ry[band] * RY2EV),
                    "occupation": float(occupations[band]),
                    "target_weight": float(weights[band, target_sector]),
                    "weight_sum": float(np.sum(weights[band])),
                    "norm": float(norms[band]),
                    "strongest_sector": ";".join(
                        str(value) for value in sectors[strongest][0]
                    ),
                    "strongest_weight": float(weights[band, strongest]),
                }
            )

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)

    result: dict[str, float | int] = {
        "n_path_points": len(rows),
        "n_bands": int(band_count or 0),
        "n_atoms": len(positions),
        "orbitals_per_atom": orbitals_per_atom,
        "n_translation_sectors": len(mappings),
        "max_norm_error": max_norm_error,
        "max_sector_sum_error": max_sector_sum_error,
        "min_projector_weight": min_projector_weight,
        "max_projector_weight": max_projector_weight,
        "max_overlap_antihermitian": max_overlap_antihermitian,
    }
    summary_path = Path(summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path-table", required=True)
    parser.add_argument("--stru", required=True)
    parser.add_argument("--overlap", required=True)
    parser.add_argument("--wfc-dir", required=True)
    parser.add_argument("--kpt-info")
    parser.add_argument("--factors", type=int, nargs=3, required=True)
    parser.add_argument("--orbitals-per-atom", type=int, required=True)
    parser.add_argument("--nspin", type=int, default=1)
    parser.add_argument("--lspinorb", action="store_true")
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = unfold_path(
        path_table=args.path_table,
        stru=args.stru,
        overlap=args.overlap,
        wfc_dir=args.wfc_dir,
        kpt_info=args.kpt_info,
        factors=args.factors,
        orbitals_per_atom=args.orbitals_per_atom,
        nspin=args.nspin,
        lspinorb=args.lspinorb,
        output=args.output,
        summary=args.summary,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
