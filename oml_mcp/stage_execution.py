"""Stage placement, login-node execution, LibRPA preflight and live monitoring.

Fast stages do not need a scheduler
-----------------------------------
``nscf``, ``pyatb`` and ``preprocess`` are seconds-to-minutes work on a small
cell. Sending them through Slurm costs far more in queue latency than the work
itself, so this module lets them run directly on a remote login node while
``scf`` and ``librpa`` stay on the scheduler. That is the "run it on the login
node because it is very fast" rule, made explicit and auditable instead of
being an operator habit.

The placement decision is data, not a hidden default: ``STAGE_EXECUTION_MODES``
records where each stage is allowed to run, and ``plan_stage_placement`` turns a
stage list plus a policy into an explicit plan the caller can inspect.

Three guarantees are preserved regardless of placement
-----------------------------------------------------
1. **One body per stage.** The login-node path renders the *same* stage body as
   the scheduled path, so the two cannot drift apart.
2. **The same command receipt.** A login-node stage writes
   ``.oml/stage-results/<stage>.status`` in the identical format, so the whole
   existing ``inspect_stage_outputs`` gate battery applies unchanged.
3. **Never a silent pass.** A stage that cannot be observed is reported as
   UNKNOWN, and a monitor that sees no evidence of progress says so rather than
   assuming the job is healthy.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .stage_templates import CONTROLLED_PERIODIC_STAGES, stage_body


# Where each controlled stage is allowed to run.
#
#   "login_node" - cheap enough that scheduler latency dominates the real cost
#   "scheduler"  - heavy enough to need an allocation
STAGE_EXECUTION_MODES: dict[str, str] = {
    "scf": "scheduler",
    "pyatb": "login_node",
    "nscf": "login_node",
    "preprocess": "login_node",
    "librpa": "scheduler",
}

VALID_EXECUTION_MODES = frozenset({"login_node", "scheduler"})

# Markers that mean LibRPA is already in trouble. These are matched against the
# live output stream while the job runs.
LIBRPA_FAILURE_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mpi_error", re.compile(r"Error on MPI", re.I)),
    ("librpa_failed", re.compile(r"Error:\s*libRPA failed", re.I)),
    ("segfault", re.compile(r"Segmentation fault|SIGSEGV", re.I)),
    ("bad_termination", re.compile(r"BAD TERMINATION", re.I)),
    ("inverse_matrix", re.compile(r"Inverse_Matrix\.hpp", re.I)),
    ("nan_or_inf", re.compile(r"(?<![A-Za-z])(?:nan|[+-]?inf(?:inity)?)(?![A-Za-z])", re.I)),
    ("out_of_range", re.compile(r"std::out_of_range|map::at", re.I)),
)

# Markers that mean LibRPA is progressing normally.
LIBRPA_PROGRESS_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("timer_stop", re.compile(r"Timer stop:\s+total\.", re.I)),
    ("finished", re.compile(r"libRPA finished successfully", re.I)),
)

LOGIN_NODE_MARKER = "#OML_LOGIN_NODE=1"


class StageExecutionError(ValueError):
    """Raised when a stage placement or login-node run is misconfigured."""


@dataclass(frozen=True)
class LoginNodePolicy:
    """How fast stages may run directly on a login node."""

    enabled: bool = True
    allowed_stages: tuple[str, ...] = ("pyatb", "nscf", "preprocess")
    timeout_seconds: int = 3600
    ssh_program: str = "ssh"
    ssh_host: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int)
            or self.timeout_seconds <= 0
        ):
            raise StageExecutionError("login-node timeout_seconds must be a positive integer")
        for stage in self.allowed_stages:
            if stage not in CONTROLLED_PERIODIC_STAGES:
                raise StageExecutionError(f"unknown stage in login-node policy: {stage}")
            if STAGE_EXECUTION_MODES[stage] != "login_node":
                raise StageExecutionError(
                    f"stage {stage} is not eligible for login-node execution"
                )
        if self.enabled and not self.ssh_host:
            raise StageExecutionError(
                "login-node execution requires an ssh_host; refusing to run stages silently locally"
            )


@dataclass(frozen=True)
class StagePlacement:
    """Where one stage of a plan will run."""

    stage: str
    mode: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "mode": self.mode, "reason": self.reason}


def plan_stage_placement(
    stages: Iterable[str],
    *,
    login_node: LoginNodePolicy | None = None,
) -> tuple[StagePlacement, ...]:
    """Decide where each stage runs, with an explicit reason per stage.

    Login-node execution is used only when the policy enables it AND the stage
    is on the policy's allow-list AND the stage is intrinsically cheap. Falling
    back to the scheduler is always safe, so any missing condition degrades to
    the scheduler rather than to an unmonitored local run.
    """
    policy = login_node or LoginNodePolicy(enabled=False)
    placements: list[StagePlacement] = []
    for stage in stages:
        if stage not in CONTROLLED_PERIODIC_STAGES:
            raise StageExecutionError(f"unsupported controlled stage: {stage}")
        intrinsic = STAGE_EXECUTION_MODES[stage]
        if intrinsic != "login_node":
            placements.append(
                StagePlacement(
                    stage, "scheduler", "stage is heavy and requires an allocation"
                )
            )
            continue
        if not policy.enabled:
            placements.append(
                StagePlacement(stage, "scheduler", "login-node execution is disabled by policy")
            )
            continue
        if stage not in policy.allowed_stages:
            placements.append(
                StagePlacement(
                    stage, "scheduler", "stage is not on the login-node allow-list"
                )
            )
            continue
        placements.append(
            StagePlacement(
                stage,
                "login_node",
                "stage is cheap enough that scheduler latency dominates its runtime",
            )
        )
    return tuple(placements)


def render_login_node_script(
    stage: str,
    *,
    runtime: Mapping[str, str | int],
    run_id: str,
    attempt_id: str,
) -> str:
    """Render a login-node stage script that matches the controlled contract.

    The script writes the same receipt as the scheduled path, so the existing
    stage-inspection gates apply without modification.
    """
    if stage not in CONTROLLED_PERIODIC_STAGES:
        raise StageExecutionError(f"unsupported controlled stage: {stage}")
    if STAGE_EXECUTION_MODES[stage] != "login_node":
        raise StageExecutionError(
            f"stage {stage} is not eligible for login-node execution"
        )
    from .stage_templates import render_env

    env = render_env(runtime, environment={}, run_id=run_id, plan_digest=attempt_id)
    return f"""#!/usr/bin/env bash
{LOGIN_NODE_MARKER}
set -uo pipefail
run_dir="$(pwd -P)"
cd "$run_dir"
{env}export PYTHONDONTWRITEBYTECODE=1
mkdir -p ".oml/stage-results"
printf 'RUNNING:{attempt_id}\\n' > ".oml/stage-results/{stage}.status"
status=0
{stage_body(stage)}
status=$?
if [[ $status -eq 0 ]]; then
  printf 'COMMAND_COMPLETED:{attempt_id}\\n' > ".oml/stage-results/{stage}.status"
