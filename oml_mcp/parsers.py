from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .models import InputDocument, InputEntry


class ParseError(ValueError):
    """Raised when an OML input or metadata file is malformed."""


def _read_lines(path: str | Path) -> tuple[Path, list[str]]:
    file_path = Path(path).expanduser()
    try:
        return file_path, file_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ParseError(f"input file not found: {file_path}") from exc
    except UnicodeDecodeError as exc:
        raise ParseError(f"input file is not UTF-8 text: {file_path}") from exc
    except OSError as exc:
        raise ParseError(f"cannot read input file {file_path}: {exc}") from exc


def _without_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def parse_abacus_input(path: str | Path) -> InputDocument:
    file_path, lines = _read_lines(path)
    entries: list[InputEntry] = []
    for line_number, raw in enumerate(lines, start=1):
        content = _without_comment(raw)
        if not content or content.upper() == "INPUT_PARAMETERS":
            continue
        parts = content.split(None, 1)
        if len(parts) != 2 or not parts[1].strip():
            raise ParseError(f"invalid ABACUS assignment at {file_path}: line {line_number}")
        entries.append(InputEntry(parts[0].lower(), parts[1].strip(), line_number))
    return InputDocument(path=file_path.resolve(), syntax="abacus", entries=tuple(entries))


def parse_librpa_input(path: str | Path) -> InputDocument:
    file_path, lines = _read_lines(path)
    entries: list[InputEntry] = []
    for line_number, raw in enumerate(lines, start=1):
        content = _without_comment(raw)
        if not content:
            continue
        if "=" not in content:
            raise ParseError(f"invalid LibRPA assignment at {file_path}: line {line_number}")
        key, value = content.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            raise ParseError(f"invalid LibRPA assignment at {file_path}: line {line_number}")
        entries.append(InputEntry(key, value, line_number))
    return InputDocument(path=file_path.resolve(), syntax="librpa", entries=tuple(entries))


def parse_abacus_kpt(path: str | Path) -> dict[str, Any]:
    file_path, lines = _read_lines(path)
    content = [_without_comment(line) for line in lines]
    content = [line for line in content if line]
    if len(content) < 3 or content[0].upper() not in {"K_POINTS", "KPOINTS"}:
        raise ParseError(f"invalid ABACUS KPT header in {file_path}")
    count = parse_int(content[1], name="KPT point count")
    if count < 0:
        raise ParseError(f"KPT point count cannot be negative in {file_path}")
    mode = content[2].strip().lower()
    rows = [line.split() for line in content[3:]]
    if mode in {"gamma", "mp", "monkhorst-pack"}:
        if count != 0 or len(rows) != 1 or len(rows[0]) != 6:
            raise ParseError(f"mesh KPT requires count 0 and one six-value row in {file_path}")
        grid = [parse_int(token, name="KPT grid dimension") for token in rows[0][:3]]
        offset = [parse_float(token, name="KPT grid offset") for token in rows[0][3:]]
        if any(value <= 0 for value in grid):
            raise ParseError(f"KPT grid dimensions must be positive in {file_path}")
        return {
            "mode": "mesh",
            "scheme": "gamma" if mode == "gamma" else "mp",
            "grid": grid,
            "offset": offset,
        }
    if mode in {"line", "line_cartesian"}:
        if count <= 0 or len(rows) != count:
            raise ParseError(
                f"KPT row count {len(rows)} != declared count {count} in {file_path}"
            )
        points: list[list[float]] = []
        segments: list[int] = []
        for index, row in enumerate(rows, start=1):
            if len(row) != 4:
                raise ParseError(f"invalid line-mode KPT row {index} in {file_path}")
            point = [parse_float(token, name="KPT coordinate") for token in row[:3]]
            segment = parse_int(row[3], name="KPT segment count")
            if segment <= 0:
                raise ParseError(f"KPT segment count must be positive in {file_path}")
            points.append(point)
            segments.append(segment)
        return {
            "mode": "path",
            "coordinate_system": "cartesian" if mode == "line_cartesian" else "direct",
            "points": points,
            "segments": segments,
        }
    if mode in {"direct", "cartesian"}:
        if count <= 0 or len(rows) != count:
            raise ParseError(
                f"KPT row count {len(rows)} != declared count {count} in {file_path}"
            )
        points: list[list[float]] = []
        weights: list[float] = []
        for index, row in enumerate(rows, start=1):
            if len(row) != 4:
                raise ParseError(f"invalid explicit KPT row {index} in {file_path}")
            points.append([parse_float(token, name="KPT coordinate") for token in row[:3]])
            weight = parse_float(row[3], name="KPT weight")
            if weight < 0:
                raise ParseError(f"KPT weights cannot be negative in {file_path}")
            weights.append(weight)
        return {
            "mode": "explicit",
            "coordinate_system": mode,
            "points": points,
            "weights": weights,
        }
    raise ParseError(f"unsupported KPT mode {content[2]!r} in {file_path}")


