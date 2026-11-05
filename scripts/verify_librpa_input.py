#!/usr/bin/env python3
"""Audit a LibRPA input before staging or submitting it.

Run this for every FHI-aims + LibRPA and ABACUS + LibRPA submission. It catches
the two mistakes that silently change the physics:

    # the input was rebuilt from the driver dump: cs_R_threshold is ignored
    .venv/bin/python scripts/verify_librpa_input.py \
      --librpa-in librpa.in --dimension 3d --require-cs-threshold

    # a strict-2D base was reused for a 3D system
    .venv/bin/python scripts/verify_librpa_input.py \
      --librpa-in librpa.in --dimension 3d

For FHI-aims, also pass ``--control-in control.in`` so ``frequency_points`` and
``nfreq`` are checked as a pair.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oml_mcp.librpa_input import audit_librpa_in  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--librpa-in", required=True)
    parser.add_argument("--dimension", default="3d", choices=("3d", "2d"))
    parser.add_argument(
        "--require-cs-threshold",
        action="store_true",
        help="require an explicit cs_threshold (FHI-aims production inputs)",
    )
    parser.add_argument(
        "--control-in",
        default=None,
        help="optional FHI-aims control.in; checks frequency_points against nfreq",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = audit_librpa_in(
        args.librpa_in,
        dimension=args.dimension,
        require_cs_threshold=args.require_cs_threshold,
        control_in=args.control_in,
    )
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"librpa.in: {report.path}")
        print(f"dimension: {args.dimension}")
        for finding in report.findings:
            print(f"[{finding.status}] {finding.gate_id}: {finding.message}")
            if finding.repair:
                print(f"    repair: {finding.repair}")
        print(f"ok: {report.ok}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
