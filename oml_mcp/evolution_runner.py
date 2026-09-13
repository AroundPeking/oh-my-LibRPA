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
from .profiles import load_profile
from .remote_adapter import (
    ControlledExecutionBinding,
    ControlledRunAdapter,
    RemoteAdapterError,
    locate_case_source,
    stage_case_bundle,
)
from .self_iteration import LoopPolicy, SelfIterationError, run_self_iteration
from .control import ControlledExecutionService


DEFAULT_UPSTREAM_ROOT = Path("/Users/ghj/code/LibRPA/regression_tests/testcases")

# Heavy producer bundles (hundreds of MB) must not live in any git repository.
# They are staged once into this local cache (or any directory listed in
# OML_FAST_UPSTREAM_ROOTS) and every lookup falls back through the roots.
CACHE_UPSTREAM_ROOT = Path.home() / ".local/share/oh-my-librpa/upstream"


def resolve_upstream_roots(primary: str | Path = DEFAULT_UPSTREAM_ROOT) -> tuple[Path, ...]:
    """Ordered upstream roots: explicit, env-listed, then the local data cache."""
    import os

    roots = [Path(primary).expanduser()]
    env_roots = os.environ.get("OML_FAST_UPSTREAM_ROOTS", "")
    for item in env_roots.split(":"):
        if item.strip():
            roots.append(Path(item.strip()).expanduser())
    roots.append(CACHE_UPSTREAM_ROOT)
    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return tuple(unique)