else
  printf 'COMMAND_FAILED:%s:{attempt_id}\\n' "$status" > ".oml/stage-results/{stage}.status"
fi
exit $status
"""


@dataclass
class LoginNodeResult:
    """Outcome of one login-node stage execution."""

    stage: str
    exit_code: int | None
    stdout: str
    stderr: str
    observed: bool
    duration_seconds: float

    @property
    def status(self) -> str:
        if not self.observed:
            return "UNKNOWN"
        return "COMPLETED" if self.exit_code == 0 else "FAILED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "exit_code": self.exit_code,
            "observed": self.observed,
            "duration_seconds": self.duration_seconds,
        }


def run_login_node_stage(
    *,
    stage: str,
    run_dir: str | Path,
    script: str,
    ssh_host: str,
    ssh_program: str = "ssh",
    timeout_seconds: int = 3600,
    runner: Callable[[list[str], str, int], tuple[int, str, str]] | None = None,
) -> LoginNodeResult:
    """Run a fast stage directly on a login node and report what happened.

    ``runner`` is injected so the sequencing is testable without a cluster. The
    default runner executes ``bash -s`` over SSH in the remote run directory.
    The script is fed on stdin, so no temporary file has to be staged remotely.
    """
    if STAGE_EXECUTION_MODES[stage] != "login_node":
        raise StageExecutionError(
            f"stage {stage} is not eligible for login-node execution"
        )
    remote = f"cd {run_dir!s} && bash -s"
    argv = [ssh_program, ssh_host, remote]
    started = time.monotonic()
    if runner is None:
        runner = _default_ssh_runner
    exit_code, stdout, stderr = runner(argv, script, timeout_seconds)
    duration = time.monotonic() - started
    observed = exit_code is not None
    return LoginNodeResult(
        stage=stage,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        observed=observed,
        duration_seconds=duration,
    )


def _default_ssh_runner(
    argv: list[str], script: str, timeout_seconds: int
) -> tuple[int | None, str, str]:
    """Execute a stage script over SSH, treating a timeout as unobserved."""
    import subprocess

    try:
        completed = subprocess.run(
            argv,
            input=script,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # A timeout means the outcome is unknown, never success.
        return None, exc.stdout or "", exc.stderr or ""
    return completed.returncode, completed.stdout, completed.stderr


# ---------------------------------------------------------------------------
# LibRPA input preflight
# ---------------------------------------------------------------------------


def preflight_librpa_input(
    case_root: str | Path,
    *,
    task: str = "gw",
    system_type: str = "solid",
    use_symmetry: bool = False,
    soc: bool = False,
    headwing: bool | None = None,
    response_method: str = "sos",
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Validate ``librpa.in`` and the paired ABACUS inputs before any compute.

    This exposes the existing ``validate_case(stage="input")`` battery as a
    single gate report so a caller can refuse to spend compute on inputs that
    are already known to be inconsistent. It is a preflight: it never submits.
    """
    from .validators import validate_case

    report = validate_case(
        case_root,
        task=task,
        system_type=system_type,
        use_symmetry=use_symmetry,
        soc=soc,
        headwing=headwing,
        stage="input",
        response_method=response_method,
        profile_id=profile_id,
    )
    gates = [gate.to_dict() for gate in report.gates]
    failed = [gate["gate_id"] for gate in gates if gate["status"] == "FAIL"]
    warned = [gate["gate_id"] for gate in gates if gate["status"] == "WARN"]
    return {
        "schema": "oml.librpa-preflight.v1",
        "profile_id": report.profile_id,
        "accepted": report.accepted,
        "status": "FAIL" if failed else "PASS",
        "failed_gates": failed,
        "warned_gates": warned,
        "gates": gates,
    }


