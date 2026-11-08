#!/usr/bin/env python3
"""Project Delta-ST completion time from live per-rank progress records."""

import argparse
import math
import statistics
import sys
from pathlib import Path
from typing import Optional, Tuple


def parse_progress(path: Path) -> Tuple[int, float, Optional[int]]:
    completed = 0
    elapsed = 0.0
    equations_per_kpair = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            fields = line.split()
            if not fields:
                continue
            if fields[0] == "equation" and len(fields) >= 12:
                completed = max(completed, int(fields[6]))
                elapsed = max(elapsed, float(fields[11]))
            elif fields[0] == "kpair_finish" and len(fields) >= 12:
                cumulative = int(fields[6])
                if cumulative > 0 and equations_per_kpair is None:
                    equations_per_kpair = cumulative
                elapsed = max(elapsed, float(fields[11]))
    return completed, elapsed, equations_per_kpair


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--total-equations", type=int)
    mode.add_argument("--global-kpoints", type=int)
    parser.add_argument("--kpoint-groups", type=int, default=1)
    parser.add_argument("--equations-per-kpair", type=int)
    parser.add_argument("--startup-minutes", type=float, default=5.0)
    parser.add_argument("--safety-factor", type=float, default=1.25)
    parser.add_argument("--budget-hours", type=float, default=18.0)
    parser.add_argument("--wall-limit-hours", type=float, default=24.0)
    args = parser.parse_args()

    files = sorted(args.run_dir.glob("STERNHEIMER_CHI0_PROGRESS_rank*.dat"))
    if not files:
        print("status=insufficient_progress reason=no_progress_files")
        return 3

    records = [(path, *parse_progress(path)) for path in files]
    inferred = [record[3] for record in records if record[3] is not None]
    equations_per_kpair = args.equations_per_kpair or (min(inferred) if inferred else None)

    if args.total_equations is not None:
        target_per_rank = math.ceil(args.total_equations / len(files))
        mode_name = "global_equation"
    else:
        if args.global_kpoints <= 0 or args.kpoint_groups <= 0:
            parser.error("global k-points and k-point groups must be positive")
        if equations_per_kpair is None:
            print("status=insufficient_progress reason=no_completed_kpair")
            return 3
        local_kpairs = math.ceil(args.global_kpoints / args.kpoint_groups)
        target_per_rank = local_kpairs * equations_per_kpair
        mode_name = "frequency_grouped"

    projections = []
    for path, completed, elapsed, _ in records:
        if completed <= 0 or elapsed <= 0:
            print(f"status=insufficient_progress reason=rank_not_started file={path.name}")
            return 3
        projected = args.startup_minutes * 60.0 + elapsed * target_per_rank / completed
        projections.append(projected * args.safety_factor / 3600.0)

    maximum = max(projections)
    print("status=estimated")
    print(f"mode={mode_name}")
    print(f"ranks={len(files)}")
    print(f"target_equations_per_rank={target_per_rank}")
    if equations_per_kpair is not None:
        print(f"equations_per_kpair={equations_per_kpair}")
    print(f"projected_min_hours={min(projections):.3f}")
    print(f"projected_median_hours={statistics.median(projections):.3f}")
    print(f"projected_max_hours={maximum:.3f}")
    print(f"budget_hours={args.budget_hours:.3f}")
    print(f"wall_limit_hours={args.wall_limit_hours:.3f}")
    if maximum <= args.budget_hours:
        print("decision=PASS_SUBMIT_FULL_CAMPAIGN")
        return 0
    if maximum <= args.wall_limit_hours:
        print("decision=UNSAFE_CHANGE_PARALLEL_LAYOUT")
        return 2
    print("decision=REJECT_WILL_EXCEED_WALL_LIMIT")
    return 2


if __name__ == "__main__":
    sys.exit(main())
