#!/usr/bin/env python3
"""Run one analysis-driven loop on a fast case through an execution profile.

Example (BN, fisherd current stack):

    .venv/bin/python scripts/run_case_loop.py \
      --case bn-k222-sym-v1-shrink-head-g0w0 \
      --execution-profile fisherd-current-3d-gw-v1 \
      --software-profile abacus-librpa-2026-09-06-v6 \
      --staging-root ~/.local/share/oh-my-librpa/fisherd/sources \
      --helpers-dir templates/abacus-librpa-gw/template \
      --upstream-root ~/.local/share/oh-my-librpa/upstream \
      --artifact-root ~/.local/share/oh-my-librpa/fisherd/loop-artifacts \
      --max-trials 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oml_mcp.fast_benchmark import load_fast_case  # noqa: E402
from oml_mcp.loop_adapter import ControlledLoopRunner  # noqa: E402
from oml_mcp.loop_runner import run_loop  # noqa: E402


CONTINUATION_SEED = {
    "tfgrids_type": "minimax",
    "n_params_anacon": 6,
    "option_qpe_solver": 0,
    "use_qpe_adaptive_damp": False,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True)
    parser.add_argument("--execution-profile", required=True)
    parser.add_argument("--software-profile", default=None)
    parser.add_argument("--staging-root", required=True)
    parser.add_argument("--helpers-dir", required=True)
    parser.add_argument("--upstream-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--max-trials", type=int, default=1)
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--scheduler-max-polls", type=int, default=None)
    parser.add_argument("--ledger", default=None)
    parser.add_argument(
        "--seed-file",
        default=None,
        help="JSON definition merged over the continuation seed (e.g. the case's current values)",
    )
    parser.add_argument(
        "--gap-reference-ev",
        type=float,
        default=None,
        help="trusted physical GW gap reference (eV); overrides the frozen replay gap",
    )
    parser.add_argument(
        "--basis-root",
        default=os.environ.get("OML_BASIS_LIBRARY_ROOT"),
        help="LibRPA-database root (default: $OML_BASIS_LIBRARY_ROOT); PP/NAO/ABFS come from here by default",
    )
    parser.add_argument(
        "--basis-family",
        default=None,
        help="preferred element-set family (e.g. SG15); default is the deterministic first usable set",
    )
    parser.add_argument(
        "--case-basis",
        action="store_true",
        help="opt out of the database basis default and keep the case-bundled assets",
    )
    parser.add_argument(
        "--policy-mode",
        choices=("production", "replay"),
        default="production",
        help="policy scope: production enforces the database basis and standard k grid",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="run the policy preflight audit and exit without submitting",
    )
    parser.add_argument(
        "--accept-deviations",
        action="store_true",
        help="acknowledge reviewed settings deviations (required when the review card flags any)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    seed = dict(CONTINUATION_SEED)
    if args.seed_file:
        seed.update(json.loads(Path(args.seed_file).read_text(encoding="utf-8")))
    case = load_fast_case(args.case)
    runner = ControlledLoopRunner(
        case=case,
        execution_profile_id=args.execution_profile,
        software_profile_id=args.software_profile,
        staging_root=args.staging_root,
        helpers_dir=args.helpers_dir,
        upstream_root=args.upstream_root,
        artifact_root=args.artifact_root,
        poll_seconds=args.poll_seconds,
        scheduler_max_polls=args.scheduler_max_polls,
        basis_root=args.basis_root,
        basis_family=args.basis_family,
        use_database_basis=not args.case_basis,
        policy_mode=args.policy_mode,
    )
    audit = runner.audit(seed, mode=args.policy_mode)
    if args.preflight_only:
        print(json.dumps(audit, indent=2, ensure_ascii=False))
        return 0 if audit["ok"] else 2
    if not audit["ok"]:
        print(json.dumps(audit, indent=2, ensure_ascii=False))
        print("preflight failed; refusing to submit", file=sys.stderr)
        return 2
    if audit["review"]["needs_review"] and not args.accept_deviations:
        print(json.dumps(audit, indent=2, ensure_ascii=False))
        print(
            "settings review has deviations; review them and pass --accept-deviations",
            file=sys.stderr,
        )
        return 2
    ledger = args.ledger or str(Path(args.artifact_root) / f"{case.case_id}-ledger.json")
    gap_reference = (
        args.gap_reference_ev
        if args.gap_reference_ev is not None
        else runner.reference_gap_ev()
    )
    result = run_loop(
        seed,
        runner,
        occupied_bands=None,
        gap_reference_ev=gap_reference,
        max_trials=args.max_trials,
        ledger_path=ledger,
    )
    report = result.to_dict()
    if result.records:
        report["reference"] = runner.evaluate_reference(result.records[-1].trial)
    report["gap_reference_ev"] = gap_reference
    report["execution_profile"] = args.execution_profile
    report["software_profile"] = args.software_profile
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if result.status == "ACCEPTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