# ---------------------------------------------------------------------------
# LibRPA live monitoring
# ---------------------------------------------------------------------------


@dataclass
class LibrpaMonitorVerdict:
    """What a live LibRPA output stream currently shows."""

    state: str
    failure_markers: tuple[str, ...] = ()
    progress_markers: tuple[str, ...] = ()
    stalled: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "failure_markers": list(self.failure_markers),
            "progress_markers": list(self.progress_markers),
            "stalled": self.stalled,
            "detail": self.detail,
        }


def _librpa_log_paths(root: Path) -> tuple[Path, ...]:
    found = (
        *sorted(root.glob("librpa_para_nprocs_*_myid_*.out")),
        *sorted(root.glob("LibRPA*.out")),
        *sorted(root.glob("librpa*.out")),
    )
    return tuple(dict.fromkeys(path for path in found if path.is_file()))


def monitor_librpa(
    run_dir: str | Path,
    *,
    previous_size: int | None = None,
    stall_seconds: float | None = None,
    now: float | None = None,
) -> LibrpaMonitorVerdict:
    """Inspect the live LibRPA output and report whether it looks healthy.

    The monitor answers the "will LibRPA go wrong while it runs" question with
    evidence rather than optimism:

      * a failure marker in any rank log   -> ``FAILING``
      * a clean completion marker          -> ``FINISHED``
      * output present and still growing   -> ``RUNNING``
      * no failure, no progress, and the output has stopped growing for
        ``stall_seconds``                  -> ``STALLED``
      * no readable output at all          -> ``UNOBSERVED``
    """
    root = Path(run_dir).expanduser()
    logs = _librpa_log_paths(root)
    if not logs:
        return LibrpaMonitorVerdict(
            state="UNOBSERVED",
            detail={"reason": "no LibRPA rank output files were found", "root": str(root)},
        )

    total_size = 0
    texts: dict[str, str] = {}
    for path in logs:
        try:
            texts[str(path)] = path.read_text(encoding="utf-8", errors="replace")
            total_size += path.stat().st_size
        except OSError:
            continue

    failures: list[str] = []
    progress: list[str] = []
    for path, text in texts.items():
        for label, pattern in LIBRPA_FAILURE_MARKERS:
            if pattern.search(text):
                failures.append(f"{label}:{Path(path).name}")
        for label, pattern in LIBRPA_PROGRESS_MARKERS:
            if pattern.search(text):
                progress.append(f"{label}:{Path(path).name}")

    detail: dict[str, Any] = {
        "log_count": len(texts),
        "total_size": total_size,
        "previous_size": previous_size,
    }

    finished = any(item.startswith("finished") or item.startswith("timer_stop") for item in progress)
    if failures:
        return LibrpaMonitorVerdict(
            state="FAILING",
            failure_markers=tuple(failures),
            progress_markers=tuple(progress),
            detail=detail,
        )
    if finished:
        return LibrpaMonitorVerdict(
            state="FINISHED",
            progress_markers=tuple(progress),
            detail=detail,
        )

    stalled = False
    if previous_size is not None and previous_size == total_size:
        stalled = True
    detail["stall_seconds"] = stall_seconds
    detail["observed_at"] = now
    if stalled:
        return LibrpaMonitorVerdict(
            state="STALLED",
            progress_markers=tuple(progress),
            stalled=True,
            detail=detail,
        )
    return LibrpaMonitorVerdict(
        state="RUNNING",
        progress_markers=tuple(progress),
        detail=detail,
    )


