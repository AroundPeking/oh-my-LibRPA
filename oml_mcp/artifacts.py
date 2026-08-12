from __future__ import annotations

import glob
import math
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .models import ArtifactInfo, GateResult
from .parsers import ParseError, parse_band_out, parse_k_path_info


EIGENVECTOR_MARKER = -12345679
EIGENVECTOR_KIND = 28
VELOCITY_MARKER = -12345680
VELOCITY_KIND = 29
COULOMB_MARKER = -20129433
CS_MARKER = -10267453
SHRINK_SINVS_MARKER = -30241621
COMPLEX_DOUBLE_BYTES = 16
BLOCK_RECORD_BYTES = 12


class ArtifactError(ValueError):
    """Raised internally when a scientific artifact violates its format."""


def _failure(path: Path, artifact_type: str, message: str, repair: str) -> ArtifactInfo:
    size = path.stat().st_size if path.exists() and path.is_file() else 0
    return ArtifactInfo(
        path=path,
        artifact_type=artifact_type,
        format_version="unknown",
        size=size,
        metadata={},
        gates=(
            GateResult(
                gate_id=f"{artifact_type}.format",
                status="FAIL",
                message=message,
                evidence=(str(path),),
                repair=repair,
            ),
        ),
    )


def _inspect_binary(
    path: str | Path,
    *,
    artifact_type: str,
    header_format: str,
    header_names: tuple[str, ...],
    expected_marker: int,
    expected_kind: int,
    block_size: Callable[[dict[str, int]], int],
    extra_validate: Callable[[dict[str, int]], None] | None = None,
) -> ArtifactInfo:
    file_path = Path(path).expanduser().resolve()
    repair = f"regenerate {artifact_type} with the pinned OML reader-v1 adapter"
    try:
        file_size = file_path.stat().st_size
        header_bytes = struct.calcsize(header_format)
        if file_size < header_bytes:
            raise ArtifactError("file is smaller than the reader-v1 header")
        with file_path.open("rb") as handle:
            values = struct.unpack(header_format, handle.read(header_bytes))
            metadata = dict(zip(header_names, values, strict=True))
            if metadata["marker"] != expected_marker:
                raise ArtifactError(
                    f"marker {metadata['marker']} != expected reader-v1 marker {expected_marker}"
                )
            if metadata["kind"] != expected_kind:
                raise ArtifactError(
                    f"kind {metadata['kind']} != expected reader-v1 kind {expected_kind}"
                )
            for name, value in metadata.items():
                if name == "nkpoints" and value < 0:
                    raise ArtifactError("nkpoints cannot be negative")
                if name not in {"marker", "kind", "nkpoints"} and value <= 0:
                    raise ArtifactError(f"{name} must be positive")
            if extra_validate is not None:
                extra_validate(metadata)
            nkpoints = metadata["nkpoints"]
            table_end = header_bytes + BLOCK_RECORD_BYTES * nkpoints
            if file_size < table_end:
                raise ArtifactError("file is smaller than the reader-v1 block table")
            records = [struct.unpack("=iq", handle.read(BLOCK_RECORD_BYTES)) for _ in range(nkpoints)]
            indices = tuple(record[0] for record in records)
            offsets = tuple(record[1] for record in records)
            if len(set(indices)) != len(indices):
                raise ArtifactError("reader-v1 k-point indices must be unique")
            if any(index < 1 for index in indices):
                raise ArtifactError("reader-v1 k-point indices must be 1-based positive integers")
            payload_bytes = block_size(metadata)
            for index, offset in zip(indices, offsets, strict=True):
                if offset < table_end:
                    raise ArtifactError(f"payload offset for k-point {index} overlaps the header table")
                if offset + payload_bytes > file_size:
                    raise ArtifactError(f"payload for k-point {index} extends beyond file size")
            intervals = sorted(
                (offset, offset + payload_bytes, index)
                for index, offset in zip(indices, offsets, strict=True)
            )
            for previous, current in zip(intervals, intervals[1:]):
                if current[0] < previous[1]:
                    raise ArtifactError(
                        f"payloads for k-points {previous[2]} and {current[2]} overlap"
                    )
    except FileNotFoundError:
        return _failure(file_path, artifact_type, "artifact not found", repair)
    except OSError as exc:
        return _failure(file_path, artifact_type, f"cannot read artifact: {exc}", repair)
    except (ArtifactError, struct.error) as exc:
        return _failure(file_path, artifact_type, str(exc), repair)

    metadata["k_indices"] = indices
    metadata["payload_bytes_per_kpoint"] = payload_bytes
    return ArtifactInfo(
        path=file_path,
        artifact_type=artifact_type,
        format_version="v1",
        size=file_size,
        metadata=metadata,
        gates=(
            GateResult(
                gate_id=f"{artifact_type}.format",
                status="PASS",
                message=f"valid {artifact_type} reader-v1 header, block table, and payload bounds",
                evidence=(str(file_path),),
                measurements={"size": file_size, "nkpoints": metadata["nkpoints"]},
            ),
        ),
    )


