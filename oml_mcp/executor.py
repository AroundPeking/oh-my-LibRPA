from __future__ import annotations

import re
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import OMLError
from .execution_profiles import ExecutionProfile
from .profiles import load_profile
from .stage_templates import CONTROLLED_PERIODIC_STAGES, stage_job_name


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
FINGERPRINT_SCRIPT = """import hashlib
import json
import os
import sys

path = sys.argv[1]
digest = hashlib.sha256()
with open(path, "rb") as handle:
    while chunk := handle.read(1024 * 1024):
        digest.update(chunk)
print(json.dumps({"sha256": digest.hexdigest(), "size": os.path.getsize(path)}, sort_keys=True))
"""
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
ATTEMPT_ID_PATTERN = re.compile(r"^attempt-[0-9a-f]{20}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_scheduler_state(raw_state: str) -> str:
    token = raw_state.strip().upper().split()[0].rstrip("+") if raw_state.strip() else ""
    return NORMALIZED_STATES.get(token, "UNKNOWN")


class SlurmExecutor:
    def __init__(self, profile: ExecutionProfile, *, timeout_seconds: int = 20) -> None:
        self.profile = profile
        self.timeout_seconds = timeout_seconds

    def _run(
        self,
        arguments: list[str],
        *,
        cwd: Path | None = None,
        timeout_code: str = "SCHEDULER_UNOBSERVABLE",
    ) -> subprocess.CompletedProcess[str]:
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
                timeout_code,
                (
                    "submission command timed out before its result could be reconciled"
                    if timeout_code == "SUBMISSION_AMBIGUOUS"
                    else "configured external adapter timed out"
                ),
                evidence=tuple(str(item) for item in arguments[:2]),
                recovery=(
                    "query the scheduler for the recorded run and stage before retrying"
                    if timeout_code == "SUBMISSION_AMBIGUOUS"
                    else "restore reliable scheduler, SSH, or version observation before continuing"
                ),
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
            [ssh["ssh_program"], ssh["host"], "mkdir", "--", remote_run_dir]
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
            return
        temporary = snapshot_dir.with_name(f".{snapshot_dir.name}.fetching")
        if temporary.exists():
            raise OMLError(
                "SNAPSHOT_CONFLICT",
                "an incomplete inspection snapshot is already being fetched",
                evidence=(str(temporary),),
                recovery="reconcile the interrupted fetch before retrying inspection",
            )
        temporary.mkdir(parents=True, mode=0o700)
        result = self._run(
            [
                self.profile.ssh["rsync_program"],
                "-a",
                "--",
                f"{self.profile.ssh['host']}:{remote_run_dir}/",
                f"{temporary}/",
            ]
        )
        if result.returncode != 0:
            try:
                temporary.rmdir()
            except OSError:
                pass
            raise OMLError(
                "SNAPSHOT_FAILED",
                "failed to create a bounded remote output snapshot",
                evidence=(result.stderr.strip(), remote_run_dir, str(temporary)),
                recovery="repair SSH/rsync observation access before inspecting the stage",
            )
        temporary.rename(snapshot_dir)

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
        executables = {
            name: self._fingerprint_executable(str(self.profile.runtime[name]))
            for name in ("abacus", "librpa")
        }
        return {
            "verdict": "match",
            "components": components,
            "executables": executables,
        }

    def _fingerprint_executable(self, path: str) -> dict[str, str | int]:
        arguments = [str(self.profile.runtime["python"]), "-c", FINGERPRINT_SCRIPT, path]
        if self.profile.transport == "ssh":
            assert self.profile.ssh is not None
            remote_command = " ".join(shlex.quote(item) for item in arguments)
            arguments = [
                self.profile.ssh["ssh_program"],
                self.profile.ssh["host"],
                remote_command,
            ]
        result = self._run(arguments)
        try:
            payload = json.loads(result.stdout.strip()) if result.returncode == 0 else None
        except json.JSONDecodeError:
            payload = None
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("sha256"), str)
            or not SHA256_PATTERN.fullmatch(payload["sha256"])
            or not isinstance(payload.get("size"), int)
            or isinstance(payload.get("size"), bool)
            or payload["size"] <= 0
        ):
            raise OMLError(
                "BINARY_UNVERIFIABLE",
                "configured executable fingerprint could not be verified",
                evidence=(path, result.stdout.strip(), result.stderr.strip()),
                recovery="repair the executable path and runtime Python in the execution profile",
            )
        return {"path": path, "sha256": payload["sha256"], "size": payload["size"]}

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
        runtime_surface = self._run(
            [
                self.profile.ssh["rsync_program"],
                "-r",
                "--dry-run",
                "--checksum",
                "--itemize-changes",
                "--delete",
                "--exclude=.oml/snapshots/",
                "--include=*/",
                "--include=*.py",
                "--include=*.pyc",
                "--include=*.sh",
                "--include=*.slurm",
                "--include=*.so",
                "--include=*.dylib",
                "--exclude=*",
                "--",
                f"{local_run_dir}/",
                f"{self.profile.ssh['host']}:{remote_run_dir}/",
            ]
        )
        runtime_changes = "\n".join(
            line
            for line in runtime_surface.stdout.splitlines()
            if not line.startswith("cannot delete non-empty directory: ")
        ).strip()
        if runtime_surface.returncode != 0 or runtime_changes:
            raise OMLError(
                "REMOTE_MANIFEST_MISMATCH",
                "remote run contains changed or unregistered executable code",
                evidence=(
                    runtime_changes or runtime_surface.stderr.strip(),
                    str(local_run_dir),
                    remote_run_dir,
                ),
                recovery="do not submit; prepare a fresh remote run directory from the immutable bundle",
            )
        return {"verdict": "match", "remote_run_dir": remote_run_dir}

    def _scheduler_command(self, arguments: list[str]) -> list[str]:
        if self.profile.transport == "local":
            return arguments
        if self.profile.ssh is None:
            raise OMLError(
                "PROFILE_INVALID",
                "SSH execution profile is incomplete",
                evidence=(self.profile.profile_id,),
                recovery="repair the execution profile",
            )
        remote_command = " ".join(shlex.quote(item) for item in arguments)
        return [self.profile.ssh["ssh_program"], self.profile.ssh["host"], remote_command]

    def reconcile_submission(self, run_id: str, stage: str) -> dict[str, Any]:
        job_name = stage_job_name(run_id, stage)
        queries = (
            (
                "squeue",
                [
                    self.profile.scheduler["status_program"],
                    "-h",
                    "--name",
                    job_name,
                    "-o",
                    "%i|%T|%j",
                ],
            ),
            (
                "sacct",
                [
                    self.profile.scheduler["history_program"],
                    "-n",
                    "-X",
                    "--name",
                    job_name,
                    "--format=JobIDRaw,State,JobName",
                    "--parsable2",
                ],
            ),
        )
        for source, query in queries:
            try:
                result = self._run(self._scheduler_command(query))
            except OMLError as exc:
                raise OMLError(
                    "SCHEDULER_UNOBSERVABLE",
                    "cannot reconcile the ambiguous submission reliably",
                    evidence=(run_id, stage, source, exc.code),
                    recovery="restore scheduler observation before considering another submission",
                ) from exc
            if result.returncode != 0:
                raise OMLError(
                    "SCHEDULER_UNOBSERVABLE",
                    "scheduler rejected the submission-reconciliation query",
                    evidence=(run_id, stage, source, result.stderr.strip()),
                    recovery="restore scheduler observation before considering another submission",
                )
            matches: dict[str, str] = {}
            for line in result.stdout.splitlines():
                parts = [part.strip() for part in line.split("|")]
                if len(parts) < 3 or parts[2] != job_name or not parts[0].isdigit():
                    continue
                matches[parts[0]] = parts[1]
            if len(matches) > 1:
                raise OMLError(
                    "SUBMISSION_AMBIGUOUS",
                    "multiple scheduler jobs match one immutable run stage",
                    evidence=tuple(f"{job_id}:{state}" for job_id, state in matches.items()),
                    recovery="do not submit again; inspect and resolve every matching job",
                )
            if matches:
                scheduler_id, raw_state = next(iter(matches.items()))
                return {
                    "verdict": "found",
                    "scheduler_id": scheduler_id,
                    "normalized_state": _normalize_scheduler_state(raw_state),
                    "raw_state": raw_state,
                    "source": source,
                    "observed_at": _utc_now(),
                }
        return {
            "verdict": "absent",
            "normalized_state": "UNKNOWN",
            "raw_state": "NOT_FOUND",
            "source": "squeue+sacct",
            "observed_at": _utc_now(),
        }

    def submit(
        self,
        local_run_dir: Path,
        stage: str,
        *,
        attempt_id: str,
        remote_run_dir: str | None,
    ) -> str:
        if stage not in CONTROLLED_PERIODIC_STAGES:
            raise OMLError(
                "STATE_TRANSITION_DENIED",
                f"unsupported controlled stage: {stage}",
                evidence=(stage,),
                recovery="submit only a stage listed in the immutable periodic GW plan",
            )
        if not ATTEMPT_ID_PATTERN.fullmatch(attempt_id):
            raise OMLError(
                "STATE_INVALID",
                "attempt ID is not a generated OML submission identity",
                evidence=(attempt_id,),
                recovery="submit only the attempt returned by OML state authorization",
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
                [
                    submit_program,
                    "--parsable",
                    f"--export=ALL,OML_ATTEMPT_ID={attempt_id}",
                    relative_script.as_posix(),
                ],
                cwd=local_run_dir,
                timeout_code="SUBMISSION_AMBIGUOUS",
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
                    f"--export=ALL,OML_ATTEMPT_ID={attempt_id}",
                    f"--chdir={remote_run_dir}",
                    remote_script,
                ],
                timeout_code="SUBMISSION_AMBIGUOUS",
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
                "observed_at": _utc_now(),
            }
        if result.returncode != 0:
            return {
                "normalized_state": "UNKNOWN",
                "raw_state": result.stderr.strip(),
                "source": "squeue",
                "error_code": "SCHEDULER_UNOBSERVABLE",
                "observed_at": _utc_now(),
            }
        raw = result.stdout.strip().splitlines()
        if not raw:
            return self._history_status(scheduler_id)
        raw_state = raw[0].strip().upper().split()[0]
        normalized = _normalize_scheduler_state(raw_state)
        observation = {
            "normalized_state": normalized,
            "raw_state": raw_state,
            "source": "squeue",
            "observed_at": _utc_now(),
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
                "observed_at": _utc_now(),
            }
        raw = result.stdout.strip().splitlines() if result.returncode == 0 else []
        raw_state = raw[0].strip().upper().split("|", 1)[0].split()[0] if raw else ""
        normalized = _normalize_scheduler_state(raw_state)
        observation = {
            "normalized_state": normalized,
            "raw_state": raw_state or result.stderr.strip(),
            "source": "sacct",
            "observed_at": _utc_now(),
        }
        if normalized == "UNKNOWN":
            observation["error_code"] = "SCHEDULER_UNOBSERVABLE"
        return observation
