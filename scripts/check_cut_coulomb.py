#!/usr/bin/env python3
"""Decide LibRPA's Wc Cholesky switch from the actual cut-Coulomb matrices.

The truncated (cut) Coulomb is what LibRPA factorises for Wc. When it is not
positive definite, ``use_cholesky_gw_wc = t`` fails at the first q block with
"the matrix is not positive definite"; when it is positive definite, Cholesky
is the faster path and should be enabled. Run this after the Coulomb stage and
before the LibRPA stage:

    .venv/bin/python scripts/check_cut_coulomb.py --run-dir <run> --write

``--write`` only rewrites ``librpa.in`` in that directory; it never touches the
Coulomb matrices or the production defaults.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oml_mcp.coulomb_diagnostics import inspect_cut_coulomb_cholesky  # noqa: E402


def _read_switch(path: Path, key: str) -> bool | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == key:
            return value.split("#", 1)[0].strip().lower() in {"t", "true", "1", "on"}
    return None


def _write_switch(path: Path, key: str, value: bool) -> None:
    token = "t" if value else "f"
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for index, line in enumerate(lines):
        name, separator, _ = line.partition("=")
        if separator and name.strip() == key:
            lines[index] = f"{key} = {token}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key} = {token}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--write", action="store_true", help="set use_cholesky_gw_wc in librpa.in")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).expanduser().resolve()
    librpa_in = run_dir / "librpa.in"
    current = _read_switch(librpa_in, "use_cholesky_gw_wc")
    gate = inspect_cut_coulomb_cholesky(run_dir, use_cholesky=current)
    measurements = gate.measurements or {}
    predicted = bool(measurements.get("positive_definite"))

    if args.write:
        if not librpa_in.is_file():
            print(f"librpa.in does not exist in {run_dir}", file=sys.stderr)
            return 2
        _write_switch(librpa_in, "use_cholesky_gw_wc", predicted)
        current = predicted
        gate = inspect_cut_coulomb_cholesky(run_dir, use_cholesky=current)

    report = {
        "run_dir": str(run_dir),
        "gate": gate.to_dict(),
        "current_use_cholesky_gw_wc": current,
        "recommended_use_cholesky_gw_wc": predicted,
        "positive_definite": predicted,
    }
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"cut-Coulomb q blocks: {measurements.get('q_blocks')}")
        print(f"min eigenvalue: {measurements.get('min_eigenvalue'):.6e}")
        print(f"min relative eigenvalue: {measurements.get('min_relative_eigenvalue'):.3e}")
        print(f"negative eigenvalues: {measurements.get('negative_eigenvalue_count')}")
        print(f"positive definite: {predicted}")
        print(f"current use_cholesky_gw_wc: {current}")
        print(f"recommended use_cholesky_gw_wc: {'t' if predicted else 'f'}")
        print(f"status: {gate.status} - {gate.message}")
        if gate.repair:
            print(f"repair: {gate.repair}")
    return 0 if gate.status in {"PASS", "WARN", "SKIP"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
