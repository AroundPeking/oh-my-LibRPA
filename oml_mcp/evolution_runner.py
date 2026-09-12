"""Entry point that wires the closed self-iteration loop onto the real stack.

The loop engine (``self_iteration``) and the production binding
(``remote_adapter.ControlledExecutionBinding``) both exist; this module is the
thin glue between them plus a command line interface so one command can:

1. propose one-axis candidates for a fast case (dry run, no cluster contact),
2. optionally stage every candidate locally from the upstream LibRPA
   regression tree and report which parameters actually applied,
3. optionally execute the loop for real through an approved execution
   profile, comparing each produced case against the frozen reference.

Execution is opt-in: without ``--execute`` nothing is ever submitted.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from .evolution import EvolutionBudget
from .execution_profiles import load_execution_profile
from .fast_benchmark import load_fast_case
from .parameter_prescriptions import (
    apply_prescription,
    resolve_prescription_keys,
)
from .remote_adapter import (
    ControlledExecutionBinding,
    ControlledRunAdapter,
    locate_case_source,
    stage_case_bundle,
)
from .self_iteration import LoopPolicy, SelfIterationError, run_self_iteration
from .control import ControlledExecutionService


DEFAULT_UPSTREAM_ROOT = Path("/Users/ghj/code/LibRPA/regression_tests/testcases")


class _RefusingAdapter:
    """Adapter used in proposal mode: any execution attempt is a bug."""

    def run_candidate(self, **_: Any) -> dict[str, Any]:
        raise SelfIterationError(
            "proposal mode must not execute; set execute=True to submit candidates"
        )


def load_reference_texts(case_id: str, upstream_root: str | Path) -> dict[str, str]:
    """Read the frozen reference outputs for a case from the regression tree.

    Frozen refs live in the LibRPA regression ``refs/<case>`` directory next to
    ``testcases/``; the case's own testcases directory is checked as a fallback.
    Files that are absent are simply omitted; the evaluator then reports
    NOT_EVALUATED for the affected validators instead of guessing.
    """
    case = load_fast_case(case_id)
    source = locate_case_source(case, upstream_root)
    refs_root = Path(upstream_root).expanduser().parent / "refs" / source.directory.name
    search_dirs = (refs_root, source.directory)
    reference: dict[str, str] = {}
    for name in case.output_files:
        for directory in search_dirs:
            path = directory / name
            if path.is_file():
                try:
                    reference[name] = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                break
    return reference


def prescription_definition(case_id: str) -> dict[str, Any]:
    """Flatten the family prescription into a plain parameter definition.

    Each rule contributes its pinned target when it has one, otherwise its
    default, so the loop baseline is the per-system recommended starting point
    (this is how "heavy elements need exx_cs_inv_thr 1e-5" reaches the run).
    """
    keys = resolve_prescription_keys(case_id)
    if keys is None:
        raise SelfIterationError(
            f"case {case_id} has no parameter prescription; pass an explicit baseline"
        )
    route_id, family = keys
    prescription = apply_prescription(route_id, family)
    definition: dict[str, Any] = {}
    for name, rule in prescription["parameters"].items():
        definition[name] = rule["target"] if rule.get("target") is not None else rule["default"]
    return definition


def baseline_from_prescription(case_id: str) -> dict[str, Any]:
    """Derive the loop baseline from the system-family prescription defaults."""
    return prescription_definition(case_id)


def stage_check(
    case_id: str,
    upstream_root: str | Path,
    candidate: dict[str, Any],
    *,
    staging_root: str | Path,
) -> dict[str, Any]:
    """Stage one candidate locally and report what actually applied.

    This never contacts a cluster: it verifies that the upstream case exists,
    that the candidate parameters are recognized by the input rewriter, and
    that the frozen reference outputs are readable.
    """
    case = load_fast_case(case_id)
    bundle = Path(staging_root).expanduser() / f"stagecheck-{case.case_id}"
    if bundle.exists():
        raise SelfIterationError(f"stage-check destination already exists: {bundle}")
    staging = stage_case_bundle(
        case, upstream_root=upstream_root, destination=bundle, candidate=candidate
    )
    reference = load_reference_texts(case_id, upstream_root)
    missing_reference = sorted(set(case.output_files) - set(reference))
    return {
        "case_id": case.case_id,
        "bundle": str(bundle),
        "stages": staging["stages"],
        "applied": staging["applied"],
        "unapplied": staging["unapplied"],
        "reference_files_found": sorted(reference),
        "reference_files_missing": missing_reference,
    }


def run_evolution(
    *,
    case_id: str,
    axis_values: dict[str, Sequence[Any]],
    allowed_axes: tuple[str, ...],
    budget: EvolutionBudget,
    execute: bool = False,
    execution_profile_id: str | None = None,
    upstream_root: str | Path = DEFAULT_UPSTREAM_ROOT,
    staging_root: str | Path | None = None,
    baseline: dict[str, Any] | None = None,
    stop_after_consecutive_rejections: int = 0,
) -> dict[str, Any]:
    """Run the closed loop for one fast case.

    Proposal mode (``execute=False``) never contacts a cluster. Execution mode
    requires an approved execution profile id and drives the controlled
    service: prepare immutable runs, submit every staged stage, inspect each
    with the diagnostic battery, and compare against the frozen reference.
    """
    case = load_fast_case(case_id)
    base = baseline if baseline is not None else baseline_from_prescription(case_id)

    if not execute:
        report = run_self_iteration(
            case=case,
            baseline=base,
            axis_values=axis_values,
            policy=LoopPolicy(
                budget=budget,
                allowed_axes=allowed_axes,
                stop_after_consecutive_rejections=stop_after_consecutive_rejections,
                execute=False,
            ),
            adapter=_RefusingAdapter(),
        )
        report["mode"] = "propose_only"
        return report

    if execution_profile_id is None:
        raise SelfIterationError("execute=True requires an execution profile id")
    if staging_root is None:
        raise SelfIterationError("execute=True requires a staging root")
    profile = load_execution_profile(execution_profile_id)
    service = ControlledExecutionService(profile, profile_id=execution_profile_id)
    binding = ControlledExecutionBinding(service=service)
    adapter = ControlledRunAdapter(
        case=case,
        upstream_root=upstream_root,
        staging_root=staging_root,
        materialize=binding.materialize,
        run_stages=binding.run_stages,
        collect_outputs=binding.collect_outputs,
    )
    reference = load_reference_texts(case_id, upstream_root)
    report = run_self_iteration(
        case=case,
        baseline=base,
        axis_values=axis_values,
        policy=LoopPolicy(
            budget=budget,
            allowed_axes=allowed_axes,
            stop_after_consecutive_rejections=stop_after_consecutive_rejections,
            execute=True,
        ),
        adapter=adapter,
        reference=reference or None,
    )
    report["mode"] = "execute"
    report["execution_profile_id"] = execution_profile_id
    return report


def _coerce_token(token: str) -> Any:
    lowered = token.strip().lower()
    if lowered in {"t", "true"}:
        return True
    if lowered in {"f", "false"}:
        return False
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token.strip()


def _parse_axis(value: str) -> tuple[str, tuple[Any, ...]]:
    name, _, raw = value.partition("=")
    if not name or not raw:
        raise SystemExit(f"invalid --axis {value!r}; expected name=v1,v2,...")
    tokens = [token for token in raw.split(",") if token.strip()]
    return name.strip(), tuple(_coerce_token(token) for token in tokens)


def _parse_budget_argument(value: str) -> tuple[str, float]:
    name, _, raw = value.partition("=")
    try:
        return name.strip(), float(raw)
    except ValueError as exc:
        raise SystemExit(f"invalid budget {value!r}: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", help="fast case id, e.g. bn-3d-sym-shrink-g0w0")
    parser.add_argument(
        "--axis",
        action="append",
        default=[],
        metavar="NAME=v1,v2",
        help="one mutation axis and its candidate values (repeatable)",
    )
    parser.add_argument(
        "--upstream-root",
        default=str(DEFAULT_UPSTREAM_ROOT),
        help="LibRPA regression testcases root holding the frozen upstream data",
    )
    parser.add_argument("--staging-root", help="directory for staged candidate bundles")
    parser.add_argument(
        "--profile", help="execution profile id; required with --execute"
    )
    parser.add_argument(
        "--baseline",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="override one baseline definition value (repeatable)",
    )
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--cpu-hours", type=float, default=1.0)
    parser.add_argument("--wall-minutes", type=float, default=60.0)
    parser.add_argument("--disk-gb", type=float, default=10.0)
    parser.add_argument(
        "--audit",
        action="store_true",
        help="report benchmark readiness for every registered fast case, then exit",
    )
    parser.add_argument(
        "--stage-check",
        action="store_true",
        help="stage one candidate locally to verify inputs and references, then exit",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="really submit candidates through the execution profile (default: propose only)",
    )
    parser.add_argument("--out", help="write the JSON report to this path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.audit:
        report = audit_benchmarks(args.upstream_root)
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0
    if not args.case:
        raise SystemExit("--case is required for this mode")
    axis_values = dict(_parse_axis(item) for item in args.axis)
    if not axis_values:
        raise SystemExit("at least one --axis is required")
    baseline = None
    if args.baseline:
        baseline = {}
        for item in args.baseline:
            key, _, raw = item.partition("=")
            baseline[key.strip()] = raw.strip()

    if args.stage_check:
        candidate = prescription_definition(args.case)
        for name, values in axis_values.items():
            candidate[name] = values[0]
        report = stage_check(
            args.case, args.upstream_root, candidate, staging_root=args.staging_root or "."
        )
    else:
        budget = EvolutionBudget(
            cpu_hours=args.cpu_hours,
            wall_seconds=int(args.wall_minutes * 60),
            disk_bytes=int(args.disk_gb * 10**9),
            max_candidates=args.max_candidates,
        )
        case = load_fast_case(args.case)
        allowed = tuple(
            axis for axis in axis_values if axis in _route_axes(case.route)
        )
        unknown = sorted(set(axis_values) - set(allowed))
        if unknown:
            raise SystemExit(
                f"axes not registered for route {case.route}: {', '.join(unknown)}"
            )
        report = run_evolution(
            case_id=args.case,
            axis_values=axis_values,
            allowed_axes=allowed,
            budget=budget,
            execute=args.execute,
            execution_profile_id=args.profile,
            upstream_root=args.upstream_root,
            staging_root=args.staging_root,
            baseline=baseline,
        )

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def _route_axes(route_id: str) -> frozenset[str]:
    from .evolution import ROUTE_MUTATION_AXES

    return ROUTE_MUTATION_AXES.get(route_id, frozenset())



def audit_benchmarks(upstream_root: str | Path = DEFAULT_UPSTREAM_ROOT) -> dict[str, Any]:
    """Report benchmark readiness for every registered fast case.

    For each case the audit answers four questions without running anything:
    does the upstream producer bundle exist, which stages would a replay run,
    are the frozen reference files readable, and does every validator regex
    actually extract values from those references. A case is READY only when
    all four hold; every other combination names what is missing.
    """
    from .fast_benchmark import list_fast_cases
    from .remote_adapter import RemoteAdapterError

    rows: list[dict[str, Any]] = []
    for case in list_fast_cases():
        row: dict[str, Any] = {
            "case_id": case.case_id,
            "route": case.route,
            "reference_status": case.reference_status,
            "stages": list(case.stages),
        }
        try:
            source = locate_case_source(case, upstream_root)
            row["upstream_found"] = True
            row["replayable_stages"] = list(source.replayable_stages)
        except RemoteAdapterError as exc:
            row["upstream_found"] = False
            row["upstream_error"] = str(exc)
            row["replayable_stages"] = []
        try:
            reference = load_reference_texts(case.case_id, upstream_root)
        except RemoteAdapterError:
            reference = {}
        row["reference_files_found"] = sorted(reference)
        row["reference_files_missing"] = sorted(set(case.output_files) - set(reference))
        validator_rows = []
        extracts = True
        for validator in case.validators:
            key = validator.file or next(iter(reference), None)
            text = reference.get(key) if key else None
            values = validator.extract(text) if text is not None else []
            ok = bool(values)
            extracts = extracts and ok
            validator_rows.append(
                {
                    "name": validator.name,
                    "file": key,
                    "values_from_reference": len(values),
                    "ok": ok,
                }
            )
        row["validators"] = validator_rows
        row["ready"] = bool(
            row["upstream_found"]
            and case.evaluable
            and extracts
            and not row["reference_files_missing"]
        )
        if not row["ready"]:
            reasons = []
            if not row["upstream_found"]:
                reasons.append("upstream bundle missing")
            if row["reference_files_missing"]:
                reasons.append("reference files missing")
            if not case.validators:
                reasons.append("no validators declared")
            elif not extracts:
                reasons.append("a validator regex extracts nothing from the reference")
            if case.reference_status != "REFERENCE_AVAILABLE":
                reasons.append(f"reference_status={case.reference_status}")
            row["not_ready_because"] = reasons
        rows.append(row)

    ready = sum(1 for row in rows if row["ready"])
    return {
        "schema": "oml.benchmark-audit.v1",
        "upstream_root": str(upstream_root),
        "total_cases": len(rows),
        "ready_cases": ready,
        "cases": rows,
    }

if __name__ == "__main__":
    sys.exit(main())