def inspect_eigenvector_v1(path: str | Path) -> ArtifactInfo:
    return _inspect_binary(
        path,
        artifact_type="ks_eigenvector",
        header_format="=6i",
        header_names=("marker", "kind", "nkpoints", "nspin", "nstates", "nbasis"),
        expected_marker=EIGENVECTOR_MARKER,
        expected_kind=EIGENVECTOR_KIND,
        block_size=lambda m: m["nspin"] * m["nstates"] * m["nbasis"] * COMPLEX_DOUBLE_BYTES,
    )


def _validate_velocity(metadata: dict[str, int]) -> None:
    if metadata["nalpha"] != 3:
        raise ArtifactError(f"nalpha {metadata['nalpha']} != 3")


def inspect_velocity_v1(path: str | Path) -> ArtifactInfo:
    return _inspect_binary(
        path,
        artifact_type="velocity_matrix",
        header_format="=7i",
        header_names=("marker", "kind", "nkpoints", "nspin", "nbands", "naos", "nalpha"),
        expected_marker=VELOCITY_MARKER,
        expected_kind=VELOCITY_KIND,
        block_size=lambda m: (
            m["nspin"] * m["nalpha"] * m["nbands"] * m["nbands"] * COMPLEX_DOUBLE_BYTES
        ),
        extra_validate=_validate_velocity,
    )


def _fail_gate(gate_id: str, message: str, evidence: tuple[str, ...], repair: str) -> GateResult:
    return GateResult(
        gate_id=gate_id,
        status="FAIL",
        message=message,
        evidence=evidence,
        repair=repair,
    )


def _binary_info(
    path: Path,
    artifact_type: str,
    metadata: dict[str, Any],
    message: str,
) -> ArtifactInfo:
    return ArtifactInfo(
        path,
        artifact_type,
        "v1",
        path.stat().st_size,
        metadata,
        (
            GateResult(
                f"{artifact_type}.format",
                "PASS",
                message,
                (str(path),),
            ),
        ),
    )


def _intervals_do_not_overlap(intervals: list[tuple[int, int]], context: str) -> None:
    intervals.sort()
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise ArtifactError(f"overlapping {context} payload blocks")


def _coulomb_pair_from_index(index: int, natoms: int) -> tuple[int, int]:
    remaining = index
    for first in range(natoms):
        row_size = natoms - first
        if remaining < row_size:
            return first, first + remaining
        remaining -= row_size
    raise ArtifactError(f"invalid Coulomb atom-pair index {index}")


