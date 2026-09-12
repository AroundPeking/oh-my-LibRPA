"""Real (cluster-driving) adapter for the closed-loop self-iteration engine.

``oml_mcp.self_iteration`` defines the loop and an ``IterationAdapter`` protocol.
This module supplies the production implementation: it materializes a fast
benchmark case into an immutable source bundle, applies the candidate
parameter definition, drives the controlled ABACUS -> PyATB -> NSCF ->
preprocess -> LibRPA stages on the remote scheduler, and returns the produced
case outputs for reference comparison.

Design boundaries
-----------------
* **Nothing here runs on the local macOS host.** Every stage is executed on the
  configured remote scheduler through an approved execution profile; the local
  side only stages inputs and collects artifacts.
* **No fabricated results.** If a stage cannot be observed, the adapter returns
  ``status: "UNKNOWN"`` and the loop records NOT_EVALUATED. It never invents a
  verdict, and it never claims a run passed.
* **Fresh run per attempt.** The controlled executor refuses to reuse a run
  directory after a terminal stage attempt, so each iteration creates a new run.
* **Stage gating.** Each stage is inspected with the reference-free diagnostic
  battery before the next stage is submitted, so a broken Coulomb matrix or an
  incomplete state space stops the loop *before* expensive LibRPA work.

The adapter is deliberately thin: the safety-critical bookkeeping (immutable
runs, duplicate-job protection, version pinning, promotion gates) lives in
``control.py``/``state.py`` and is reused, not reimplemented.
"""

from __future__ import annotations