def _locate_case_in_roots(case, roots: tuple[Path, ...]):
    """Locate a case across the upstream roots; first hit wins."""
    from .remote_adapter import RemoteAdapterError, locate_case_source

    errors: list[str] = []
    for root in roots:
        try:
            return locate_case_source(case, root), root
        except RemoteAdapterError as exc:
            errors.append(str(exc))
    raise RemoteAdapterError(
        f"upstream case directory not found in any root: {'; '.join(errors)}"
    )


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
    # Reference outputs live in a <root>/../refs/<case> directory next to each
    # upstream root (the LibRPA regression convention), with the case directory
    # itself as a fallback. Search every root so a case can keep its heavy
    # producer bundle in the data cache while its refs stay in the repo.
    search_dirs: list[Path] = []
    roots = resolve_upstream_roots(upstream_root)
    for root in roots:
        # Refs live in a <root>/../refs/<case> directory next to each upstream
        # root (the LibRPA regression convention). Search every root's refs
        # regardless of where the heavy producer bundle itself was found.
        search_dirs.append(root.parent / "refs" / case.upstream_directory)
    try:
        source, source_root = _locate_case_in_roots(case, roots)
        search_dirs.append(source.directory)
    except RemoteAdapterError:
        pass
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
    axis_overrides: dict[str, Any] | None = None,
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
    source, source_root = _locate_case_in_roots(case, resolve_upstream_roots(upstream_root))
    staging = stage_case_bundle(
        case,
        upstream_root=source_root,
        destination=bundle,
        candidate=candidate,
        # Mirror the real loop semantics: only the axis overrides the caller
        # passed are explicit mutations; prescription-baseline values must not
        # clobber the case's own pinned keys.
        explicit_axes=frozenset(axis_overrides or {}),
    )
    reference = load_reference_texts(case_id, upstream_root)
    missing_reference = sorted(set(case.output_files) - set(reference))
    return {
        "case_id": case.case_id,
        "bundle": str(bundle),
        "stages": staging["stages"],
        "applied": staging["applied"],
        "unapplied": staging["unapplied"],
        "preserved": staging.get("preserved", {}),
        "axis_overrides": axis_overrides or {},
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
    software_profile_id: str | None = None,
    helpers_dir: str | Path | None = None,
    upstream_root: str | Path = DEFAULT_UPSTREAM_ROOT,
    staging_root: str | Path | None = None,
    baseline: dict[str, Any] | None = None,
    stop_after_consecutive_rejections: int = 0,
    control_replay: bool = False,
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
        policy = LoopPolicy(
            budget=budget,
            allowed_axes=allowed_axes or ("nfreq",),
            stop_after_consecutive_rejections=stop_after_consecutive_rejections,
            execute=False,
            control_replay=control_replay,
        )
        report = run_self_iteration(
            case=case,
            baseline=base,
            axis_values=axis_values,
            policy=policy,
            adapter=_RefusingAdapter(),
        )
        report["mode"] = "propose_only"
        return report

    if execution_profile_id is None:
        raise SelfIterationError("execute=True requires an execution profile id")
    if staging_root is None:
        raise SelfIterationError("execute=True requires a staging root")
    # Stale bundles from an earlier crashed attempt are derived data; set
    # them aside (never silently deleted) so this attempt starts clean while
    # the previous attempt's remains stay inspectable.
    if staging_root is not None:
        staging_dir = Path(staging_root).expanduser()
        import time as _time

        for stale in sorted(staging_dir.glob(f"{case.case_id}-iter*")):
            if stale.is_dir():
                stale.rename(staging_dir / f"{stale.name}.crashed-{int(_time.time())}")
    profile = load_execution_profile(execution_profile_id)
    service = ControlledExecutionService(profile, profile_id=software_profile_id)

    # Controlled bundles must carry the workflow helpers approved by the
    # pinned software profile. Stage them from --helpers-dir and verify every
    # digest before anything is planned or submitted; a mismatch is refused.
    approved_helpers = (
        load_profile(profile_id=software_profile_id)["contract"]["workflow_helpers"]
        if software_profile_id is not None
        else load_profile()["contract"]["workflow_helpers"]
    )

    def materialize_with_helpers(bundle: Path, definition: dict[str, Any]) -> dict[str, Any]:
        import hashlib
        import shutil as _shutil

        bundle_dir = Path(bundle)
        for name, digest in approved_helpers.items():
            source = Path(helpers_dir) / name if helpers_dir else None
            destination = bundle_dir / name
            if source is None or not source.is_file():
                raise SelfIterationError(
                    f"approved helper {name} not found in helpers dir; "
                    "pass --helpers-dir pointing at the reviewed helper set"
                )
            _shutil.copy2(source, destination)
            observed = hashlib.sha256(destination.read_bytes()).hexdigest()
            if observed != digest:
                destination.unlink()
                raise SelfIterationError(
                    f"helper {name} does not match the approved digest "
                    f"({observed[:16]}... != {digest[:16]}...); refusing to submit"
                )
        return binding.materialize(bundle, definition)

    binding = ControlledExecutionBinding(
        service=service,
        # The plan MUST be computed against the same pinned software profile
        # the controlled service verifies with, or the materializer's digest
        # replay produces STALE_PLAN by construction.
        plan_options={
            "task": case.task,
            "system_type": case.system_type,
            "soc": case.soc,
            "use_symmetry": case.use_symmetry,
            "headwing": case.headwing,
            "profile_id": software_profile_id,
        },
        # The live LibRPA monitor reads the LOCAL run mirror, which for ssh
        # transport never receives live outputs - it would poll its whole
        # budget as UNOBSERVED. Stage-gate inspection still judges the stage.
        monitor_librpa=profile.transport == "local",
    )
    case_source, case_root = _locate_case_in_roots(case, resolve_upstream_roots(upstream_root))
    adapter = ControlledRunAdapter(
        case=case,
        upstream_root=case_root,
        staging_root=staging_root,
        materialize=materialize_with_helpers,
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
            control_replay=control_replay,
        ),
        adapter=adapter,
        reference=reference or None,
    )
    report["mode"] = "execute"
    report["execution_profile_id"] = execution_profile_id
    report["software_profile_id"] = software_profile_id
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
        "--helpers-dir",
        help="directory holding the workflow helper scripts approved by the software profile",
    )
    parser.add_argument(
        "--software-profile",
        help="pinned software (ABACUS/LibRPA/PyATB) profile id; defaults to the global default",
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
        "--control",
        action="store_true",
        help="control replay: run the pristine upstream config once as a reproducibility anchor",
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
    if not axis_values and not args.control:
        raise SystemExit("at least one --axis is required (or use --control)")
    baseline = None
    if args.baseline:
        baseline = {}
        for item in args.baseline:
            key, _, raw = item.partition("=")
            baseline[key.strip()] = raw.strip()

    if args.stage_check:
        candidate = prescription_definition(args.case)
        axis_overrides = {name: values[0] for name, values in axis_values.items()}
        candidate.update(axis_overrides)
        report = stage_check(
            args.case, args.upstream_root, candidate, staging_root=args.staging_root or ".",
            axis_overrides=axis_overrides,
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
            software_profile_id=args.software_profile,
            helpers_dir=args.helpers_dir,
            upstream_root=args.upstream_root,
            staging_root=args.staging_root,
            baseline=baseline,
            control_replay=args.control,
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
            source, source_root = _locate_case_in_roots(case, resolve_upstream_roots(upstream_root))
            row["upstream_found"] = True
            row["upstream_root"] = str(source_root)
            row["replayable_stages"] = list(source.replayable_stages)
        except RemoteAdapterError as exc:
            row["upstream_found"] = False
            row["upstream_error"] = str(exc)[:160]
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