def inspect_coulomb_v1(path: str | Path) -> ArtifactInfo:
    file_path = Path(path).expanduser().resolve()
    repair = "regenerate this Coulomb family with ABACUS out_librpa_reader_version = 1"
    try:
        data = file_path.read_bytes()
        if len(data) < 24:
            raise ArtifactError("file is smaller than the Coulomb v1 header")
        marker, iq, naux, value_flag, natoms, nblocks = struct.unpack_from("=6i", data)
        if marker != COULOMB_MARKER:
            raise ArtifactError(f"marker {marker} != expected Coulomb v1 marker {COULOMB_MARKER}")
        if iq <= 0 or naux <= 0 or natoms <= 0 or nblocks < 0 or value_flag not in {0, 1}:
            raise ArtifactError("invalid Coulomb v1 header values")
        table_end = 24 + 4 * natoms + 12 * nblocks
        if table_end > len(data):
            raise ArtifactError("truncated Coulomb v1 atom sizes or block table")
        atom_naux = struct.unpack_from(f"={natoms}i", data, 24)
        if any(value <= 0 for value in atom_naux) or sum(atom_naux) != naux:
            raise ArtifactError("Coulomb v1 per-atom auxiliary sizes do not sum to naux")
        npairs = natoms * (natoms + 1) // 2
        if nblocks > npairs:
            raise ArtifactError("Coulomb v1 block count exceeds atom-pair count")
        pair_indices: list[int] = []
        intervals: list[tuple[int, int]] = []
        value_bytes = 16 if value_flag == 1 else 8
        position = 24 + 4 * natoms
        for _ in range(nblocks):
            pair_index, offset = struct.unpack_from("=iq", data, position)
            position += 12
            if pair_index < 0 or pair_index >= npairs or pair_index in pair_indices:
                raise ArtifactError(f"invalid or duplicate Coulomb atom-pair index {pair_index}")
            first, second = _coulomb_pair_from_index(pair_index, natoms)
            payload_bytes = atom_naux[first] * atom_naux[second] * value_bytes
            if offset < table_end or offset + payload_bytes > len(data):
                raise ArtifactError(f"invalid Coulomb payload bounds for atom-pair {pair_index}")
            pair_indices.append(pair_index)
            intervals.append((offset, offset + payload_bytes))
        _intervals_do_not_overlap(intervals, "Coulomb")
        filename_iq = re.search(r"_iq_(\d+)_rank", file_path.name)
        if filename_iq and int(filename_iq.group(1)) != iq:
            raise ArtifactError(f"Coulomb filename q index does not match header iq={iq}")
        metadata = {
            "iq": iq,
            "naux": naux,
            "value_flag": value_flag,
            "natoms": natoms,
            "nblocks": nblocks,
            "atom_naux": tuple(atom_naux),
            "pair_indices": tuple(pair_indices),
        }
        return _binary_info(file_path, "coulomb_v1", metadata, "valid Coulomb v1 header and payload bounds")
    except FileNotFoundError:
        return _failure(file_path, "coulomb_v1", "artifact not found", repair)
    except OSError as exc:
        return _failure(file_path, "coulomb_v1", f"cannot read artifact: {exc}", repair)
    except (ArtifactError, struct.error) as exc:
        return _failure(file_path, "coulomb_v1", str(exc), repair)


def inspect_cs_v1(
    path: str | Path,
    *,
    wfc_atom_sizes: tuple[int, ...],
    aux_atom_sizes: tuple[int, ...],
) -> ArtifactInfo:
    file_path = Path(path).expanduser().resolve()
    repair = "regenerate this Cs family with ABACUS out_librpa_reader_version = 1"
    try:
        data = file_path.read_bytes()
        if len(data) < 28:
            raise ArtifactError("file is smaller than the Cs v1 header")
        marker, natoms, ncell, nrecords, nrecords_max = struct.unpack_from("=3i2q", data)
        if marker != CS_MARKER:
            raise ArtifactError(f"marker {marker} != expected Cs v1 marker {CS_MARKER}")
        if natoms <= 0 or ncell != 0 or nrecords < 0 or nrecords_max < nrecords:
            raise ArtifactError("invalid Cs v1 header values")
        if len(wfc_atom_sizes) != natoms or len(aux_atom_sizes) != natoms:
            raise ArtifactError("Cs v1 atom count does not match split-basis metadata")
        table_end = 28 + 36 * nrecords_max
        if table_end > len(data):
            raise ArtifactError("truncated Cs v1 block table")
        keys: list[tuple[int, int, int, int, int]] = []
        intervals: list[tuple[int, int]] = []
        position = 28
        for record_index in range(nrecords_max):
            ia1, ia2, r0, r1, r2, max_abs, offset = struct.unpack_from("=5idq", data, position)
            position += 36
            if record_index >= nrecords:
                if (ia1, ia2, r0, r1, r2, max_abs, offset) != (0, 0, 0, 0, 0, 0.0, 0):
                    raise ArtifactError("nonzero padding record in Cs v1 block table")
                continue
            if ia1 <= 0 or ia1 > natoms or ia2 <= 0 or ia2 > natoms:
                raise ArtifactError("invalid atom index in Cs v1 block table")
            if not math.isfinite(max_abs) or max_abs < 0:
                raise ArtifactError("invalid max-abs value in Cs v1 block table")
            key = (ia1, ia2, r0, r1, r2)
            if key in keys:
                raise ArtifactError("duplicate atom-pair/cell record in Cs v1 block table")
            payload_bytes = (
                wfc_atom_sizes[ia1 - 1]
                * wfc_atom_sizes[ia2 - 1]
                * aux_atom_sizes[ia1 - 1]
                * 8
            )
            if offset < table_end or offset + payload_bytes > len(data):
                raise ArtifactError("invalid Cs v1 payload bounds")
            keys.append(key)
            intervals.append((offset, offset + payload_bytes))
        _intervals_do_not_overlap(intervals, "Cs")
        metadata = {
            "natoms": natoms,
            "nrecords": nrecords,
            "record_keys": tuple(keys),
        }
        return _binary_info(file_path, "cs_v1", metadata, "valid Cs v1 header and payload bounds")
    except FileNotFoundError:
        return _failure(file_path, "cs_v1", "artifact not found", repair)
    except OSError as exc:
        return _failure(file_path, "cs_v1", f"cannot read artifact: {exc}", repair)
    except (ArtifactError, struct.error) as exc:
        return _failure(file_path, "cs_v1", str(exc), repair)


