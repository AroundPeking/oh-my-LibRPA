#!/usr/bin/env python3
"""Render the KS / EXX / GW band figure for a finished run directory.

    python scripts/plot_band_triple.py --run-dir <dir> [--scf-kpt <dir>/KPT_scf]

The figure is the artifact a periodic GW result is judged on: a gap number
alone cannot show a collapsed dispersion or a broken layer. The rendering
rules are the LibRPA-database ones (``oml_mcp/band_frontier.py``), so the
artifact produced here is the same object a database record carries: one SVG
per method, a JSON sidecar per figure, and one metadata file for the set.

Pass ``--scf-kpt`` to mark the path samples that coincide with the
self-consistent mesh. Without it the curves are still correct, but no sample
is claimed to carry mesh information.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oml_mcp.band_analysis import BandAnalysisError  # noqa: E402
from oml_mcp.band_figure import DEFAULT_FIGURE_NAME, render_band_figure  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", required=True, help="directory holding the band tables")
    parser.add_argument(
        "--output",
        default=None,
        help=f"figure directory (default: <run-dir>/{DEFAULT_FIGURE_NAME})",
    )
    parser.add_argument("--occupied-bands", type=int, default=None)
    parser.add_argument(
        "--scf-kpt",
        default=None,
        help="KPT of the self-consistent run; grid-coincident path points get dots",
    )
    parser.add_argument(
        "--labels",
        default=None,
        help="JSON file with high-symmetry ticks: {\"ticks\": [{\"x\": 0.0, \"label\": \"G\"}]}",
    )
    parser.add_argument("--occupied-window", type=int, default=3)
    parser.add_argument("--empty-window", type=int, default=4)
    parser.add_argument("--title", default=None)
    return parser


def _read_labels(path: str | None) -> list[dict]:
    if not path:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    ticks = payload.get("ticks") if isinstance(payload, dict) else payload
    if not isinstance(ticks, list):
        raise SystemExit(f"{path}: expected a list of ticks or {{\"ticks\": [...]}}")
    return ticks


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
    scf_kpt = Path(args.scf_kpt).expanduser() if args.scf_kpt else run_dir / "KPT_scf"
    output = Path(args.output) if args.output else run_dir / DEFAULT_FIGURE_NAME
    try:
        report = render_band_figure(
            roots,
            output,
            occupied_bands=args.occupied_bands,
            title=args.title or f"Band structure: {run_dir.name}",
            scf_kpt=scf_kpt if scf_kpt.is_file() else None,
            kpath_labels=_read_labels(args.labels),
            occupied_window=args.occupied_window,
            empty_window=args.empty_window,
        )
    except BandAnalysisError as exc:
        print(f"band figure refused: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
