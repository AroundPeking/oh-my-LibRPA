from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import OMLError
from .evals import score_run
from .execution_profiles import (
    ExecutionProfile,
    execution_profile_payload,
    execution_profile_receipt,
)
from .executor import SlurmExecutor
from .materializer import prepare_run as materialize_run
from .planner import plan_case
from .provenance import digest_json, sha256_file
from .state import StateStore
from .stage_inspection import inspect_stage_outputs
from .validators import validate_case


class ControlledExecutionService:
    def __init__(self, profile: ExecutionProfile) -> None:
        self.profile = profile
        self.store = StateStore(profile.state_db)
        self.executor = SlurmExecutor(profile)

    def prepare_run(self, source_path: str | Path, plan_digest: str) -> dict[str, Any]:
        version_evidence = self.executor.verify_versions()
        execution_receipt = execution_profile_receipt(self.profile, version_evidence)
        receipt = materialize_run(
            source_path,
            plan_digest,
            self.profile,
            execution_receipt=execution_receipt,
        )
        self.executor.sync_run(
            Path(receipt["local_run_dir"]),
            receipt["remote_run_dir"],
        )
        return {**receipt, "version_evidence": version_evidence}

    def _load_receipts(self, run_id: str, plan_digest: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
        run = self.store.get_run(run_id)
        if run["execution_profile_id"] != self.profile.profile_id:
            raise OMLError(
                "PROFILE_MISMATCH",
                "run belongs to a different execution profile",
                evidence=(run["execution_profile_id"], self.profile.profile_id),
                recovery="use the profile that prepared this run",
            )
        if run["plan_digest"] != plan_digest:
            raise OMLError(
                "STALE_PLAN",
                "supplied plan digest does not match the prepared run",
                evidence=(plan_digest, run["plan_digest"]),
                recovery="use the immutable digest returned by prepare_run",
            )
        run_dir = Path(run["local_run_dir"]).resolve()
        if not any(run_dir.is_relative_to(root) for root in self.profile.allowed_run_roots):
            raise OMLError(
                "RUN_NOT_ALLOWED",
                "registered run directory is outside the current allowed roots",
                evidence=(str(run_dir),),
                recovery="repair the execution profile before taking further action",
            )
        plan = self.store.get_plan(run["plan_id"])
        execution_path = run_dir / ".oml" / "execution.json"
        try:
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OMLError(
                "PROFILE_MISMATCH",
                f"cannot read prepared execution profile receipt: {exc}",
                evidence=(str(execution_path),),
                recovery="prepare a fresh run with the current execution profile",
            ) from exc
        current_profile = execution_profile_payload(self.profile)
        if execution.get("execution_profile_digest") != digest_json(current_profile):
            raise OMLError(
                "PROFILE_MISMATCH",
                "current execution profile differs from the prepared run receipt",
                evidence=(
                    str(execution.get("execution_profile_digest")),
                    digest_json(current_profile),
                ),
                recovery="use the original profile or prepare a fresh run after reviewing changes",
            )
        return run, plan, run_dir

    def _verify_source(self, plan: dict[str, Any]) -> None:
        options = plan["options"]
        current = plan_case(
            plan["source_path"],
            task=options["task"],
            system_type=options["system_type"],
            use_symmetry=bool(options["use_symmetry"]),
            soc=bool(options["soc"]),
            headwing=bool(options["headwing"]),
        )
        if current.digest != plan["digest"] or current.source_digest != plan["source_digest"]:
            raise OMLError(
                "STALE_PLAN",
                "approved source inputs changed after run preparation",
                evidence=(plan["digest"], current.digest),
                recovery="do not reuse this run; review a new plan and prepare a fresh directory",
            )

    def _verify_manifest(self, run: dict[str, Any], run_dir: Path) -> None:
        manifest_path = run_dir / ".oml" / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OMLError(
                "MANIFEST_MISMATCH",
                f"cannot read the immutable run manifest: {exc}",
                evidence=(str(manifest_path),),
                recovery="prepare a fresh run; do not reconstruct receipts manually",
            ) from exc
        claimed = manifest.pop("manifest_digest", None)
        actual_receipt_digest = digest_json(manifest)
        if claimed != actual_receipt_digest or claimed != run["manifest_digest"]:
            raise OMLError(
                "MANIFEST_MISMATCH",
                "run manifest receipt digest is inconsistent",
                evidence=(str(claimed), actual_receipt_digest, run["manifest_digest"]),
                recovery="prepare a fresh run from the reviewed plan",
            )
        failures = []
        for item in manifest.get("files", []):
            relative = Path(str(item["path"]))
            path = run_dir / relative
            resolved = path.resolve()
            if path.is_symlink() or not resolved.is_relative_to(run_dir) or not resolved.is_file():
                failures.append(f"{relative.as_posix()}: missing, linked, or escaped")
                continue
            stat = resolved.stat()
            if stat.st_size != int(item["size"]) or sha256_file(resolved) != item["sha256"]:
                failures.append(f"{relative.as_posix()}: size or hash changed")
        if failures:
            raise OMLError(
                "MANIFEST_MISMATCH",
                "one or more controlled run files changed after preparation",
                evidence=tuple(failures),
                recovery="do not submit the modified run; prepare a fresh immutable run",
            )

    def submit_stage(self, run_id: str, stage: str, plan_digest: str) -> dict[str, Any]:
        run, plan, run_dir = self._load_receipts(run_id, plan_digest)
        self._verify_source(plan)
        self._verify_manifest(run, run_dir)
        version_evidence = self.executor.verify_versions()
        remote_bundle = self.executor.verify_remote_bundle(run_dir, run["remote_run_dir"])
        if stage == "librpa":
            validation_root = run_dir
            if self.profile.transport == "ssh":
                preprocess_attempt = self.store.passed_attempt(run_id, "preprocess")
                if preprocess_attempt is None:
                    raise OMLError(
                        "STATE_TRANSITION_DENIED",
                        "remote LibRPA validation requires a passed preprocess snapshot",
                        evidence=(run_id,),
                        recovery="inspect and pass the remote preprocess stage before LibRPA submission",
                    )
                validation_root = (
                    run_dir / ".oml" / "snapshots" / preprocess_attempt["attempt_id"]
                )
            report = validate_case(
                validation_root,
                task="gw",
                system_type=str(plan["options"]["system_type"]),
                use_symmetry=bool(plan["options"]["use_symmetry"]),
                soc=False,
                stage="pre_librpa",
            )
            if not report.accepted:
                failed = tuple(gate.gate_id for gate in report.gates if gate.status == "FAIL")
                raise OMLError(
                    "GATE_FAILED",
                    "full pre-LibRPA consistency gates failed",
                    evidence=failed,
                    recovery="apply every failed gate repair before submitting LibRPA",
                    details={"validation": report.to_dict()},
                )
        attempt = self.store.authorize_submission(
            run_id,
            stage,
            plan_digest,
            preflight={
                "version_evidence": version_evidence,
                "remote_bundle": remote_bundle,
            },
        )
        try:
            scheduler_id = self.executor.submit(
                run_dir,
                stage,
                remote_run_dir=run["remote_run_dir"],
            )
        except OMLError as exc:
            status = "UNKNOWN" if exc.code in {"SUBMISSION_AMBIGUOUS", "SCHEDULER_UNOBSERVABLE"} else "FAILED"
            self.store.record_attempt_status(attempt["attempt_id"], status)
            raise
        submitted = self.store.mark_attempt_submitted(attempt["attempt_id"], scheduler_id)
        return {
            **submitted,
            "version_evidence": version_evidence,
            "remote_bundle": remote_bundle,
        }

    def get_status(self, run_id: str, attempt_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        attempt = self.store.get_attempt(attempt_id)
        if attempt["run_id"] != run_id:
            raise OMLError(
                "ATTEMPT_RUN_MISMATCH",
                "stage attempt does not belong to the requested run",
                evidence=(run_id, attempt_id),
                recovery="use the run ID stored in the attempt receipt",
            )
        if not attempt["scheduler_id"]:
            latest = self.store.latest_observation(attempt_id)
            return {"ok": True, "run": run, "attempt": attempt, "scheduler": latest}
        observation = self.executor.status(attempt["scheduler_id"])
        self.store.record_observation(
            attempt_id,
            normalized_state=observation["normalized_state"],
            raw_state=observation["raw_state"],
            source=observation["source"],
        )
        normalized = observation["normalized_state"]
        if attempt["status"] not in {"PASSED", "FAILED", "CANCELLED"}:
            if normalized in {"PENDING", "RUNNING", "UNKNOWN"}:
                self.store.record_attempt_status(attempt_id, normalized)
            elif normalized in {"FAILED", "CANCELLED"}:
                self.store.record_attempt_status(attempt_id, normalized)
        attempt = self.store.get_attempt(attempt_id)
        return {"ok": True, "run": run, "attempt": attempt, "scheduler": observation}

    def inspect_stage(self, run_id: str, attempt_id: str, plan_digest: str) -> dict[str, Any]:
        run, plan, run_dir = self._load_receipts(run_id, plan_digest)
        self._verify_source(plan)
        self._verify_manifest(run, run_dir)
        attempt = self.store.get_attempt(attempt_id)
        if attempt["run_id"] != run_id:
            raise OMLError(
                "ATTEMPT_RUN_MISMATCH",
                "stage attempt does not belong to the requested run",
                evidence=(run_id, attempt_id),
                recovery="use the run ID stored in the attempt receipt",
            )
        existing = self.store.get_inspection(attempt_id)
        if existing is not None:
            return {"ok": True, **existing, **existing["report"]}
        observation = self.store.latest_observation(attempt_id)
        if observation is None or observation["normalized_state"] != "COMPLETED":
            raise OMLError(
                "STATE_TRANSITION_DENIED",
                "stage outputs cannot be accepted before scheduler completion is observed",
                evidence=(attempt_id, str(observation or "no observation")),
                recovery="call get_status until the scheduler reports COMPLETED, then inspect artifacts",
            )
        inspection_root = run_dir
        if self.profile.transport == "ssh":
            inspection_root = run_dir / ".oml" / "snapshots" / attempt_id
            self.executor.snapshot_run(run["remote_run_dir"], inspection_root)
        report = inspect_stage_outputs(inspection_root, attempt["stage"])
        if attempt["stage"] == "pyatb":
            cross_report = validate_case(
                inspection_root,
                task="gw",
                system_type=str(plan["options"]["system_type"]),
                use_symmetry=bool(plan["options"]["use_symmetry"]),
                soc=False,
                stage="pre_librpa",
            ).to_dict()
            gates = [*report["gates"], *cross_report["gates"]]
            counts = {
                status: sum(gate["status"] == status for gate in gates)
                for status in ("PASS", "WARN", "FAIL", "SKIP")
            }
            report = {
                **report,
                "accepted": counts["FAIL"] == 0,
                "counts": counts,
                "gates": gates,
            }
        receipt = self.store.finalize_inspection(attempt_id, report)
        return {"ok": True, **receipt, **report}

    def score_case(self, run_id: str, plan_digest: str) -> dict[str, Any]:
        provenance_errors = []
        provenance_ok = True
        prepared_versions_match = None
        try:
            run, plan, run_dir = self._load_receipts(run_id, plan_digest)
            self._verify_source(plan)
            self._verify_manifest(run, run_dir)
            execution = json.loads(
                (run_dir / ".oml" / "execution.json").read_text(encoding="utf-8")
            )
            prepared_versions_match = (
                execution.get("version_evidence", {}).get("verdict") == "match"
            )
        except OMLError as exc:
            if exc.code in {
                "MANIFEST_MISMATCH",
                "PROFILE_MISMATCH",
                "STALE_PLAN",
                "RUN_NOT_ALLOWED",
            }:
                provenance_ok = False
                provenance_errors.append(
                    {
                        "code": exc.code,
                        "message": exc.message,
                        "evidence": list(exc.evidence),
                        "recovery": exc.recovery,
                    }
                )
            else:
                raise
        report = score_run(
            self.store,
            run_id,
            provenance_ok=provenance_ok,
            prepared_versions_match=prepared_versions_match,
        )
        report["provenance_errors"] = provenance_errors
        return report