def inspect_shrink_sinvs_v1(
    path: str | Path,
    *,
    expected_rows: int,
    expected_cols: int,
) -> ArtifactInfo:
    file_path = Path(path).expanduser().resolve()
    repair = "regenerate shrink overlap data with ABACUS out_librpa_reader_version = 1"
    try:
        data = file_path.read_bytes()
        if len(data) < 8:
            raise ArtifactError("file is smaller than the shrink_sinvS v1 header")
        marker, nrecords = struct.unpack_from("=2i", data)
        if marker != SHRINK_SINVS_MARKER or nrecords < 0:
            raise ArtifactError("invalid shrink_sinvS v1 marker or record count")
        table_end = 8 + 44 * nrecords
        if table_end > len(data):
            raise ArtifactError("truncated shrink_sinvS v1 block table")
        intervals: list[tuple[int, int]] = []
        q_indices: list[int] = []
        position = 8
        for _ in range(nrecords):
            values = struct.unpack_from("=7idq", data, position)
            position += 44
            iq, nrow, ncol, begin_row, end_row, begin_col, end_col, weight, offset = values
            if iq <= 0 or nrow != expected_rows or ncol != expected_cols:
                raise ArtifactError("shrink_sinvS v1 q index or total dimensions are inconsistent")
            if (
                begin_row < 1
                or end_row < begin_row
                or end_row > nrow
                or begin_col < 1
                or end_col < begin_col
                or end_col > ncol
                or not math.isfinite(weight)
            ):
                raise ArtifactError("invalid shrink_sinvS v1 block dimensions or weight")
            payload_bytes = (end_row - begin_row + 1) * (end_col - begin_col + 1) * 16
            if offset < table_end or offset + payload_bytes > len(data):
                raise ArtifactError("invalid shrink_sinvS v1 payload bounds")
            q_indices.append(iq)
            intervals.append((offset, offset + payload_bytes))
        _intervals_do_not_overlap(intervals, "shrink_sinvS")
        metadata = {"nrecords": nrecords, "q_indices": tuple(q_indices)}
        return _binary_info(
            file_path,
            "shrink_sinvs_v1",
            metadata,
            "valid shrink_sinvS v1 header and payload bounds",
        )
    except FileNotFoundError:
        return _failure(file_path, "shrink_sinvs_v1", "artifact not found", repair)
    except OSError as exc:
        return _failure(file_path, "shrink_sinvs_v1", f"cannot read artifact: {exc}", repair)
    except (ArtifactError, struct.error) as exc:
        return _failure(file_path, "shrink_sinvs_v1", str(exc), repair)