def monitor_librpa_until_settled(
    run_dir: str | Path,
    *,
    poll_seconds: float = 30.0,
    max_polls: int = 120,
    sleep: Callable[[float], None] | None = None,
) -> LibrpaMonitorVerdict:
    """Poll the live LibRPA output until it finishes, fails, stalls or times out.

    Two consecutive identical sizes count as a stall, so a wedged job is
    reported instead of being waited on until the wall clock runs out.
    """
    sleep = sleep or time.sleep
    previous: int | None = None
    same_size_polls = 0
    verdict = LibrpaMonitorVerdict(state="UNOBSERVED")
    for _ in range(max_polls):
        verdict = monitor_librpa(run_dir, previous_size=previous)
        if verdict.state in {"FAILING", "FINISHED"}:
            return verdict
        if verdict.state == "UNOBSERVED":
            sleep(poll_seconds)
            continue
        if verdict.state == "STALLED":
            same_size_polls += 1
            # Require two consecutive stalled polls so a slow flush is not
            # mistaken for a wedge.
            if same_size_polls >= 2:
                return verdict
        else:
            same_size_polls = 0
        previous = verdict.detail.get("total_size")
        sleep(poll_seconds)
    return verdict


__all__ = [
    "STAGE_EXECUTION_MODES",
    "LIBRPA_FAILURE_MARKERS",
    "LIBRPA_PROGRESS_MARKERS",
    "LoginNodePolicy",
    "LoginNodeResult",
    "LibrpaMonitorVerdict",
    "StageExecutionError",
    "StagePlacement",
    "monitor_librpa",
    "monitor_librpa_until_settled",
    "plan_stage_placement",
    "preflight_librpa_input",
    "render_login_node_script",
    "run_login_node_stage",
]