def parse_bool(value: str | None) -> bool:
    if value is None:
        raise ParseError("missing boolean value")
    normalized = value.strip().lower()
    if normalized in {"t", "true", "1", "yes", "on"}:
        return True
    if normalized in {"f", "false", "0", "no", "off"}:
        return False
    raise ParseError(f"invalid boolean value: {value}")


def parse_int(value: str | None, *, name: str = "value") -> int:
    if value is None:
        raise ParseError(f"missing integer {name}")
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ParseError(f"invalid integer {name}: {value}") from exc


def parse_float(value: str | None, *, name: str = "value") -> float:
    if value is None:
        raise ParseError(f"missing floating-point {name}")
    try:
        parsed = float(value.strip())
    except ValueError as exc:
        raise ParseError(f"invalid floating-point {name}: {value}") from exc
    if not math.isfinite(parsed):
        raise ParseError(f"floating-point {name} must be finite: {value}")
    return parsed


def _positive_header(path: Path, tokens: list[str], names: tuple[str, ...]) -> dict[str, int]:
    if len(tokens) < len(names):
        raise ParseError(f"incomplete header in {path}")
    values: dict[str, int] = {}
    for name, token in zip(names, tokens, strict=True):
        value = parse_int(token, name=name)
        if value <= 0:
            raise ParseError(f"{name} must be positive in {path}")
        values[name] = value
    return values


def parse_k_path_info(path: str | Path) -> dict[str, Any]:
    file_path, lines = _read_lines(path)
    content = [_without_comment(line) for line in lines]
    content = [line for line in content if line]
    if not content:
        raise ParseError(f"empty k_path_info: {file_path}")
    header = _positive_header(
        file_path,
        content[0].split(),
        ("nbasis", "nstates", "nspin", "nkpoints"),
    )
    if len(content) - 1 != header["nkpoints"]:
        raise ParseError(
            f"k_path_info row count {len(content) - 1} != {header['nkpoints']} in {file_path}"
        )
    kpoints: list[tuple[float, float, float]] = []
    for index, line in enumerate(content[1:], start=2):
        tokens = line.split()
        if len(tokens) != 3:
            raise ParseError(f"invalid k-point at {file_path}: line {index}")
        try:
            kpoint = (float(tokens[0]), float(tokens[1]), float(tokens[2]))
        except ValueError as exc:
            raise ParseError(f"invalid k-point at {file_path}: line {index}") from exc
        if not all(math.isfinite(value) for value in kpoint):
            raise ParseError(f"k-point must contain finite values at {file_path}: line {index}")
        kpoints.append(kpoint)
    for index, left in enumerate(kpoints):
        for right in kpoints[index + 1 :]:
            deltas = (lhs - rhs for lhs, rhs in zip(left, right, strict=True))
            if all(abs(delta - round(delta)) <= 1e-5 for delta in deltas):
                raise ParseError(f"duplicate periodic k-point coordinates in {file_path}")
    return {**header, "kpoints": tuple(kpoints)}