import json
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from .fast_benchmark import FastCase
from .parameter_prescriptions import (
    ParameterPrescriptionError,
    apply_prescription,
    resolve_prescription_keys,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .stage_execution import LoginNodePolicy


class RemoteAdapterError(RuntimeError):
    """Raised when the adapter cannot stage or drive a candidate run."""


# Stages the adapter may drive, in execution order.
STAGE_ORDER = ("scf", "pyatb", "nscf", "preprocess", "librpa")


@dataclass(frozen=True)
class CaseSource:
    """Where a fast case's upstream inputs live and what they contain."""

    directory: Path
    abacus_inputs: bool
    staged_archive: Path | None

    @property
    def replayable_stages(self) -> tuple[str, ...]:
        """Stages this source can actually drive.

        A case with full ABACUS inputs runs the whole pipeline. A case that
        only ships a pre-staged LibRPA archive can run the LibRPA stage alone.
        """
        return STAGE_ORDER if self.abacus_inputs else ("librpa",)


def locate_case_source(case: FastCase, upstream_root: str | Path) -> CaseSource:
    """Resolve where a fast case's inputs live under the upstream suite root."""
    root = Path(upstream_root).expanduser().resolve()
    if case.upstream_directory is None:
        raise RemoteAdapterError(f"fast case {case.case_id} has no upstream directory")
    directory = root / case.upstream_directory
    if not directory.is_dir():
        raise RemoteAdapterError(
            f"upstream case directory is missing: {directory}"
        )
    archive = directory / "input_librpa.tar.gz"
    abacus_inputs = all(
        (directory / name).is_file()
        for name in ("INPUT_scf", "INPUT_nscf", "KPT_scf", "STRU")
    )
    return CaseSource(
        directory=directory,
        abacus_inputs=abacus_inputs,
        staged_archive=archive if archive.is_file() else None,
    )


def _apply_definition_to_inputs(bundle: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    """Rewrite the staged ABACUS/LibRPA inputs to reflect a candidate definition.

    Only parameters that map onto real input keys are written; anything else is
    reported as unapplied so the ledger can show what the candidate actually
    changed on disk. This is intentionally conservative: an unmapped axis must
    not silently pretend to have been applied.
    """
    applied: dict[str, Any] = {}
    unapplied: dict[str, Any] = {}

    # ABACUS INPUT_scf / INPUT_nscf key mapping.
    abacus_keys = {
        "nbands": "nbands",
        "exx_cs_inv_thr": "exx_cs_inv_thr",
        "shrink_threshold": "shrink_lu_inv_thr",
    }
    for axis, key in abacus_keys.items():
        if axis not in candidate:
            continue
        value = candidate[axis]
        if value is None:
            continue
        written = False
        for name in ("INPUT_scf", "INPUT_nscf"):
            path = bundle / name
            if not path.is_file():
                continue
            written = _upsert_abacus_key(path, key, value) or written
        if written:
            applied[axis] = value
        else:
            unapplied[axis] = value

    # LibRPA librpa.in key mapping.
    librpa_keys = {
        "nfreq": "nfreq",
        "abfs_family": None,
        "basis_family": None,
        "nao_family": None,
        "screening_kgrid": None,
    }
    path = bundle / "librpa.in"
    if path.is_file():
        for axis, key in librpa_keys.items():
            if axis not in candidate or key is None:
                continue
            value = candidate[axis]
            if value is None:
                continue
            if _upsert_librpa_key(path, key, value):
                applied[axis] = value
            else:
                unapplied[axis] = value

    # Axes with no direct single-key representation are reported as unapplied
    # rather than silently ignored.
    for axis in candidate:
        if axis not in applied and axis not in unapplied:
            unapplied[axis] = candidate[axis]

    return {"applied": applied, "unapplied": unapplied}


def _upsert_abacus_key(path: Path, key: str, value: Any) -> bool:
    """Set ``key value`` in an ABACUS INPUT file, replacing an existing entry."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    rendered = f"{key:<16}{value if not isinstance(value, list) else ' '.join(map(str, value))}"
    replaced = False
    out: list[str] = []
    for line in lines:
        stripped = line.split("#", 1)[0].strip()
        if stripped.split()[:1] == [key]:
            out.append(rendered)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(rendered)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def _upsert_librpa_key(path: Path, key: str, value: Any) -> bool:
    """Set ``key = value`` in a librpa.in file, replacing an existing entry."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    if isinstance(value, list):
        rendered_value = " ".join(str(item) for item in value)
    elif isinstance(value, bool):
        rendered_value = "t" if value else "f"
    else:
        rendered_value = str(value)
    rendered = f"{key} = {rendered_value}"
    replaced = False
    out: list[str] = []
    for line in lines:
        stripped = line.split("#", 1)[0].strip()
        if "=" in stripped and stripped.split("=", 1)[0].strip() == key:
            out.append(rendered)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(rendered)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return True


def stage_case_bundle(
    case: FastCase,
    *,
    upstream_root: str | Path,
    destination: str | Path,
    candidate: dict[str, Any],
    upstream_extras: Iterable[str] = (),
) -> dict[str, Any]:
    """Build an immutable, self-contained source bundle for one candidate.

    Copies the upstream inputs, expands the staged LibRPA archive when present,
    then rewrites the inputs to reflect ``candidate``. Returns a receipt with
    the applied/unapplied parameter report and the staged file list.
    """
    source = locate_case_source(case, upstream_root)
    target = Path(destination).expanduser()
    if target.exists():
        raise RemoteAdapterError(f"staging destination already exists: {target}")
    target.mkdir(parents=True)

    for item in sorted(source.directory.iterdir()):
        if item.is_dir() or item.name == "input_librpa.tar.gz":
            continue
        shutil.copy2(item, target / item.name)

    for extra in upstream_extras:
        candidate_path = source.directory / extra
        if candidate_path.is_file():
            shutil.copy2(candidate_path, target / candidate_path.name)

    if source.staged_archive is not None:
        with tarfile.open(source.staged_archive, "r:gz") as archive:
            # Guard against path traversal in the upstream archive, then extract
            # with an explicit ``data`` filter so Python 3.14's stricter default
            # does not change behaviour between interpreters.
            for member in archive.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise RemoteAdapterError(
                        f"staged archive contains an unsafe path: {member.name}"
                    )
            try:
                archive.extractall(path=target, filter="data")
            except TypeError:  # Python < 3.12 has no filter argument
                archive.extractall(path=target)

    # Upstream archives nest everything under input_librpa/; librpa.in points at
    # that directory, so leave the layout as the upstream case expects.
    report = _apply_definition_to_inputs(target, candidate)
    staged = sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file())
    return {
        "bundle": str(target),
        "stages": list(source.replayable_stages),
        "abacus_inputs": source.abacus_inputs,
        "applied": report["applied"],
        "unapplied": report["unapplied"],
        "staged_files": staged,
    }


class ControlledRunAdapter:
    """Drive the controlled executor and return reference-comparable outputs.

    The adapter is constructed with three injected callables so the loop can be
    exercised without a cluster while production wires in the real execution
    service:

      * ``materialize(bundle_dir, candidate) -> run_receipt``
      * ``run_stages(run_receipt, stages) -> {"status", "run_id", "diagnostics"}``
      * ``collect_outputs(run_receipt, file_names) -> {name: text}``

    Every callable is expected to be fail-closed: an unobservable stage must be
    reported as UNKNOWN rather than as success.
    """

    def __init__(
        self,
        *,
        case: FastCase,
        upstream_root: str | Path,
        staging_root: str | Path,
        materialize: Callable[[Path, dict[str, Any]], dict[str, Any]],
        run_stages: Callable[[dict[str, Any], tuple[str, ...]], dict[str, Any]],
        collect_outputs: Callable[[dict[str, Any], tuple[str, ...]], dict[str, str]],
    ) -> None:
        self.case = case
        self.upstream_root = Path(upstream_root).expanduser()
        self.staging_root = Path(staging_root).expanduser()
        self._materialize = materialize
        self._run_stages = run_stages
        self._collect_outputs = collect_outputs

    def _resolve_definition(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Merge the system-family prescription into the candidate definition.

        The prescription fills in the per-system parameters the candidate did
        not set explicitly, which is how "different systems need different
        input parameters" reaches the actual run.
        """
        keys = resolve_prescription_keys(self.case.case_id)
        if keys is None:
            return dict(candidate)
        route_id, family = keys
        try:
            result = apply_prescription(route_id, family, definition=candidate)
        except ParameterPrescriptionError:
            return dict(candidate)
        return dict(result["definition"])

    def run_candidate(
        self,
        *,
        case: FastCase,
        candidate: dict[str, Any],
        iteration: int,
    ) -> dict[str, Any]:
        definition = self._resolve_definition(candidate)
        bundle = self.staging_root / f"{case.case_id}-iter{iteration}"
        staging = stage_case_bundle(
            case,
            upstream_root=self.upstream_root,
            destination=bundle,
            candidate=definition,
        )
        stages = tuple(staging["stages"])

        receipt = self._materialize(bundle, definition)
        execution = self._run_stages(receipt, stages)
        status = execution.get("status", "UNKNOWN")

        observed: dict[str, str] = {}
        if status == "COMPLETED":
            observed = dict(
                self._collect_outputs(receipt, tuple(case.output_files))
            )

        return {
            "status": status,
            "observed": observed,
            "diagnostics": execution.get("diagnostics"),
            "run_id": execution.get("run_id") or receipt.get("run_id"),
            "detail": {
                "stages": list(stages),
                "applied": staging["applied"],
                "unapplied": staging["unapplied"],
                "resolved_definition": definition,
                "stage_detail": execution.get("detail"),
            },
        }


def summarize_collected_outputs(case: FastCase, run_dir: str | Path) -> dict[str, str]:
    """Collect a case's declared output files from a produced run directory.

    Only files the case declares are read, and a missing file is simply absent
    from the mapping so the evaluator reports NOT_EVALUATED instead of guessing.
    """
    root = Path(run_dir).expanduser()
    collected: dict[str, str] = {}
    for name in case.output_files:
        path = root / name
        if not path.is_file():
            continue
        try:
            collected[name] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return collected


def write_staging_receipt(staging: dict[str, Any], path: str | Path) -> Path:
    """Persist a staging receipt next to the bundle for auditability."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"schema": "oml.fast-stage-receipt.v1", **staging}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


# Terminal scheduler states. Anything else means the job is still running and
# must be polled again rather than treated as finished.
_TERMINAL_SCHEDULER_STATES = frozenset(
    {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY"}
)


class ControlledExecutionBinding:
    """Bind the loop onto ``ControlledExecutionService`` (the real cluster path).

    This is the production wiring for ``ControlledRunAdapter``: it prepares an
    immutable run for each candidate, submits every stage in order, waits for
    each stage to reach a terminal scheduler state, inspects it with the
    reference-free diagnostic battery, and collects the declared outputs.

    The binding is intentionally thin. Immutability, duplicate-job protection,
    binary pinning, and the pre-LibRPA validation gates already live in
    ``control.py``; this class only sequences them and translates the results
    into the adapter's ``{status, observed, diagnostics}`` contract.

    Requires a configured, approved ``ExecutionProfile``; without one the
    controlled service cannot resolve a scheduler or a remote run root.
    """

    def __init__(
        self,
        *,
        service: Any,
        poll_seconds: float = 30.0,
        max_polls: int = 240,
        plan_options: dict[str, Any] | None = None,
        sleep: Callable[[float], None] | None = None,
        login_node: "LoginNodePolicy | None" = None,
        login_node_runner: Callable[..., Any] | None = None,
        monitor_librpa: bool = True,
        monitor_poll_seconds: float = 30.0,
        monitor_max_polls: int = 120,
    ) -> None:
        self.service = service
        self.poll_seconds = poll_seconds
        self.max_polls = max_polls
        self.plan_options = plan_options or {}
        self._sleep = sleep
        self.login_node = login_node
        self._login_node_runner = login_node_runner
        self.monitor_librpa = monitor_librpa
        self.monitor_poll_seconds = monitor_poll_seconds
        self.monitor_max_polls = monitor_max_polls

    # -- plan + materialize -------------------------------------------------
    def materialize(self, bundle: Path, definition: dict[str, Any]) -> dict[str, Any]:
        """Create the plan and prepare an immutable run for a staged bundle."""
        from .planner import plan_case

        plan = plan_case(bundle, **self.plan_options)
        receipt = self.service.prepare_run(bundle, plan.digest)
        return {
            "run_id": receipt["run_id"],
            "plan_digest": plan.digest,
            "local_run_dir": receipt.get("local_run_dir"),
            "remote_run_dir": receipt.get("remote_run_dir"),
            "bundle": str(bundle),
        }

    # -- stage execution ----------------------------------------------------
    def _await_stage(self, run_id: str, attempt_id: str) -> dict[str, Any]:
        """Poll one attempt until it reaches a terminal scheduler state."""
        import time

        sleep = self._sleep or time.sleep
        last: dict[str, Any] = {}
        for _ in range(self.max_polls):
            last = self.service.get_status(run_id, attempt_id)
            attempt = last.get("attempt") or {}
            state = str(attempt.get("status") or "").upper()
            scheduler = last.get("scheduler") or {}
            normalized = str(scheduler.get("normalized_state") or "").upper()
            if state in {"PASSED"}:
                return {"reached": "PASSED", "observation": last}
            if state in {"FAILED", "CANCELLED"}:
                return {"reached": state, "observation": last}
            if normalized in _TERMINAL_SCHEDULER_STATES:
                return {"reached": normalized, "observation": last}
            sleep(self.poll_seconds)
        # Never assume success on a timeout: an unobserved stage is UNKNOWN.
        return {"reached": "UNKNOWN", "observation": last}

    def run_stages(
        self, receipt: dict[str, Any], stages: tuple[str, ...]
    ) -> dict[str, Any]:
        """Run every stage, placing fast work on the login node and gating each step.

        Sequence for each stage:
          1. ``librpa`` preflights ``librpa.in`` before any compute is spent.
          2. Fast stages run directly on the login node when policy allows;
             heavy stages go to the scheduler.
          3. Each stage is inspected with the reference-free gate battery.
          4. The LibRPA stage is monitored live while it runs.

        The pipeline stops at the first failure so a broken early stage never
        buys an expensive later one.
        """
        from .stage_execution import (
            LoginNodePolicy,
            monitor_librpa_until_settled,
            plan_stage_placement,
            preflight_librpa_input,
            render_login_node_script,
            run_login_node_stage,
        )

        run_id = receipt["run_id"]
        plan_digest = receipt["plan_digest"]
        detail: list[dict[str, Any]] = []
        diagnostics: dict[str, Any] | None = None

        policy = self.login_node or LoginNodePolicy(enabled=False)
        placements = {p.stage: p for p in plan_stage_placement(stages, login_node=policy)}

        for stage in stages:
            placement = placements[stage]

            # LibRPA is expensive and most likely to fail on bad inputs, so
            # validate its input contract before spending any compute on it.
            if stage == "librpa":
                local_dir = receipt.get("local_run_dir")
                if local_dir:
                    preflight = preflight_librpa_input(
                        local_dir, **self.plan_options
                    )
                    detail.append(
                        {
                            "stage": stage,
                            "step": "preflight",
                            "status": preflight["status"],
                            "failed_gates": preflight["failed_gates"],
                        }
                    )
                    if not preflight["accepted"]:
                        return {
                            "status": "FAILED",
                            "run_id": run_id,
                            "diagnostics": {
                                "status": "FAIL",
                                "stage": stage,
                                "reason": "librpa.in preflight failed",
                                "failed_gates": preflight["failed_gates"],
                                "gates": preflight["gates"],
                            },
                            "detail": detail,
                        }

            if placement.mode == "login_node":
                script = render_login_node_script(
                    stage,
                    runtime=self._login_node_runtime(),
                    run_id=run_id,
                    attempt_id=f"login-{run_id}-{stage}",
                )
                outcome = run_login_node_stage(
                    stage=stage,
                    run_dir=receipt.get("remote_run_dir") or receipt.get("local_run_dir") or ".",
                    script=script,
                    ssh_host=policy.ssh_host or "",
                    ssh_program=policy.ssh_program,
                    timeout_seconds=policy.timeout_seconds,
                    runner=self._login_node_runner,
                )
                detail.append(
                    {
                        "stage": stage,
                        "placement": placement.to_dict(),
                        "outcome": outcome.status,
                        "exit_code": outcome.exit_code,
                    }
                )
                if outcome.status != "COMPLETED":
                    return {
                        "status": "FAILED",
                        "run_id": run_id,
                        "diagnostics": diagnostics,
                        "detail": detail,
                    }
                inspection = self._inspect_login_stage(receipt, stage)
                accepted = bool(inspection.get("accepted"))
                if not accepted:
                    diagnostics = {
                        "status": "FAIL",
                        "stage": stage,
                        "counts": inspection.get("counts"),
                        "gates": inspection.get("gates", []),
                    }
                    return {
                        "status": "COMPLETED",
                        "run_id": run_id,
                        "diagnostics": diagnostics,
                        "detail": detail,
                    }
                diagnostics = {"status": "PASS", "stage": stage, "counts": inspection.get("counts")}
                continue

            attempt = self.service.submit_stage(run_id, stage, plan_digest)
            attempt_id = attempt["attempt_id"]

            # A long LibRPA job is monitored while it runs, so a wedge or a
            # blow-up is caught during the run instead of after the wall clock.
            if stage == "librpa" and self.monitor_librpa:
                monitor_root = receipt.get("local_run_dir") or receipt.get("remote_run_dir")
                if monitor_root:
                    verdict = monitor_librpa_until_settled(
                        monitor_root,
                        poll_seconds=self.monitor_poll_seconds,
                        max_polls=self.monitor_max_polls,
                        sleep=self._sleep,
                    )
                    detail.append({"stage": stage, "step": "monitor", **verdict.to_dict()})
                    if verdict.state in {"FAILING", "STALLED"}:
                        return {
                            "status": "FAILED",
                            "run_id": run_id,
                            "diagnostics": {
                                "status": "FAIL",
                                "stage": stage,
                                "reason": f"live LibRPA monitor reported {verdict.state}",
                                "monitor": verdict.to_dict(),
                            },
                            "detail": detail,
                        }

            outcome = self._await_stage(run_id, attempt_id)
            if outcome["reached"] != "PASSED":
                detail.append(
                    {"stage": stage, "attempt_id": attempt_id, "outcome": outcome["reached"]}
                )
                return {
                    "status": "FAILED",
                    "run_id": run_id,
                    "diagnostics": diagnostics,
                    "detail": detail,
                }

            inspection = self.service.inspect_stage(run_id, attempt_id, plan_digest)
            accepted = bool(inspection.get("accepted"))
            detail.append(
                {
                    "stage": stage,
                    "attempt_id": attempt_id,
                    "placement": placement.to_dict(),
                    "outcome": "PASSED",
                    "accepted": accepted,
                    "counts": inspection.get("counts"),
                }
            )
            if not accepted:
                # A stage that ran but failed its gates is a diagnostic failure,
                # and the loop must not continue to the next expensive stage.
                diagnostics = {
                    "status": "FAIL",
                    "stage": stage,
                    "counts": inspection.get("counts"),
                    "gates": inspection.get("gates", []),
                }
                return {
                    "status": "COMPLETED",
                    "run_id": run_id,
                    "diagnostics": diagnostics,
                    "detail": detail,
                }
            diagnostics = {
                "status": "PASS",
                "stage": stage,
                "counts": inspection.get("counts"),
            }

        return {
            "status": "COMPLETED",
            "run_id": run_id,
            "diagnostics": diagnostics,
            "detail": detail,
        }

    def _login_node_runtime(self) -> dict[str, Any]:
        """Runtime paths the login-node stage script needs."""
        runtime = dict(self.plan_options.get("runtime") or {})
        defaults = {
            "python": "python3",
            "mpi_launcher": "mpirun",
            "abacus": "abacus",
            "librpa": "chi0_main.exe",
            "mpi_ranks": 1,
            "pyatb_mpi_ranks": 1,
            "omp_threads": 1,
        }
        defaults.update(runtime)
        return defaults

    def _inspect_login_stage(self, receipt: dict[str, Any], stage: str) -> dict[str, Any]:
        """Inspect a login-node stage with the shared gate battery.

        The login-node script writes the same command receipt as the scheduled
        path, so the identical gates apply; a caller may still inject a custom
        inspector through ``plan_options["inspect_login_stage"]``.
        """
        inspector = self.plan_options.get("inspect_login_stage")
        root = receipt.get("local_run_dir") or receipt.get("remote_run_dir")
        if inspector is not None:
            return inspector(root, stage)
        if not root:
            return {"accepted": False, "counts": {"FAIL": 1}, "gates": []}
        from .stage_inspection import inspect_stage_outputs

        return inspect_stage_outputs(root, stage)

    # -- artifact collection ------------------------------------------------
    def collect_outputs(
        self, receipt: dict[str, Any], file_names: tuple[str, ...]
    ) -> dict[str, str]:
        """Read declared outputs from the prepared local run directory."""
        root = receipt.get("local_run_dir")
        if not root:
            return {}
        collected: dict[str, str] = {}
        for name in file_names:
            path = Path(root) / name
            if not path.is_file():
                continue
            try:
                collected[name] = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
        return collected


def build_controlled_adapter(
    *,
    case: FastCase,
    service: Any,
    upstream_root: str | Path,
    staging_root: str | Path,
    plan_options: dict[str, Any] | None = None,
    poll_seconds: float = 30.0,
    max_polls: int = 240,
    sleep: Callable[[float], None] | None = None,
    login_node: "LoginNodePolicy | None" = None,
    login_node_runner: Callable[..., Any] | None = None,
    monitor_librpa_live: bool = True,
) -> ControlledRunAdapter:
    """Wire a fast case onto the real controlled execution service.

    Passing a ``login_node`` policy lets the cheap stages (nscf, pyatb,
    preprocess) run directly on the login node instead of waiting in the
    scheduler queue; ``scf`` and ``librpa`` always stay on the scheduler.
    """
    binding = ControlledExecutionBinding(
        service=service,
        poll_seconds=poll_seconds,
        max_polls=max_polls,
        plan_options=plan_options,
        sleep=sleep,
        login_node=login_node,
        login_node_runner=login_node_runner,
        monitor_librpa=monitor_librpa_live,
    )
    return ControlledRunAdapter(
        case=case,
        upstream_root=upstream_root,
        staging_root=staging_root,
        materialize=binding.materialize,
        run_stages=binding.run_stages,
        collect_outputs=binding.collect_outputs,
    )
