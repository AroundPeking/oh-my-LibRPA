from __future__ import annotations

import glob
import struct
from pathlib import Path
from typing import Any, Callable

from .models import ArtifactInfo, GateResult
from .parsers import ParseError, parse_band_out_header, parse_k_path_info


EIGENVECTOR_MARKER = -12345679
EIGENVECTOR_KIND = 28
VELOCITY_MARKER = -12345680
VELOCITY_KIND = 29
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
                if name not in {"marker", "kind"} and value <= 0:
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


def inspect_headwing_directory(path: str | Path) -> ArtifactInfo:
    root = Path(path).expanduser().resolve()
    gates: list[GateResult] = []
    metadata: dict[str, Any] = {}
    repair = "regenerate the complete pyatb_librpa_df directory on one full regular k-grid"
    try:
        kpath = parse_k_path_info(root / "k_path_info")
        band = parse_band_out_header(root / "band_out")
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
    velocity_paths = tuple(Path(item) for item in sorted(glob.glob(str(root / "velocity_matrix*"))))
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

    eigen_coverage = {index for info in eigen_infos if info.accepted for index in info.metadata["k_indices"]}
    velocity_coverage = {
        index for info in velocity_infos if info.accepted for index in info.metadata["k_indices"]
    }
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
        return float(token)
    except ValueError as exc:
        raise ArtifactError(f"invalid floating-point value in {context}: {token}") from exc


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
                for rotation in range(9):
                    _parse_int(tokens[position + rotation], f"symmetry operation {operation + 1} rotation")
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
                {"has_symmetry": True, "n_symops": n_symops, "convention": convention}
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
