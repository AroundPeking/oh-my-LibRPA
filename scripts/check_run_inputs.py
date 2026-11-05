#!/usr/bin/env python3
"""Check a materialized run for in-place input drift before resubmitting a stage.

    python scripts/check_run_inputs.py --run-dir <dir>

Exit status 2 means the files on disk no longer match the manifest the plan was
reviewed against: create a new plan instead of editing the run in place.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oml_mcp.input_drift import InputDriftError, check_run_inputs  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = check_run_inputs(args.run_dir)
    except InputDriftError as exc:
        print(f"cannot check inputs: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if report["drifted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