def inspect_split_basis(path: str | Path, atom_types: tuple[int, ...]) -> ArtifactInfo:
    file_path = Path(path).expanduser().resolve()
    repair = "regenerate split basis metadata with the pinned ABACUS reader-v1 producer"
    try:
        tokens = file_path.read_text(encoding="utf-8").split()
        if len(tokens) < 3:
            raise ArtifactError("split basis header is incomplete")
        ntypes = _parse_int(tokens[0], "split basis type count")
        total_basis = _parse_int(tokens[1], "split basis total size")
        convention = tokens[2].lower()
        if ntypes <= 0 or total_basis <= 0 or convention != "abacus":
            raise ArtifactError("split basis header must use positive sizes and abacus convention")
        position = 3
        type_sizes = [0] * ntypes
        for _ in range(ntypes):
            if position + 2 > len(tokens):
                raise ArtifactError("split basis type-size table is truncated")
            type_index = _parse_int(tokens[position], "split basis type index") - 1
            size = _parse_int(tokens[position + 1], "split basis type size")
            position += 2
            if type_index < 0 or type_index >= ntypes or type_sizes[type_index] or size <= 0:
                raise ArtifactError("invalid or duplicate split basis type size")
            type_sizes[type_index] = size
        shell_types: set[int] = set()
        for _ in range(ntypes):
            if position + 2 > len(tokens):
                raise ArtifactError("split basis shell table is truncated")
            type_index = _parse_int(tokens[position], "split basis shell type") - 1
            nshell = _parse_int(tokens[position + 1], "split basis shell count")
            position += 2
            if (
                type_index < 0
                or type_index >= ntypes
                or type_index in shell_types
                or nshell < 0
                or position + nshell > len(tokens)
            ):
                raise ArtifactError("invalid split basis shell header")
            shell_types.add(type_index)
            shell_size = 0
            for token in tokens[position : position + nshell]:
                angular_momentum = _parse_int(token, "split basis angular momentum")
                if angular_momentum < 0:
                    raise ArtifactError("split basis angular momentum cannot be negative")
                shell_size += 2 * angular_momentum + 1
            position += nshell
            if shell_size != type_sizes[type_index]:
                raise ArtifactError("split basis shell layout does not match the type size")
        if position != len(tokens):
            raise ArtifactError("unexpected trailing tokens in split basis metadata")
        if any(atom_type <= 0 or atom_type > ntypes for atom_type in atom_types):
            raise ArtifactError("split basis type count does not cover stru_out atom types")
        atom_sizes = tuple(type_sizes[atom_type - 1] for atom_type in atom_types)
        if sum(atom_sizes) != total_basis:
            raise ArtifactError("split basis total size does not match stru_out atoms")
        metadata = {
            "ntypes": ntypes,
            "total_basis": total_basis,
            "type_sizes": tuple(type_sizes),
            "atom_sizes": atom_sizes,
            "convention": convention,
        }
        return _binary_info(file_path, "split_basis", metadata, "valid ABACUS split-basis metadata")
    except FileNotFoundError:
        return _failure(file_path, "split_basis", "artifact not found", repair)
    except (OSError, UnicodeDecodeError) as exc:
        return _failure(file_path, "split_basis", f"cannot read artifact: {exc}", repair)
    except ArtifactError as exc:
        return _failure(file_path, "split_basis", str(exc), repair)


