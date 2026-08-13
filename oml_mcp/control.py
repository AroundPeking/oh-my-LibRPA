from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
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
from .planner import PlanError, plan_case
from .provenance import digest_json, sha256_file
from .scientific_bands import (
    ScientificBandError,
    characterize_window_sampling,
    inspect_qpe_diagnostics,
    inspect_window_diagnostics,
    load_band_bundle,
    select_insulating_window,
)
from .scientific_definition import ScientificDefinitionError, build_definition_signature
from .scientific_evaluation import (
    ScientificEvaluationError,
    aggregate_convergence,
    evaluate_convergence_axis,
    evaluate_regression,
)
from .scientific_registry import (
    ScientificRegistryError,
    load_benchmark,
    load_convergence_bundle,
)
from .state import StateStore
from .stage_inspection import inspect_stage_outputs
from .validators import validate_case
from .parsers import ParseError, parse_bz_sampling


RUNTIME_CODE_SUFFIXES = frozenset({".py", ".pyc", ".sh", ".slurm", ".so", ".dylib"})
SUBMISSION_ABSENCE_GRACE_SECONDS = 300


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ControlledExecutionService:
    def __init__(self, profile: ExecutionProfile, *, initialize_state: bool = True) -> None:
        self.profile = profile
        self.store = StateStore(profile.state_db, initialize=initialize_state)
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
        try:
            current = plan_case(
                plan["source_path"],
                task=options["task"],
                system_type=options["system_type"],
                use_symmetry=bool(options["use_symmetry"]),
                soc=bool(options["soc"]),
                headwing=bool(options["headwing"]),
            )
        except (PlanError, ValueError, OSError) as exc:
            raise OMLError(
                "STALE_PLAN",
                f"approved source can no longer reproduce its plan: {exc}",
                evidence=(str(plan["source_path"]),),
                recovery="review the changed source and prepare a fresh immutable plan",
            ) from exc
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
        approved = {str(item["path"]) for item in manifest.get("files", [])}
        unregistered_code = []
        for path in run_dir.rglob("*"):
            relative = path.relative_to(run_dir)
            if relative.parts[:2] == (".oml", "snapshots"):
                continue
            if (
                relative.as_posix() not in approved
                and path.suffix.lower() in RUNTIME_CODE_SUFFIXES
                and (path.is_file() or path.is_symlink())
            ):
                unregistered_code.append(relative.as_posix())
        if unregistered_code:
            raise OMLError(
                "MANIFEST_MISMATCH",
                "run contains executable code that is not registered in the immutable manifest",
                evidence=tuple(sorted(unregistered_code)),
                recovery="preserve this run for diagnosis and prepare a fresh run from reviewed inputs",
            )

    def submit_stage(self, run_id: str, stage: str, plan_digest: str) -> dict[str, Any]:
        with self.store.submission_lock(run_id, stage):
            return self._submit_stage_locked(run_id, stage, plan_digest)

    def _submit_stage_locked(
        self, run_id: str, stage: str, plan_digest: str
    ) -> dict[str, Any]:
        run, plan, run_dir = self._load_receipts(run_id, plan_digest)
        active = self.store.active_attempt(run_id, stage)
        if active is not None and not active["scheduler_id"]:
            previous = self.store.latest_observation(active["attempt_id"])
            reconciliation = self.executor.reconcile_submission(run_id, stage)
            current = self.store.record_observation(
                active["attempt_id"],
                normalized_state=reconciliation["normalized_state"],
                raw_state=reconciliation["raw_state"],
                source=reconciliation["source"],
            )
            if reconciliation["verdict"] == "found":
                reconciled = self.store.reconcile_submission(
                    active["attempt_id"],
                    scheduler_id=reconciliation["scheduler_id"],
                    normalized_state=reconciliation["normalized_state"],
                )
                raise OMLError(
                    "DUPLICATE_JOB",
                    "the previously ambiguous submission exists in the scheduler",
                    evidence=(
                        reconciled["attempt_id"],
                        str(reconciled["scheduler_id"]),
                        reconciled["status"],
                    ),
                    recovery="observe and inspect the reconciled attempt; do not submit it again",
                )
            if active["status"] == "SUBMITTING":
                self.store.record_attempt_status(active["attempt_id"], "UNKNOWN")
            absence_confirmed = (
                previous is not None
                and previous["normalized_state"] == "UNKNOWN"
                and previous["raw_state"] == "NOT_FOUND"
                and (
                    _parse_utc(current["observed_at"])
                    - _parse_utc(previous["observed_at"])
                ).total_seconds()
                >= SUBMISSION_ABSENCE_GRACE_SECONDS
            )
            if absence_confirmed:
                self.store.record_attempt_status(active["attempt_id"], "FAILED")
                raise OMLError(
                    "RETRY_REQUIRES_FRESH_RUN",
                    "two separated scheduler queries found no matching submission; this run remains an immutable failed attempt",
                    evidence=(
                        active["attempt_id"],
                        previous["observed_at"],
                        current["observed_at"],
                        run_id,
                        stage,
                    ),
                    recovery="preserve this run and call prepare_run to create a fresh run before retrying",
                )
            raise OMLError(
                "SUBMISSION_UNRESOLVED",
                "no matching scheduler job is visible yet, so another submission remains blocked",
                evidence=(
                    active["attempt_id"],
                    current["observed_at"],
                    f"minimum_grace_seconds={SUBMISSION_ABSENCE_GRACE_SECONDS}",
                ),
                recovery="wait at least five minutes, then call submit_stage again to collect a second squeue+sacct absence observation",
            )
        if active is not None:
            raise OMLError(
                "DUPLICATE_JOB",
                "an equivalent stage attempt is still active or unobservable",
                evidence=(
                    active["attempt_id"],
                    str(active["scheduler_id"] or ""),
                    active["status"],
                ),
                recovery=(
                    "manually reconcile the interrupted submission before changing state"
                    if active["status"] == "SUBMITTING"
                    else "observe and inspect the existing attempt; do not prepare or submit a duplicate"
                ),
            )
        prior_attempts = tuple(
            attempt
            for attempt in self.store.list_attempts(run_id)
            if attempt["stage"] == stage
        )
        if prior_attempts:
            latest = max(prior_attempts, key=lambda item: item["attempt_number"])
            raise OMLError(
                "RETRY_REQUIRES_FRESH_RUN",
                "controlled execution does not reuse a run directory after a terminal stage attempt",
                evidence=(latest["attempt_id"], latest["status"], run_id, stage),
                recovery="preserve this run and call prepare_run to create a fresh run before retrying",
            )
        self._verify_source(plan)
        self._verify_manifest(run, run_dir)
        version_evidence = self.executor.verify_versions()
        prepared_execution = json.loads(
            (run_dir / ".oml" / "execution.json").read_text(encoding="utf-8")
        )
        prepared_executables = prepared_execution.get("version_evidence", {}).get(
            "executables"
        )
        current_executables = version_evidence.get("executables")
        if prepared_executables != current_executables:
            raise OMLError(
                "BINARY_MISMATCH",
                "configured ABACUS or LibRPA executable changed after run preparation",
                evidence=(
                    json.dumps(prepared_executables, sort_keys=True),
                    json.dumps(current_executables, sort_keys=True),
                ),
                recovery="prepare a fresh run after reviewing the new executable fingerprint",
            )
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
                headwing=bool(plan["options"]["headwing"]),
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
                attempt_id=attempt["attempt_id"],
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
        if run["execution_profile_id"] != self.profile.profile_id:
            raise OMLError(
                "PROFILE_MISMATCH",
                "run belongs to a different execution profile",
                evidence=(run["execution_profile_id"], self.profile.profile_id),
                recovery="use the profile that prepared this run",
            )
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
            if (
                existing["accepted"]
                and self.profile.transport == "local"
                and attempt["stage"] == plan["stages"][-1]
            ):
                self._snapshot_local_run(run_dir, attempt_id)
            return {"ok": True, **existing, **existing["report"]}
        if not attempt["scheduler_id"]:
            raise OMLError(
                "STATE_TRANSITION_DENIED",
                "stage outputs cannot be inspected before a scheduler ID is recorded",
                evidence=(attempt_id,),
                recovery="reconcile the submission before inspecting stage artifacts",
            )
        observation = self.executor.status(attempt["scheduler_id"])
        self.store.record_observation(
            attempt_id,
            normalized_state=observation["normalized_state"],
            raw_state=observation["raw_state"],
            source=observation["source"],
        )
        normalized = observation["normalized_state"]
        terminal_failure = normalized in {"FAILED", "CANCELLED"}
        if normalized != "COMPLETED" and not terminal_failure:
            if attempt["status"] not in {"PASSED", "FAILED", "CANCELLED"}:
                if normalized in {"PENDING", "RUNNING", "UNKNOWN"}:
                    self.store.record_attempt_status(attempt_id, normalized)
            raise OMLError(
                "STATE_TRANSITION_DENIED",
                "stage outputs cannot be inspected before a terminal scheduler state is observed",
                evidence=(attempt_id, normalized, observation["raw_state"]),
                recovery="call get_status until the scheduler reaches COMPLETED, FAILED, or CANCELLED",
            )
        self.executor.verify_remote_bundle(run_dir, run["remote_run_dir"])
        inspection_root = run_dir
        if self.profile.transport == "ssh":
            inspection_root = run_dir / ".oml" / "snapshots" / attempt_id
            link_dest = None
            stage_index = list(plan["stages"]).index(attempt["stage"])
            for prior_stage in reversed(list(plan["stages"])[:stage_index]):
                prior_attempt = self.store.passed_attempt(run_id, prior_stage)
                if prior_attempt is None:
                    continue
                candidate = inspection_root.parent / prior_attempt["attempt_id"]
                if candidate.is_dir():
                    link_dest = candidate
                    break
            self.executor.snapshot_run(
                run["remote_run_dir"], inspection_root, link_dest=link_dest
            )
        report = inspect_stage_outputs(
            inspection_root,
            attempt["stage"],
            expected_attempt_id=attempt_id,
        )
        if terminal_failure:
            scheduler_gate = {
                "gate_id": f"stage.{attempt['stage']}.scheduler",
                "status": "FAIL",
                "message": "scheduler terminated the stage before successful completion",
                "evidence": [
                    str(observation["raw_state"]),
                    str(attempt["scheduler_id"]),
                    str(inspection_root),
                ],
                "repair": "inspect the immutable scheduler and workload logs before preparing a fresh run",
                "measurements": None,
            }
            gates = [scheduler_gate, *report["gates"]]
            report = {
                **report,
                "accepted": False,
                "counts": {
                    status: sum(gate["status"] == status for gate in gates)
                    for status in ("PASS", "WARN", "FAIL", "SKIP")
                },
                "gates": gates,
            }
        if attempt["stage"] == "pyatb":
            cross_report = validate_case(
                inspection_root,
                task="gw",
                system_type=str(plan["options"]["system_type"]),
                use_symmetry=bool(plan["options"]["use_symmetry"]),
                soc=False,
                headwing=bool(plan["options"]["headwing"]),
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
        if (
            receipt["accepted"]
            and self.profile.transport == "local"
            and attempt["stage"] == plan["stages"][-1]
        ):
            self._snapshot_local_run(run_dir, attempt_id)
        return {"ok": True, **receipt, **report}

    @staticmethod
    def _snapshot_local_run(run_dir: Path, attempt_id: str) -> Path:
        snapshots = run_dir / ".oml" / "snapshots"
        target = snapshots / attempt_id
        if target.is_dir():
            return target
        temporary = snapshots / f".{attempt_id}.copying"
        if temporary.exists():
            raise OMLError(
                "SNAPSHOT_CONFLICT",
                "an incomplete local inspection snapshot already exists",
                evidence=(str(temporary),),
                recovery="reconcile the interrupted snapshot before finalizing scientific evidence",
            )

        def ignore(directory: str, names: list[str]) -> set[str]:
            path = Path(directory)
            if path == run_dir / ".oml":
                return {"snapshots"} & set(names)
            return set()

        snapshots.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copytree(run_dir, temporary, ignore=ignore, symlinks=True)
            temporary.rename(target)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return target

    def _accepted_final_snapshot(
        self, run_id: str, plan_digest: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
        run, plan, run_dir = self._load_receipts(run_id, plan_digest)
        self._verify_source(plan)
        self._verify_manifest(run, run_dir)
        attempts = self.store.list_attempts(run_id)
        latest_by_stage = {
            stage: max(
                (item for item in attempts if item["stage"] == stage),
                key=lambda item: item["attempt_number"],
                default=None,
            )
            for stage in plan["stages"]
        }
        incomplete = [
            stage
            for stage, attempt in latest_by_stage.items()
            if attempt is None or attempt["status"] != "PASSED"
        ]
        if incomplete:
            raise OMLError(
                "SCIENTIFIC_LINEAGE_INCOMPLETE",
                "every planned stage must have a passed final attempt before scientific finalization",
                evidence=tuple(incomplete),
                recovery="finish and inspect each planned stage before calling finalize_case",
            )
        final_attempt = latest_by_stage[plan["stages"][-1]]
        assert final_attempt is not None
        inspection = self.store.get_inspection(final_attempt["attempt_id"])
        if inspection is None or not inspection["accepted"]:
            raise OMLError(
                "SCIENTIFIC_LINEAGE_INCOMPLETE",
                "the final LibRPA attempt lacks an accepted immutable inspection",
                evidence=(final_attempt["attempt_id"],),
                recovery="inspect the completed LibRPA stage before scientific finalization",
            )
        snapshot = run_dir / ".oml" / "snapshots" / final_attempt["attempt_id"]
        if not snapshot.is_dir():
            raise OMLError(
                "SCIENTIFIC_SNAPSHOT_MISSING",
                "the accepted final attempt has no immutable output snapshot",
                evidence=(str(snapshot),),
                recovery="restore the accepted snapshot; do not evaluate the mutable run directory",
            )
        return run, plan, final_attempt, snapshot

    def _load_scientific_result(
        self, snapshot: Path, policy: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            below = int(policy["state_window"]["below_vbm"])
            above = int(policy["state_window"]["above_cbm"])
            if below != above:
                raise ScientificBandError(
                    "WINDOW_INVALID",
                    "the current evaluator requires equal VBM and CBM padding",
                )
            window = select_insulating_window(load_band_bundle(snapshot), padding=below)
            definition = build_definition_signature(snapshot)
            bz_sampling = parse_bz_sampling(snapshot / "bz_sampling_out")
            screening = definition["kpoints"]["scf"]
            window["sampling"] = characterize_window_sampling(
                window,
                screening_kpoints=tuple(bz_sampling["fractional_kpoints"]),
                screening_grid=tuple(screening["grid"]),
                screening_offset=tuple(screening["offset"]),
            )
            return {
                "definition": definition,
                "window": window,
                "diagnostics": inspect_window_diagnostics(
                    window,
                    inspect_qpe_diagnostics(snapshot),
                    require_positive_gw_gap=bool(policy["require_positive_gw_gap"]),
                ),
            }
        except (ParseError, ScientificBandError, ScientificDefinitionError) as exc:
            raise OMLError(
                "SCIENTIFIC_EVIDENCE_INVALID",
                str(exc),
                evidence=(str(snapshot),),
                recovery="inspect the accepted LibRPA outputs and physical-definition receipts",
            ) from exc

    @staticmethod
    def _scientific_status(
        regression: dict[str, Any], convergence: dict[str, Any]
    ) -> str:
        if regression["status"] == "FAIL" or convergence["status"] == "FAIL":
            return "FAIL"
        if regression["status"] == "PASS" and convergence["status"] == "PASS":
            return "PASS"
        return "NOT_EVALUATED"

    def finalize_case(
        self,
        run_id: str,
        plan_digest: str,
        benchmark_id: str,
        convergence_bundle_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            policy = load_benchmark(benchmark_id)
            run, plan, final_attempt, snapshot = self._accepted_final_snapshot(
                run_id, plan_digest
            )
            request = {
                "schema_version": 1,
                "evaluator_version": 4,
                "run_id": run_id,
                "plan_digest": plan_digest,
                "benchmark_id": benchmark_id,
                "convergence_bundle_id": convergence_bundle_id,
            }
            request_digest = digest_json(request)
            report_id = f"science-{request_digest[:20]}"
            existing = self.store.get_scientific_report(report_id)
            if existing is not None:
                if (
                    existing["run_id"] != run_id
                    or existing["final_attempt_id"] != final_attempt["attempt_id"]
                    or existing["manifest_digest"] != run["manifest_digest"]
                ):
                    raise OMLError(
                        "SCIENTIFIC_REPORT_CONFLICT",
                        "stored scientific report no longer matches the accepted final lineage",
                        evidence=(report_id, final_attempt["attempt_id"]),
                        recovery="preserve the existing evidence and prepare a fresh immutable run",
                    )
                self._write_scientific_report_file(run, existing["report"])
                return existing["report"]
            candidate = self._load_scientific_result(snapshot, policy)
            regression = evaluate_regression(
                candidate,
                policy["reference"],
                tolerance_ev=float(policy["regression_tolerance_ev"]),
            )
            axis_reports: dict[str, dict[str, Any]] = {}
            for previous in self.store.list_scientific_reports(run_id):
                if (
                    previous["benchmark_id"] == benchmark_id
                    and previous["final_attempt_id"] == final_attempt["attempt_id"]
                ):
                    previous_axes = previous["report"].get("convergence", {}).get("axes", {})
                    if isinstance(previous_axes, dict):
                        axis_reports.update(previous_axes)
            if convergence_bundle_id is not None:
                bundle = load_convergence_bundle(convergence_bundle_id)
                if bundle["benchmark_id"] != benchmark_id or bundle["run_ids"][-1] != run_id:
                    raise OMLError(
                        "CONVERGENCE_BUNDLE_INVALID",
                        "convergence bundle must target this benchmark and final candidate run",
                        evidence=(convergence_bundle_id, run_id, benchmark_id),
                        recovery="use a registered bundle whose final run is the case being finalized",
                    )
                pair = []
                for comparison_run_id in bundle["run_ids"]:
                    comparison_run = self.store.get_run(comparison_run_id)
                    _, _, _, comparison_snapshot = self._accepted_final_snapshot(
                        comparison_run_id, comparison_run["plan_digest"]
                    )
                    pair.append(self._load_scientific_result(comparison_snapshot, policy))
                axis_reports[bundle["axis"]] = evaluate_convergence_axis(
                    pair[0],
                    pair[1],
                    axis=bundle["axis"],
                    tolerance_ev=float(policy["convergence_tolerance_ev"]),
                )
            convergence = aggregate_convergence(
                axis_reports,
                required_axes=tuple(policy["required_axes"]),
            )
        except (ScientificRegistryError, ScientificEvaluationError) as exc:
            raise OMLError(
                getattr(exc, "code", "SCIENTIFIC_EVIDENCE_INVALID"),
                str(exc),
                evidence=(run_id, benchmark_id),
                recovery="repair the registered benchmark evidence before finalizing again",
            ) from exc

        report = {
            "schema_version": 1,
            "evaluator_version": 4,
            "report_id": report_id,
            **request,
            "request_digest": request_digest,
            "final_attempt_id": final_attempt["attempt_id"],
            "manifest_digest": run["manifest_digest"],
            "profile_id": run["execution_profile_id"],
            "scientific_status": self._scientific_status(regression, convergence),
            "definition": candidate["definition"],
            "window": candidate["window"],
            "diagnostics": candidate["diagnostics"],
            "regression": regression,
            "convergence": convergence,
        }
        self._write_scientific_report_file(run, report)
        receipt = self.store.record_scientific_report(report)
        return receipt["report"]

    @staticmethod
    def _write_scientific_report_file(
        run: dict[str, Any], report: dict[str, Any]
    ) -> None:
        science_root = Path(run["local_run_dir"]) / ".oml" / "science"
        science_root.mkdir(parents=True, exist_ok=True)
        report_path = science_root / f"{report['report_id']}.json"
        serialized = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
        if report_path.exists():
            if report_path.read_text(encoding="utf-8") != serialized:
                raise OMLError(
                    "SCIENTIFIC_REPORT_CONFLICT",
                    "scientific report file already exists with different evidence",
                    evidence=(str(report_path),),
                    recovery="preserve both run outputs and investigate the conflicting finalization",
                )
        else:
            temporary = report_path.with_name(f".{report_path.name}.writing")
            temporary.write_text(serialized, encoding="utf-8")
            os.replace(temporary, report_path)

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
