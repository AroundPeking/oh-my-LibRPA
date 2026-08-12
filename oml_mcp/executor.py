from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .errors import OMLError
from .execution_profiles import ExecutionProfile
from .profiles import load_profile
from .stage_templates import CONTROLLED_PERIODIC_STAGES


SCHEDULER_ID_PATTERN = re.compile(r"^(\d+)(?:;[^\s]+)?$")
NORMALIZED_STATES = {
    "PENDING": "PENDING",
    "CONFIGURING": "PENDING",
    "RUNNING": "RUNNING",
    "COMPLETING": "RUNNING",
    "COMPLETED": "COMPLETED",
    "FAILED": "FAILED",
    "TIMEOUT": "FAILED",
    "NODE_FAIL": "FAILED",
    "OUT_OF_MEMORY": "FAILED",
    "CANCELLED": "CANCELLED",
    "PREEMPTED": "CANCELLED",
}


class SlurmExecutor:
    def __init__(self, profile: ExecutionProfile, *, timeout_seconds: int = 20) -> None:
        self.profile = profile
        self.timeout_seconds = timeout_seconds

    def _run(self, arguments: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                arguments,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OMLError(
                "SUBMISSION_AMBIGUOUS",
                "scheduler command timed out before its result could be reconciled",
                evidence=tuple(str(item) for item in arguments[:2]),
                recovery="query the scheduler for the recorded run and stage before retrying",
            ) from exc
        except OSError as exc:
            raise OMLError(
                "SCHEDULER_UNOBSERVABLE",
                f"cannot start the configured scheduler adapter: {exc}",
                evidence=(arguments[0],),
                recovery="repair the administrator-managed execution profile",
            ) from exc

    def sync_run(self, local_run_dir: Path, remote_run_dir: str | None) -> None:
        if self.profile.transport == "local":
            return
        if self.profile.ssh is None or remote_run_dir is None:
            raise OMLError(
                "PROFILE_INVALID",
                "SSH execution requires a registered remote run directory",
                evidence=(self.profile.profile_id,),
                recovery="repair the execution profile and prepare a fresh run",
            )
        ssh = self.profile.ssh
        create = self._run(
            [ssh["ssh_program"], ssh["host"], "mkdir", "-p", "--", remote_run_dir]
        )
        if create.returncode != 0:
            raise OMLError(
                "REMOTE_PREPARE_FAILED",
                "failed to create the bounded remote run directory",
                evidence=(create.stderr.strip(), remote_run_dir),
                recovery="check the approved SSH profile and remote root permissions",
            )
        transfer = self._run(
            [
                ssh["rsync_program"],
                "-a",
                "--",
                f"{local_run_dir}/",
                f"{ssh['host']}:{remote_run_dir}/",
            ]
        )
        if transfer.returncode != 0:
            raise OMLError(
                "REMOTE_PREPARE_FAILED",
                "failed to synchronize the immutable run bundle",
                evidence=(transfer.stderr.strip(), str(local_run_dir), remote_run_dir),
                recovery="inspect rsync/SSH access; do not submit until the existing run is reconciled",
            )

    def snapshot_run(self, remote_run_dir: str | None, snapshot_dir: Path) -> None:
        if self.profile.transport != "ssh" or self.profile.ssh is None or remote_run_dir is None:
            raise OMLError(
                "PROFILE_INVALID",
                "remote snapshots require a complete SSH execution profile",
                evidence=(self.profile.profile_id,),
                recovery="repair the execution profile before inspecting remote artifacts",
            )
        if snapshot_dir.exists():
            raise OMLError(
                "SNAPSHOT_CONFLICT",
                "inspection snapshot already exists",
                evidence=(str(snapshot_dir),),
                recovery="preserve the immutable snapshot and use its existing inspection receipt",
            )
        snapshot_dir.mkdir(parents=True, mode=0o700)
        result = self._run(
            [
                self.profile.ssh["rsync_program"],
                "-a",
                "--",
                f"{self.profile.ssh['host']}:{remote_run_dir}/",
                f"{snapshot_dir}/",
            ]
        )
        if result.returncode != 0:
            try:
                snapshot_dir.rmdir()
            except OSError:
                pass
            raise OMLError(
                "SNAPSHOT_FAILED",
                "failed to create a bounded remote output snapshot",
                evidence=(result.stderr.strip(), remote_run_dir, str(snapshot_dir)),
                recovery="repair SSH/rsync observation access before inspecting the stage",
            )

    def verify_versions(self) -> dict[str, Any]:
        pinned = load_profile()["components"]
        components: dict[str, dict[str, str]] = {}
        for name in ("abacus", "librpa", "pyatb"):
            arguments = [
                self.profile.sources["git_program"],
                "-C",
                self.profile.sources[name],
                "rev-parse",
                "HEAD",
            ]
            if self.profile.transport == "ssh":
                assert self.profile.ssh is not None
                arguments = [self.profile.ssh["ssh_program"], self.profile.ssh["host"], *arguments]
            result = self._run(arguments)
            actual = result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else ""
            expected = pinned[name]["revision"]
            components[name] = {
                "source_path": self.profile.sources[name],
                "expected_revision": expected,
                "actual_revision": actual,
                "match": str(actual == expected).lower(),
            }
            if actual != expected:
                raise OMLError(
                    "VERSION_MISMATCH",
                    f"{name} source revision does not match the pinned OML profile",
                    evidence=(self.profile.sources[name], expected, actual or result.stderr.strip()),
                    recovery="build or select the pinned source revision before controlled execution",
                    details={"components": components},
                )
        return {"verdict": "match", "components": components}

    def verify_remote_bundle(self, local_run_dir: Path, remote_run_dir: str | None) -> dict[str, str]:
        if self.profile.transport != "ssh" or self.profile.ssh is None or remote_run_dir is None:
            return {"verdict": "not_applicable", "transport": self.profile.transport}
        result = self._run(
            [
                self.profile.ssh["rsync_program"],
                "-r",
                "--dry-run",
                "--checksum",
                "--itemize-changes",
                "--exclude=.oml/snapshots/",
                "--",
                f"{local_run_dir}/",
                f"{self.profile.ssh['host']}:{remote_run_dir}/",
            ]
        )
        changes = result.stdout.strip()
        if result.returncode != 0 or changes:
            raise OMLError(
                "REMOTE_MANIFEST_MISMATCH",
                "remote run bundle differs from the locally verified immutable bundle",
                evidence=(changes or result.stderr.strip(), str(local_run_dir), remote_run_dir),
                recovery="do not submit; reconcile or prepare a fresh remote run bundle",
            )
        return {"verdict": "match", "remote_run_dir": remote_run_dir}

    def submit(self, local_run_dir: Path, stage: str, *, remote_run_dir: str | None) -> str:
        if stage not in CONTROLLED_PERIODIC_STAGES:
            raise OMLError(
                "STATE_TRANSITION_DENIED",
                f"unsupported controlled stage: {stage}",
                evidence=(stage,),
                recovery="submit only a stage listed in the immutable periodic GW plan",
            )
        relative_script = Path(".oml") / "stages" / f"{stage}.slurm"
        local_script = local_run_dir / relative_script
        if not local_script.is_file():
            raise OMLError(
                "STAGE_SCRIPT_MISSING",
                "generated stage script is missing",
                evidence=(str(local_script),),
                recovery="do not recreate it manually; prepare a fresh run from the immutable plan",
            )

        submit_program = self.profile.scheduler["submit_program"]
        if self.profile.transport == "local":
            result = self._run(
                [submit_program, "--parsable", relative_script.as_posix()],
                cwd=local_run_dir,
            )
        else:
            if self.profile.ssh is None or remote_run_dir is None:
                raise OMLError(
                    "PROFILE_INVALID",
                    "SSH execution requires a registered remote run directory",
                    evidence=(self.profile.profile_id,),
                    recovery="repair the execution profile and prepare a fresh run",
                )
            remote_script = str(Path(remote_run_dir) / relative_script)
            result = self._run(
                [
                    self.profile.ssh["ssh_program"],
                    self.profile.ssh["host"],
                    submit_program,
                    "--parsable",
                    f"--chdir={remote_run_dir}",
                    remote_script,
                ]
            )
        if result.returncode != 0:
            raise OMLError(
                "SUBMISSION_FAILED",
                "scheduler rejected the generated stage script",
                evidence=(result.stderr.strip(), stage),
                recovery="inspect the scheduler message and execution profile before a reviewed retry",
            )
        output = result.stdout.strip().splitlines()
        match = SCHEDULER_ID_PATTERN.fullmatch(output[-1].strip()) if output else None
        if match is None:
            raise OMLError(
                "SUBMISSION_AMBIGUOUS",
                "scheduler returned no unambiguous numeric job ID",
                evidence=(result.stdout.strip(), result.stderr.strip()),
                recovery="reconcile the scheduler by run/stage identity before retrying",
            )
        return match.group(1)

    def status(self, scheduler_id: str) -> dict[str, Any]:
        if not scheduler_id.isdigit():
            raise OMLError(
                "SCHEDULER_ID_INVALID",
                "scheduler ID must contain digits only",
                evidence=(scheduler_id,),
                recovery="use the scheduler ID stored in the stage attempt receipt",
            )
        status_program = self.profile.scheduler["status_program"]
        arguments = [status_program, "-h", "-j", scheduler_id, "-o", "%T"]
        if self.profile.transport == "ssh":
            if self.profile.ssh is None:
                raise OMLError(
                    "PROFILE_INVALID",
                    "SSH execution profile is incomplete",
                    evidence=(self.profile.profile_id,),
                    recovery="repair the execution profile",
                )
            arguments = [self.profile.ssh["ssh_program"], self.profile.ssh["host"], *arguments]
        try:
            result = self._run(arguments)
        except OMLError as exc:
            if exc.code not in {"SUBMISSION_AMBIGUOUS", "SCHEDULER_UNOBSERVABLE"}:
                raise
            return {
                "normalized_state": "UNKNOWN",
                "raw_state": "",
                "source": "squeue",
                "error_code": "SCHEDULER_UNOBSERVABLE",
            }
        if result.returncode != 0:
            return {
                "normalized_state": "UNKNOWN",
                "raw_state": result.stderr.strip(),
                "source": "squeue",
                "error_code": "SCHEDULER_UNOBSERVABLE",
            }
        raw = result.stdout.strip().splitlines()
        if not raw:
            return self._history_status(scheduler_id)
        raw_state = raw[0].strip().upper().split()[0]
        normalized = NORMALIZED_STATES.get(raw_state, "UNKNOWN")
        observation = {
            "normalized_state": normalized,
            "raw_state": raw_state,
            "source": "squeue",
        }
        if normalized == "UNKNOWN":
            observation["error_code"] = "SCHEDULER_UNOBSERVABLE"
        return observation

    def _history_status(self, scheduler_id: str) -> dict[str, Any]:
        arguments = [
            self.profile.scheduler["history_program"],
            "-n",
            "-X",
            "-j",
            scheduler_id,
            "--format=State",
            "--parsable2",
        ]
        if self.profile.transport == "ssh":
            assert self.profile.ssh is not None
            arguments = [self.profile.ssh["ssh_program"], self.profile.ssh["host"], *arguments]
        try:
            result = self._run(arguments)
        except OMLError:
            return {
                "normalized_state": "UNKNOWN",
                "raw_state": "",
                "source": "sacct",
                "error_code": "SCHEDULER_UNOBSERVABLE",
            }
        raw = result.stdout.strip().splitlines() if result.returncode == 0 else []
        raw_state = raw[0].strip().upper().split("|", 1)[0].split()[0] if raw else ""
        normalized = NORMALIZED_STATES.get(raw_state, "UNKNOWN")
        observation = {
            "normalized_state": normalized,
            "raw_state": raw_state or result.stderr.strip(),
            "source": "sacct",
        }
        if normalized == "UNKNOWN":
            observation["error_code"] = "SCHEDULER_UNOBSERVABLE"
        return observation