def inspect_headwing_directory(path: str | Path) -> ArtifactInfo:
    root = Path(path).expanduser().resolve()
    gates: list[GateResult] = []
    metadata: dict[str, Any] = {}
    repair = "regenerate the complete pyatb_librpa_df directory on one full regular k-grid"
    try:
        kpath = parse_k_path_info(root / "k_path_info")
        band = parse_band_out(root / "band_out")
        metadata.update(kpath)
        if (
            band["nkpoints"] != kpath["nkpoints"]
            or band["nspin"] != kpath["nspin"]
            or band["nstates"] != kpath["nstates"]
        ):
            gates.append(
                _fail_gate(
                    "pyatb.dimensions.metadata",
                    "band_out dimensions are inconsistent with k_path_info",
                    (str(root / "band_out"), str(root / "k_path_info")),
                    repair,
                )
            )
    except ParseError as exc:
        gates.append(_fail_gate("pyatb.metadata", str(exc), (str(root),), repair))
        return ArtifactInfo(root, "pyatb_headwing_directory", "v1", 0, metadata, tuple(gates))

    eigen_paths = tuple(Path(item) for item in sorted(glob.glob(str(root / "KS_eigenvector_*"))))
    velocity_root = root / "velocity_matrix"
    velocity_paths = (
        (
            velocity_root,
            *tuple(
                sorted(
                    path
                    for path in root.iterdir()
                    if path.is_file() and path.name.startswith("velocity_matrix_")
                )
            ),
        )
        if velocity_root.is_file()
        else ()
    )
    if not eigen_paths:
        gates.append(
            _fail_gate("pyatb.eigenvectors", "no KS_eigenvector reader-v1 files found", (str(root),), repair)
        )
    if not velocity_paths:
        gates.append(
            _fail_gate("pyatb.velocity", "no velocity_matrix reader-v1 files found", (str(root),), repair)
        )

    eigen_infos = tuple(inspect_eigenvector_v1(item) for item in eigen_paths)
    velocity_infos = tuple(inspect_velocity_v1(item) for item in velocity_paths)
    for info in (*eigen_infos, *velocity_infos):
        gates.extend(info.gates)

    for info in eigen_infos:
        if info.accepted and (
            info.metadata["nspin"] != kpath["nspin"]
            or info.metadata["nstates"] != kpath["nstates"]
            or info.metadata["nbasis"] != kpath["nbasis"]
        ):
            gates.append(
                _fail_gate(
                    "pyatb.dimensions.eigenvector",
                    "KS eigenvector dimensions are inconsistent with k_path_info",
                    (str(info.path), str(root / "k_path_info")),
                    repair,
                )
            )
    for info in velocity_infos:
        if info.accepted and (
            info.metadata["nspin"] != kpath["nspin"]
            or info.metadata["nbands"] != kpath["nstates"]
            or info.metadata["naos"] != kpath["nbasis"]
        ):
            gates.append(
                _fail_gate(
                    "pyatb.dimensions.velocity",
                    "velocity_matrix dimensions are inconsistent with k_path_info",
                    (str(info.path), str(root / "k_path_info")),
                    repair,
                )
            )

    eigen_indices = tuple(
        index for info in eigen_infos if info.accepted for index in info.metadata["k_indices"]
    )
    velocity_indices = tuple(
        index for info in velocity_infos if info.accepted for index in info.metadata["k_indices"]
    )
    for label, indices in (("eigenvector", eigen_indices), ("velocity", velocity_indices)):
        duplicates = tuple(sorted(index for index, count in Counter(indices).items() if count > 1))
        if duplicates:
            gates.append(
                _fail_gate(
                    f"pyatb.duplicates.{label}",
                    f"{label} reader-v1 files contain duplicate k-point blocks",
                    tuple(str(index) for index in duplicates),
                    repair,
                )
            )
    eigen_coverage = set(eigen_indices)
    velocity_coverage = set(velocity_indices)
    expected = set(range(1, kpath["nkpoints"] + 1))
    if eigen_paths and eigen_coverage != expected:
        gates.append(
            _fail_gate(
                "pyatb.coverage.eigenvector",
                "KS eigenvector k-point coverage does not match the full k_path_info grid",
                (str(root),),
                repair,
            )
        )
    if velocity_paths and velocity_coverage != expected:
        gates.append(
            _fail_gate(
                "pyatb.coverage.velocity",
                "velocity_matrix k-point coverage does not match the full k_path_info grid",
                (str(root),),
                repair,
            )
        )

    if not any(gate.status == "FAIL" for gate in gates):
        gates.append(
            GateResult(
                gate_id="pyatb.headwing",
                status="PASS",
                message="PyATB head/wing metadata and reader-v1 payloads are dimensionally consistent",
                evidence=(str(root),),
                measurements={"nkpoints": kpath["nkpoints"]},
            )
        )
    total_size = sum(item.stat().st_size for item in root.iterdir() if item.is_file())
    return ArtifactInfo(root, "pyatb_headwing_directory", "v1", total_size, metadata, tuple(gates))


def _parse_int(token: str, context: str) -> int:
    try:
        return int(token)
    except ValueError as exc:
        raise ArtifactError(f"invalid integer in {context}: {token}") from exc


