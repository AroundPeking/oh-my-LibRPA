from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any


KPOINT_TOLERANCE = 1e-8
OCCUPATION_TOLERANCE = 1e-8
TABLE_NAMES = {
    "ks": "KS_band_spin_*.dat",
    "exx": "EXX_band_spin_*.dat",
    "gw": "GW_band_spin_*.dat",
}
SPIN_PATTERN = re.compile(r"_spin_(\d+)\.dat$")
DIAGNOSTIC_PATTERNS = (
    re.compile(r"QPE(?:\s+solver)?\s+failed", re.IGNORECASE),
    re.compile(r"invalid\s+(?:Pad[eé]|analytic[- ]continuation)", re.IGNORECASE),
    re.compile(r"unstable[- ]root", re.IGNORECASE),
    re.compile(r"\bnan\b", re.IGNORECASE),
    re.compile(r"\binf(?:inity)?\b", re.IGNORECASE),
)


class ScientificBandError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


def _normalized_coordinate(value: float) -> float:
    normalized = value % 1.0
    if abs(normalized) <= KPOINT_TOLERANCE or abs(normalized - 1.0) <= KPOINT_TOLERANCE:
        return 0.0
    return round(normalized, 8)


def _normalized_kpoint(values: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(_normalized_coordinate(value) for value in values)  # type: ignore[return-value]


def _state_key(spin: int, kpoint: tuple[float, float, float], band: int) -> tuple[Any, ...]:
    return spin, *kpoint, band


def parse_band_table(path: str | Path, *, quantity: str) -> dict[str, object]:
    file_path = Path(path).expanduser().resolve()
    normalized_quantity = quantity.strip().lower()
    if normalized_quantity not in TABLE_NAMES:
        raise ScientificBandError("QUANTITY_INVALID", f"unsupported band quantity: {quantity}")
    match = SPIN_PATTERN.search(file_path.name)
    if match is None:
        raise ScientificBandError(
            "SPIN_IDENTITY_MISSING",
            "band table name must end with _spin_<positive integer>.dat",
            details={"path": str(file_path)},
        )
    spin = int(match.group(1))
    if spin <= 0:
        raise ScientificBandError("SPIN_IDENTITY_INVALID", "spin index must be positive")
    try:
        lines = [line for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError) as exc:
        raise ScientificBandError(
            "BAND_TABLE_UNREADABLE", f"cannot read {file_path}: {exc}"
        ) from exc
    if not lines:
        raise ScientificBandError("TABLE_SHAPE_INVALID", "band table is empty")

    rows: list[dict[str, object]] = []
    width: int | None = None
    seen_indices: set[int] = set()
    seen_kpoints: set[tuple[float, float, float]] = set()
    for line_number, line in enumerate(lines, start=1):
        tokens = line.split()
        if len(tokens) < 6 or (len(tokens) - 4) % 2:
            raise ScientificBandError(
                "TABLE_SHAPE_INVALID",
                "each row needs an index, three k coordinates, and occupation/energy pairs",
                details={"path": str(file_path), "line": line_number, "columns": len(tokens)},
            )
        if width is None:
            width = len(tokens)
        elif len(tokens) != width:
            raise ScientificBandError(
                "TABLE_SHAPE_INVALID",
                "band-table rows have inconsistent column counts",
                details={"path": str(file_path), "line": line_number},
            )
        try:
            row_index = int(tokens[0])
            raw_kpoint = tuple(float(token) for token in tokens[1:4])
            values = tuple(float(token) for token in tokens[4:])
        except ValueError as exc:
            raise ScientificBandError(
                "BAND_VALUE_INVALID",
                "band table contains a non-numeric value",
                details={"path": str(file_path), "line": line_number},
            ) from exc
        if row_index <= 0 or row_index in seen_indices:
            raise ScientificBandError(
                "KPOINT_INDEX_INVALID",
                "k-point row indices must be unique positive integers",
                details={"path": str(file_path), "line": line_number, "index": row_index},
            )
        if not all(math.isfinite(value) for value in (*raw_kpoint, *values)):
            raise ScientificBandError(
                "NONFINITE_BAND_VALUE",
                "band table contains NaN or infinity",
                details={"path": str(file_path), "line": line_number},
            )
        kpoint = _normalized_kpoint(raw_kpoint)  # type: ignore[arg-type]
        if kpoint in seen_kpoints:
            raise ScientificBandError(
                "DUPLICATE_KPOINT",
                "band table contains duplicate periodic k-point coordinates",
                details={"path": str(file_path), "line": line_number, "kpoint": kpoint},
            )
        seen_indices.add(row_index)
        seen_kpoints.add(kpoint)
        occupations = list(values[0::2])
        energies = list(values[1::2])
        rows.append(
            {
                "index": row_index,
                "kpoint": list(kpoint),
                "occupations": occupations,
                "energies_ev": energies,
            }
        )

    return {
        "path": str(file_path),
        "quantity": normalized_quantity,
        "spin": spin,
        "nkpoints": len(rows),
        "nbands": (width - 4) // 2 if width is not None else 0,
        "rows": rows,
    }


def _tables_for_quantity(root: Path, quantity: str) -> dict[int, dict[str, object]]:
    paths = sorted(root.glob(TABLE_NAMES[quantity]))
    if not paths:
        raise ScientificBandError(
            "BAND_TABLE_MISSING",
            f"missing {quantity.upper()} band table",
            details={"root": str(root), "pattern": TABLE_NAMES[quantity]},
        )
    tables: dict[int, dict[str, object]] = {}
    for path in paths:
        table = parse_band_table(path, quantity=quantity)
        spin = int(table["spin"])
        if spin in tables:
            raise ScientificBandError(
                "SPIN_IDENTITY_INVALID", f"duplicate {quantity} table for spin {spin}"
            )
        tables[spin] = table
    return tables


def _table_state_map(table: dict[str, object]) -> dict[tuple[Any, ...], dict[str, float]]:
    spin = int(table["spin"])
    states: dict[tuple[Any, ...], dict[str, float]] = {}
    for row in table["rows"]:  # type: ignore[union-attr]
        kpoint = tuple(row["kpoint"])  # type: ignore[index]
        for band, (occupation, energy) in enumerate(
            zip(row["occupations"], row["energies_ev"], strict=True),  # type: ignore[index]
            start=1,
        ):
            states[_state_key(spin, kpoint, band)] = {
                "occupation": float(occupation),
                "energy_ev": float(energy),
            }
    return states


def load_band_bundle(root: str | Path) -> dict[str, object]:
    run_root = Path(root).expanduser().resolve()
    tables = {quantity: _tables_for_quantity(run_root, quantity) for quantity in TABLE_NAMES}
    spin_sets = {quantity: set(items) for quantity, items in tables.items()}
    if len({tuple(sorted(items)) for items in spin_sets.values()}) != 1:
        raise ScientificBandError(
            "STATE_SET_MISMATCH", "KS, EXX, and GW spin sets do not match", details=spin_sets
        )
    spins = sorted(spin_sets["ks"])
    state_maps: dict[str, dict[tuple[Any, ...], dict[str, float]]] = {}
    for quantity, by_spin in tables.items():
        merged: dict[tuple[Any, ...], dict[str, float]] = {}
        for spin in spins:
            merged.update(_table_state_map(by_spin[spin]))
        state_maps[quantity] = merged
    state_sets = {quantity: set(items) for quantity, items in state_maps.items()}
    if len({frozenset(items) for items in state_sets.values()}) != 1:
        raise ScientificBandError(
            "STATE_SET_MISMATCH",
            "KS, EXX, and GW state identities do not match",
            details={quantity: len(items) for quantity, items in state_sets.items()},
        )

    states = []
    for key in sorted(state_maps["ks"]):
        spin, kx, ky, kz, band = key
        states.append(
            {
                "spin": spin,
                "kpoint": [kx, ky, kz],
                "band": band,
                "occupation": state_maps["ks"][key]["occupation"],
                "ks_ev": state_maps["ks"][key]["energy_ev"],
                "exx_ev": state_maps["exx"][key]["energy_ev"],
                "gw_ev": state_maps["gw"][key]["energy_ev"],
            }
        )
    first = tables["ks"][spins[0]]
    if any(
        int(table["nkpoints"]) != int(first["nkpoints"])
        or int(table["nbands"]) != int(first["nbands"])
        for quantity in tables.values()
        for table in quantity.values()
    ):
        raise ScientificBandError(
            "STATE_SET_MISMATCH", "KS, EXX, and GW table dimensions do not match"
        )
    return {
        "root": str(run_root),
        "spins": spins,
        "nkpoints": int(first["nkpoints"]),
        "nbands": int(first["nbands"]),
        "states": states,
    }


def select_insulating_window(
    bundle: dict[str, object],
    *,
    occupied_value: float = 2.0,
    padding: int = 3,
) -> dict[str, object]:
    if bundle["spins"] != [1]:
        raise ScientificBandError(
            "UNSUPPORTED_OCCUPATION_PATTERN", "scientific window currently requires nspin=1"
        )
    if padding < 0:
        raise ScientificBandError("WINDOW_INVALID", "state-window padding cannot be negative")
    grouped: dict[tuple[float, float, float], list[dict[str, object]]] = {}
    for state in bundle["states"]:  # type: ignore[union-attr]
        grouped.setdefault(tuple(state["kpoint"]), []).append(state)  # type: ignore[index]
    occupied_counts: set[int] = set()
    for kpoint, states in grouped.items():
        ordered = sorted(states, key=lambda item: int(item["band"]))
        occupied_flags: list[bool] = []
        for state in ordered:
            occupation = float(state["occupation"])
            if abs(occupation - occupied_value) <= OCCUPATION_TOLERANCE:
                occupied_flags.append(True)
            elif abs(occupation) <= OCCUPATION_TOLERANCE:
                occupied_flags.append(False)
            else:
                raise ScientificBandError(
                    "UNSUPPORTED_OCCUPATION_PATTERN",
                    "partial occupations are outside the first scientific-acceptance scope",
                    details={"kpoint": kpoint, "band": state["band"], "occupation": occupation},
                )
        count = sum(occupied_flags)
        if count <= 0 or count >= len(occupied_flags) or occupied_flags != [True] * count + [False] * (
            len(occupied_flags) - count
        ):
            raise ScientificBandError(
                "UNSUPPORTED_OCCUPATION_PATTERN",
                "occupied states must precede unoccupied states at every k-point",
                details={"kpoint": kpoint, "occupations": occupied_flags},
            )
        occupied_counts.add(count)
    if len(occupied_counts) != 1:
        raise ScientificBandError(
            "UNSUPPORTED_OCCUPATION_PATTERN",
            "occupied-band count changes along the evaluated k path",
            details={"occupied_counts": sorted(occupied_counts)},
        )
    vbm_band = next(iter(occupied_counts))
    cbm_band = vbm_band + 1
    nbands = int(bundle["nbands"])
    band_start = max(1, vbm_band - padding)
    band_stop = min(nbands, cbm_band + padding)
    selected = [
        state
        for state in bundle["states"]  # type: ignore[union-attr]
        if band_start <= int(state["band"]) <= band_stop
    ]
    valence = [state for state in selected if int(state["band"]) == vbm_band]
    conduction = [state for state in selected if int(state["band"]) == cbm_band]
    vbm_state = max(valence, key=lambda item: float(item["gw_ev"]))
    cbm_state = min(conduction, key=lambda item: float(item["gw_ev"]))
    return {
        "vbm_band": vbm_band,
        "cbm_band": cbm_band,
        "band_start": band_start,
        "band_stop": band_stop,
        "state_count": len(selected),
        "states": selected,
        "vbm_state": vbm_state,
        "cbm_state": cbm_state,
        "fundamental_gw_gap_ev": float(cbm_state["gw_ev"]) - float(vbm_state["gw_ev"]),
    }


def inspect_qpe_diagnostics(root: str | Path) -> dict[str, object]:
    run_root = Path(root).expanduser().resolve()
    logs = tuple(
        dict.fromkeys(
            (*sorted(run_root.glob("LibRPA*.out")), *sorted(run_root.glob("librpa_para_nprocs_*_myid_0.out")))
        )
    )
    failures: list[dict[str, object]] = []
    for path in logs:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(run_root):
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if any(pattern.search(line) for pattern in DIAGNOSTIC_PATTERNS):
                failures.append(
                    {
                        "reason_code": "QPE_SOLVER_FAILURE",
                        "path": str(path),
                        "line": line_number,
                        "excerpt": line.strip()[:500],
                    }
                )
    return {
        "accepted": not failures,
        "log_count": len(logs),
        "failure_count": len(failures),
        "failures": failures,
    }


def inspect_window_diagnostics(
    window: dict[str, object],
    log_diagnostics: dict[str, object],
    *,
    require_positive_gw_gap: bool,
) -> dict[str, object]:
    failures = [dict(item) for item in log_diagnostics.get("failures", [])]  # type: ignore[arg-type]
    gap = float(window["fundamental_gw_gap_ev"])
    if require_positive_gw_gap and gap <= 0.0:
        failures.append(
            {
                "reason_code": "NONPOSITIVE_GW_GAP",
                "message": "insulating occupation pattern has a nonpositive fundamental GW gap",
                "gap_ev": gap,
                "vbm_band": int(window["vbm_band"]),
                "cbm_band": int(window["cbm_band"]),
            }
        )
    return {
        **log_diagnostics,
        "accepted": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "require_positive_gw_gap": require_positive_gw_gap,
    }


def characterize_window_sampling(
    window: dict[str, object],
    *,
    screening_kpoints: tuple[tuple[float, float, float], ...],
    screening_grid: tuple[int, int, int],
) -> dict[str, object]:
    grid_points = {_normalized_kpoint(point) for point in screening_kpoints}
    path_points = sorted(
        {
            _normalized_kpoint(tuple(state["kpoint"]))  # type: ignore[arg-type,index]
            for state in window["states"]  # type: ignore[union-attr]
        }
    )
    vbm_kpoint = _normalized_kpoint(tuple(window["vbm_state"]["kpoint"]))  # type: ignore[arg-type,index]
    cbm_kpoint = _normalized_kpoint(tuple(window["cbm_state"]["kpoint"]))  # type: ignore[arg-type,index]
    off_grid = [list(point) for point in path_points if point not in grid_points]
    return {
        "screening_grid": list(screening_grid),
        "screening_kpoint_count": len(grid_points),
        "band_path_kpoint_count": len(path_points),
        "vbm_on_screening_grid": vbm_kpoint in grid_points,
        "cbm_on_screening_grid": cbm_kpoint in grid_points,
        "off_grid_path_kpoints": off_grid,
    }