def parse_band_out_header(path: str | Path) -> dict[str, int]:
    file_path, lines = _read_lines(path)
    tokens: list[str] = []
    for line in lines:
        content = _without_comment(line)
        if content:
            tokens.extend(content.split())
        if len(tokens) >= 3:
            break
    return _positive_header(file_path, tokens[:3], ("nkpoints", "nspin", "nstates"))


def parse_band_out(path: str | Path) -> dict[str, int | float]:
    file_path, lines = _read_lines(path)
    tokens = [token for line in lines for token in _without_comment(line).split()]
    if len(tokens) < 5:
        raise ParseError(f"incomplete band_out header in {file_path}")
    header = _positive_header(
        file_path,
        tokens[:4],
        ("nkpoints", "nspin", "nstates", "nbasis"),
    )
    fermi_energy = parse_float(tokens[4], name="fermi_energy")
    if not math.isfinite(fermi_energy):
        raise ParseError(f"fermi_energy must be finite in {file_path}")
    expected_tokens = 5 + header["nkpoints"] * header["nspin"] * (
        2 + 4 * header["nstates"]
    )
    if len(tokens) != expected_tokens:
        raise ParseError(
            f"band_out token count {len(tokens)} != expected {expected_tokens} in {file_path}"
        )

    position = 5
    for ik in range(1, header["nkpoints"] + 1):
        for ispin in range(1, header["nspin"] + 1):
            actual_ik = parse_int(tokens[position], name="band_out k-point index")
            actual_spin = parse_int(tokens[position + 1], name="band_out spin index")
            position += 2
            if actual_ik != ik or actual_spin != ispin:
                raise ParseError(
                    f"unexpected band_out block index {actual_ik} {actual_spin}; "
                    f"expected {ik} {ispin} in {file_path}"
                )
            for band in range(1, header["nstates"] + 1):
                actual_band = parse_int(tokens[position], name="band_out band index")
                if actual_band != band:
                    raise ParseError(
                        f"unexpected band_out band index {actual_band}; expected {band} in {file_path}"
                    )
                values = (
                    parse_float(tokens[position + 1], name="band_out occupation"),
                    parse_float(tokens[position + 2], name="band_out eigenvalue"),
                    parse_float(tokens[position + 3], name="band_out eigenvalue_ev"),
                )
                if not all(math.isfinite(value) for value in values):
                    raise ParseError(f"band_out values must be finite in {file_path}")
                position += 4
    return {**header, "fermi_energy": fermi_energy}