def _parse_float(token: str, context: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise ArtifactError(f"invalid floating-point value in {context}: {token}") from exc
    if not math.isfinite(value):
        raise ArtifactError(f"non-finite floating-point value in {context}: {token}")
    return value


def inspect_stru_out(path: str | Path) -> ArtifactInfo:
    file_path = Path(path).expanduser().resolve()
    repair = "regenerate stru_out with the pinned ABACUS producer using the intended symmetry setting"
    try:
        tokens = file_path.read_text(encoding="utf-8").split()
        if len(tokens) < 19:
            raise ArtifactError("stru_out is shorter than lattice, reciprocal lattice, and atom headers")
        for index, token in enumerate(tokens[:18]):
            _parse_float(token, f"stru_out lattice token {index + 1}")
        natoms = _parse_int(tokens[18], "stru_out atom count")
        if natoms <= 0:
            raise ArtifactError("stru_out atom count must be positive")
        position = 19
        required_atoms = 4 * natoms
        if len(tokens) < position + required_atoms:
            raise ArtifactError("stru_out is truncated while reading atoms")
        atom_types: list[int] = []
        for atom in range(natoms):
            for coordinate in range(3):
                _parse_float(tokens[position + coordinate], f"atom {atom + 1} coordinate")
            atom_type = _parse_int(tokens[position + 3], f"atom {atom + 1} type")
            if atom_type <= 0:
                raise ArtifactError("stru_out atom types must be 1-based positive integers")
            atom_types.append(atom_type)
            position += 4

        metadata: dict[str, Any] = {
            "natoms": natoms,
            "atom_types": tuple(atom_types),
            "has_symmetry": False,
            "n_symops": 0,
            "convention": None,
        }
        if position < len(tokens):
            if len(tokens) - position < 2:
                raise ArtifactError("truncated stru_out symmetry header")
            n_symops = _parse_int(tokens[position], "symmetry operation count")
            convention = tokens[position + 1].lower()
            if n_symops < 0:
                raise ArtifactError("symmetry operation count cannot be negative")
            if convention not in {"row", "col"}:
                raise ArtifactError(f"invalid symmetry convention: {tokens[position + 1]}")
            position += 2
            required = 12 * n_symops
            if len(tokens) - position < required:
                raise ArtifactError("stru_out is truncated while reading symmetry operations")
            for operation in range(n_symops):
                rotation_values = []
                for rotation in range(9):
                    rotation_values.append(
                        _parse_int(
                            tokens[position + rotation],
                            f"symmetry operation {operation + 1} rotation",
                        )
                    )
                determinant = (
                    rotation_values[0]
                    * (rotation_values[4] * rotation_values[8] - rotation_values[5] * rotation_values[7])
                    - rotation_values[1]
                    * (rotation_values[3] * rotation_values[8] - rotation_values[5] * rotation_values[6])
                    + rotation_values[2]
                    * (rotation_values[3] * rotation_values[7] - rotation_values[4] * rotation_values[6])
                )
                if abs(determinant) != 1:
                    raise ArtifactError(
                        f"symmetry operation {operation + 1} rotation determinant must be +1 or -1"
                    )
                position += 9
                for translation in range(3):
                    _parse_float(
                        tokens[position + translation],
                        f"symmetry operation {operation + 1} translation",
                    )
                position += 3
            if position != len(tokens):
                raise ArtifactError("unexpected trailing tokens after stru_out symmetry operations")
            metadata.update(
                {
                    "has_symmetry": n_symops > 0,
                    "n_symops": n_symops,
                    "convention": convention,
                }
            )
        file_size = file_path.stat().st_size
    except FileNotFoundError:
        return _failure(file_path, "stru_out", "stru_out not found", repair)
    except (OSError, UnicodeDecodeError) as exc:
        return _failure(file_path, "stru_out", f"cannot read stru_out: {exc}", repair)
    except ArtifactError as exc:
        return _failure(file_path, "stru_out", str(exc), repair)

    return ArtifactInfo(
        path=file_path,
        artifact_type="stru_out",
        format_version="current",
        size=file_size,
        metadata=metadata,
        gates=(
            GateResult(
                gate_id="stru_out.format",
                status="PASS",
                message="valid stru_out structure and symmetry tail",
                evidence=(str(file_path),),
                measurements={
                    "natoms": metadata["natoms"],
                    "n_symops": metadata["n_symops"],
                },
            ),
        ),
    )
