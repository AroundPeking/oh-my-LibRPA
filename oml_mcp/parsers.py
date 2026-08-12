from __future__ import annotations

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
        return float(value.strip())
    except ValueError as exc:
        raise ParseError(f"invalid floating-point {name}: {value}") from exc


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
        if len(tokens) < 3:
            raise ParseError(f"invalid k-point at {file_path}: line {index}")
        try:
            kpoints.append((float(tokens[0]), float(tokens[1]), float(tokens[2])))
        except ValueError as exc:
            raise ParseError(f"invalid k-point at {file_path}: line {index}") from exc
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