def parse_bz_sampling(path: str | Path) -> dict[str, Any]:
    file_path, lines = _read_lines(path)
    tokens = [token for line in lines for token in _without_comment(line).split()]
    if len(tokens) < 5:
        raise ParseError(f"incomplete bz_sampling_out header in {file_path}")

    grid = tuple(
        parse_int(token, name=f"k-grid dimension {index}")
        for index, token in enumerate(tokens[:3], start=1)
    )
    if any(value <= 0 for value in grid):
        raise ParseError(f"bz_sampling_out k-grid dimensions must be positive in {file_path}")
    nk_full = math.prod(grid)
    nk_scf = parse_int(tokens[3], name="SCF k-point count")
    nk_ibz = parse_int(tokens[4], name="Coulomb IBZ k-point count")
    if nk_scf <= 0 or nk_ibz <= 0:
        raise ParseError(f"bz_sampling_out k-point counts must be positive in {file_path}")
    if nk_scf > nk_full:
        raise ParseError(f"SCF k-point count exceeds the full BZ grid size in {file_path}")
    if nk_ibz > nk_scf:
        raise ParseError(f"Coulomb IBZ k-point count exceeds the SCF count in {file_path}")

    required_tokens = 5 + 10 * nk_scf
    if len(tokens) < required_tokens:
        raise ParseError(
            f"bz_sampling_out token count {len(tokens)} is smaller than required "
            f"{required_tokens} in {file_path}"
        )

    position = 5
    weights: list[float] = []
    fractional_kpoints: list[tuple[float, float, float]] = []
    cartesian_kpoints: list[tuple[float, float, float]] = []
    mappings: list[tuple[int, int]] = []
    label_to_representative: dict[int, int] = {}
    representatives: set[int] = set()
    for row in range(1, nk_scf + 1):
        row_tokens = tokens[position : position + 10]
        position += 10
        actual_row = parse_int(row_tokens[0], name="BZ sampling k-point index")
        if actual_row != row:
            raise ParseError(
                f"unexpected BZ sampling k-point index {actual_row}; expected {row} in {file_path}"
            )
        weight = parse_float(row_tokens[1], name="BZ sampling k-point weight")
        coordinates = tuple(
            parse_float(token, name="BZ sampling k-point coordinate")
            for token in row_tokens[2:8]
        )
        if not math.isfinite(weight) or weight < 0 or not all(
            math.isfinite(value) for value in coordinates
        ):
            raise ParseError(f"BZ sampling row {row} contains an invalid number in {file_path}")
        ibz_index = parse_int(row_tokens[8], name="Coulomb IBZ index")
        representative = parse_int(row_tokens[9], name="representative SCF k-point index")
        if ibz_index <= 0 or ibz_index > nk_ibz:
            raise ParseError(f"BZ sampling IBZ index is out of range in {file_path}")
        if representative <= 0 or representative > nk_scf:
            raise ParseError(f"BZ sampling representative index is out of range in {file_path}")
        previous = label_to_representative.setdefault(ibz_index, representative)
        if previous != representative:
            raise ParseError(
                f"BZ sampling IBZ label {ibz_index} maps to multiple representatives in {file_path}"
            )
        representatives.add(representative)
        weights.append(weight)
        fractional_kpoints.append(coordinates[:3])
        cartesian_kpoints.append(coordinates[3:])
        mappings.append((ibz_index, representative))

    if abs(sum(weights) - 1.0) > 1e-6:
        raise ParseError(f"BZ sampling k-point weights do not sum to 1 in {file_path}")
    if len(representatives) != nk_ibz:
        raise ParseError(
            f"BZ sampling representative count does not match the Coulomb IBZ count in {file_path}"
        )
    if set(label_to_representative) != set(range(1, nk_ibz + 1)):
        raise ParseError(f"BZ sampling does not contain every Coulomb IBZ label in {file_path}")

    return {
        "grid": grid,
        "nk_full": nk_full,
        "nk_scf": nk_scf,
        "nk_ibz": nk_ibz,
        "weights": tuple(weights),
        "fractional_kpoints": tuple(fractional_kpoints),
        "cartesian_kpoints": tuple(cartesian_kpoints),
        "mappings": tuple(mappings),
        "ignored_trailing_tokens": len(tokens) - required_tokens,
    }


def parse_vxc_out(path: str | Path) -> dict[str, int]:
    file_path, lines = _read_lines(path)
    tokens = [token for line in lines for token in _without_comment(line).split()]
    header = _positive_header(file_path, tokens[:3], ("nkpoints", "nspin", "nstates"))
    expected_tokens = 3 + 2 * header["nkpoints"] * header["nspin"] * header["nstates"]
    if len(tokens) < expected_tokens:
        raise ParseError(
            f"vxc_out token count {len(tokens)} is smaller than required {expected_tokens} in {file_path}"
        )
    for token in tokens[3:expected_tokens]:
        value = parse_float(token, name="vxc_out matrix element")
        if not math.isfinite(value):
            raise ParseError(f"vxc_out matrix elements must be finite in {file_path}")
    return {**header, "ignored_trailing_tokens": len(tokens) - expected_tokens}
