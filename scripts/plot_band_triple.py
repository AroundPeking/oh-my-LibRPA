#!/usr/bin/env python3
"""Render the KS / EXX / GW band figure for a finished run directory.

    python scripts/plot_band_triple.py --run-dir <dir> [--reference-gap-ev 1.06]

The figure is the artifact a periodic GW result is judged on: the gap number
alone cannot show a collapsed dispersion or a broken layer. Energies are
referenced to each layer's own VBM, and the database gap - when given - is
printed as an advisory comparison, never as a pass/fail.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oml_mcp.band_figure import DEFAULT_FIGURE_NAME, render_band_figure  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", required=True, help="directory holding the band tables")
    parser.add_argument("--output", default=None, help=f"PNG path (default: <run-dir>/{DEFAULT_FIGURE_NAME})")
    parser.add_argument("--occupied-bands", type=int, default=None)
    parser.add_argument("--reference-gap-ev", type=float, default=None)
    parser.add_argument("--window-ev", type=float, default=8.0)
    parser.add_argument("--title", default=None)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run_dir = Path(args.run_dir).expanduser()
    roots = {
        layer: run_dir / f"{layer.upper()}_band_spin_1.dat" for layer in ("ks", "exx", "gw")
    }
    missing = [str(path) for path in roots.values() if not path.is_file()]
    if missing:
        print(f"missing band tables: {', '.join(missing)}", file=sys.stderr)
        return 2
    output = Path(args.output) if args.output else run_dir / DEFAULT_FIGURE_NAME
    report = render_band_figure(
        roots,
        output,
        occupied_bands=args.occupied_bands,
        title=args.title or f"Band structure: {run_dir.name}",
        window_ev=args.window_ev,
        reference_gap_ev=args.reference_gap_ev,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
