from __future__ import annotations

import json
import fcntl
import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import OMLError


ACTIVE_ATTEMPT_STATUSES = frozenset({"SUBMITTING", "SUBMITTED", "PENDING", "RUNNING", "UNKNOWN"})
TERMINAL_ATTEMPT_STATUSES = frozenset({"PASSED", "FAILED", "CANCELLED"})
ALL_ATTEMPT_STATUSES = ACTIVE_ATTEMPT_STATUSES | TERMINAL_ATTEMPT_STATUSES
ALLOWED_STATUS_TRANSITIONS = {
    "SUBMITTING": frozenset(
        {"SUBMITTING", "SUBMITTED", "PENDING", "RUNNING", "UNKNOWN", "FAILED", "CANCELLED"}
    ),
    "SUBMITTED": frozenset(
        {"SUBMITTED", "PENDING", "RUNNING", "UNKNOWN", "PASSED", "FAILED", "CANCELLED"}
    ),
    "PENDING": frozenset({"PENDING", "RUNNING", "UNKNOWN", "PASSED", "FAILED", "CANCELLED"}),
    "RUNNING": frozenset({"RUNNING", "UNKNOWN", "PASSED", "FAILED", "CANCELLED"}),
    "UNKNOWN": frozenset({"UNKNOWN", "PENDING", "RUNNING", "PASSED", "FAILED", "CANCELLED"}),
    "PASSED": frozenset({"PASSED"}),
    "FAILED": frozenset({"FAILED"}),
    "CANCELLED": frozenset({"CANCELLED"}),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _loads(value: str) -> Any:
    return json.loads(value)


class StateStore:
    def __init__(self, path: str | Path, *, initialize: bool = True) -> None:
        self.path = Path(path).expanduser().resolve()
        if initialize:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        elif not self.path.is_file():
            raise OMLError(
                "STATE_NOT_FOUND",
                "controlled-execution state database does not exist",
                evidence=(str(self.path),),
                recovery="prepare a run with this execution profile before reading its status or score",
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    digest TEXT NOT NULL,
                    source_digest TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    route TEXT NOT NULL,
                    stages_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL REFERENCES plans(plan_id),
                    plan_digest TEXT NOT NULL,
                    execution_profile_id TEXT NOT NULL,
                    local_run_dir TEXT NOT NULL UNIQUE,
                    remote_run_dir TEXT,
                    manifest_digest TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stage_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    stage TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    scheduler_id TEXT,
                    preflight_json TEXT NOT NULL DEFAULT '{}',
                    submitted_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(run_id, stage, attempt_number)
                );
                CREATE TABLE IF NOT EXISTS observations (
                    observation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attempt_id TEXT NOT NULL REFERENCES stage_attempts(attempt_id),
                    normalized_state TEXT NOT NULL,
                    raw_state TEXT NOT NULL,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS stage_inspections (
                    attempt_id TEXT PRIMARY KEY REFERENCES stage_attempts(attempt_id),
                    accepted INTEGER NOT NULL,
                    report_json TEXT NOT NULL,
                    inspected_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scientific_reports (
                    report_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    plan_digest TEXT NOT NULL,
                    benchmark_id TEXT NOT NULL,
                    convergence_bundle_id TEXT,
                    request_digest TEXT NOT NULL,
                    final_attempt_id TEXT NOT NULL REFERENCES stage_attempts(attempt_id),
                    manifest_digest TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    scientific_status TEXT NOT NULL,
                    report_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(stage_attempts)")
            }
            if "preflight_json" not in columns:
                connection.execute(
                    "ALTER TABLE stage_attempts ADD COLUMN preflight_json TEXT NOT NULL DEFAULT '{}'"
                )
            connection.commit()

    @contextmanager
    def submission_lock(self, run_id: str, stage: str) -> Iterator[None]:
        identity = hashlib.sha256(f"{run_id}\0{stage}".encode("utf-8")).hexdigest()
        lock_root = self.path.parent / f".{self.path.name}.locks"
        lock_root.mkdir(mode=0o700, exist_ok=True)
        lock_path = lock_root / f"{identity}.lock"
        with lock_path.open("a", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise OMLError(
                    "DUPLICATE_JOB",
                    "another submit_stage call is already handling this run stage",
                    evidence=(run_id, stage),
                    recovery="wait for the active submission call to return before observing or retrying",
                ) from exc
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def register_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        required = {
            "plan_id",
            "digest",
            "source_digest",
            "source_path",
            "profile_id",
            "route",
            "stages",
        }
        missing = sorted(required - set(plan))
        if missing:
            raise OMLError(
                "PLAN_INVALID",
                f"plan is missing required fields: {missing}",
                evidence=tuple(missing),
                recovery="recreate the plan with the current OML planner",
            )
        payload = dict(plan)
        now = utc_now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT digest, payload_json FROM plans WHERE plan_id = ?",
                (plan["plan_id"],),
            ).fetchone()
            if existing is not None:
                if existing["digest"] != plan["digest"] or _loads(existing["payload_json"]) != payload:
                    connection.rollback()
                    raise OMLError(
                        "PLAN_CONFLICT",
                        "an immutable plan ID already exists with different content",
                        evidence=(str(plan["plan_id"]),),
                        recovery="generate a new plan from the changed input snapshot",
                    )
                connection.commit()
                return payload
            connection.execute(
                """
                INSERT INTO plans (
                    plan_id, digest, source_digest, source_path, profile_id, route,
                    stages_json, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan["plan_id"],
                    plan["digest"],
                    plan["source_digest"],
                    plan["source_path"],
                    plan["profile_id"],
                    plan["route"],
                    _json(plan["stages"]),
                    _json(payload),
                    now,
                ),
            )
            connection.commit()
        return payload

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM plans WHERE plan_id = ?", (plan_id,)
            ).fetchone()
        if row is None:
            raise OMLError(
                "PLAN_NOT_FOUND",
                f"plan not found: {plan_id}",
                evidence=(plan_id,),
                recovery="create and register a current plan before preparing a run",
            )
        return _loads(row["payload_json"])

    def create_run(
        self,
        *,
        run_id: str,
        plan_id: str,
        plan_digest: str,
        execution_profile_id: str,
        local_run_dir: str,
        remote_run_dir: str | None,
        manifest_digest: str,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO runs (
                        run_id, plan_id, plan_digest, execution_profile_id, local_run_dir,
                        remote_run_dir, manifest_digest, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'RUN_PREPARED', ?)
                    """,
                    (
                        run_id,
                        plan_id,
                        plan_digest,
                        execution_profile_id,
                        local_run_dir,
                        remote_run_dir,
                        manifest_digest,
                        now,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                raise OMLError(
                    "RUN_CONFLICT",
                    "run ID or run directory is already registered",
                    evidence=(run_id, local_run_dir),
                    recovery="use the existing run receipt or prepare a fresh run ID",
                ) from exc
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise OMLError(
                "RUN_NOT_FOUND",
                f"run not found: {run_id}",
                evidence=(run_id,),
                recovery="prepare the run before submitting or inspecting it",
            )
        return dict(row)

    def mark_run_prepare_failed(self, run_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise OMLError(
                    "RUN_NOT_FOUND",
                    f"run not found: {run_id}",
                    evidence=(run_id,),
                    recovery="preserve the preparation error and inspect the state database",
                )
            if row["status"] != "RUN_PREPARED":
                connection.rollback()
                raise OMLError(
                    "RUN_STATE_INVALID",
                    "only a newly prepared run can be marked as a preparation failure",
                    evidence=(run_id, str(row["status"])),
                    recovery="preserve the existing run state and inspect the original failure",
                )
            connection.execute(
                "UPDATE runs SET status = 'PREPARE_FAILED' WHERE run_id = ?",
                (run_id,),
            )
            connection.commit()
        return self.get_run(run_id)

    def authorize_submission(
        self,
        run_id: str,
        stage: str,
        plan_digest: str,
        *,
        preflight: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                connection.rollback()
                raise OMLError(
                    "RUN_NOT_FOUND",
                    f"run not found: {run_id}",
                    evidence=(run_id,),
                    recovery="prepare the run before submission",
                )
            if run["plan_digest"] != plan_digest:
                connection.rollback()
                raise OMLError(
                    "STALE_PLAN",
                    "submitted plan digest does not match the prepared run",
                    evidence=(plan_digest, run["plan_digest"]),
                    recovery="re-plan and prepare a fresh run from the current source inputs",
                )
            plan = connection.execute(
                "SELECT stages_json FROM plans WHERE plan_id = ?", (run["plan_id"],)
            ).fetchone()
            stages = _loads(plan["stages_json"])
            if stage not in stages:
                connection.rollback()
                raise OMLError(
                    "STATE_TRANSITION_DENIED",
                    f"stage {stage!r} is not part of this route",
                    evidence=(run_id, stage),
                    recovery="submit only a stage listed in the immutable plan",
                )
            active = connection.execute(
                """
                SELECT attempt_id, status, scheduler_id FROM stage_attempts
                WHERE run_id = ? AND stage = ? AND status IN ('SUBMITTING','SUBMITTED','PENDING','RUNNING','UNKNOWN')
                ORDER BY attempt_number DESC LIMIT 1
                """,
                (run_id, stage),
            ).fetchone()
            if active is not None:
                connection.rollback()
                raise OMLError(
                    "DUPLICATE_JOB",
                    "an equivalent stage attempt is still active or unobservable",
                    evidence=(active["attempt_id"], str(active["scheduler_id"] or ""), active["status"]),
                    recovery="reconcile the existing attempt before considering another submission",
                )
            equivalent = connection.execute(
                """
                SELECT a.attempt_id, a.status, a.scheduler_id, a.run_id
                FROM stage_attempts AS a
                JOIN runs AS other ON other.run_id = a.run_id
                WHERE other.plan_digest = ? AND a.run_id != ? AND a.stage = ?
                  AND a.status IN ('SUBMITTING','SUBMITTED','PENDING','RUNNING','UNKNOWN')
                ORDER BY a.updated_at DESC LIMIT 1
                """,
                (plan_digest, run_id, stage),
            ).fetchone()
            if equivalent is not None:
                connection.rollback()
                raise OMLError(
                    "DUPLICATE_JOB",
                    "an equivalent plan stage is active in another run",
                    evidence=(
                        equivalent["run_id"],
                        equivalent["attempt_id"],
                        str(equivalent["scheduler_id"] or ""),
                        equivalent["status"],
                    ),
                    recovery="observe and inspect the existing run instead of submitting a duplicate",
                )
            passed_same = connection.execute(
                "SELECT 1 FROM stage_attempts WHERE run_id = ? AND stage = ? AND status = 'PASSED'",
                (run_id, stage),
            ).fetchone()
            if passed_same is not None:
                connection.rollback()
                raise OMLError(
                    "STATE_TRANSITION_DENIED",
                    "the requested stage has already passed for this immutable run",
                    evidence=(run_id, stage),
                    recovery="submit the next planned stage or create a new run for changed inputs",
                )
            stage_index = stages.index(stage)
            missing = []
            for prerequisite in stages[:stage_index]:
                passed = connection.execute(
                    "SELECT 1 FROM stage_attempts WHERE run_id = ? AND stage = ? AND status = 'PASSED'",
                    (run_id, prerequisite),
                ).fetchone()
                if passed is None:
                    missing.append(prerequisite)
            if missing:
                connection.rollback()
                raise OMLError(
                    "STATE_TRANSITION_DENIED",
                    "one or more prerequisite stages have not passed",
                    evidence=tuple(missing),
                    recovery="inspect and pass every preceding stage before submission",
                )
            attempt_number = connection.execute(
                "SELECT COUNT(*) AS count FROM stage_attempts WHERE run_id = ? AND stage = ?",
                (run_id, stage),
            ).fetchone()["count"] + 1
            attempt_id = f"attempt-{uuid.uuid4().hex[:20]}"
            connection.execute(
                """
                INSERT INTO stage_attempts (
                    attempt_id, run_id, stage, attempt_number, status, preflight_json, updated_at
                ) VALUES (?, ?, ?, ?, 'SUBMITTING', ?, ?)
                """,
                (attempt_id, run_id, stage, attempt_number, _json(preflight or {}), now),
            )
            connection.commit()
        return self.get_attempt(attempt_id)

    def active_attempt(self, run_id: str, stage: str) -> dict[str, Any] | None:
        self.get_run(run_id)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM stage_attempts
                WHERE run_id = ? AND stage = ?
                  AND status IN ('SUBMITTING','SUBMITTED','PENDING','RUNNING','UNKNOWN')
                ORDER BY attempt_number DESC LIMIT 1
                """,
                (run_id, stage),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["preflight"] = _loads(data.pop("preflight_json"))
        return data

    def reconcile_submission(
        self,
        attempt_id: str,
        *,
        scheduler_id: str,
        normalized_state: str,
    ) -> dict[str, Any]:
        status = {
            "PENDING": "PENDING",
            "RUNNING": "RUNNING",
            "FAILED": "FAILED",
            "CANCELLED": "CANCELLED",
            "COMPLETED": "SUBMITTED",
            "UNKNOWN": "UNKNOWN",
        }.get(normalized_state)
        if status is None or not scheduler_id.isdigit():
            raise OMLError(
                "STATE_INVALID",
                "reconciled submission has an invalid scheduler identity or state",
                evidence=(attempt_id, scheduler_id, normalized_state),
                recovery="preserve the ambiguous attempt and repair scheduler observation",
            )
        now = utc_now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, scheduler_id FROM stage_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                connection.rollback()
                return self.get_attempt(attempt_id)
            if row["scheduler_id"] not in {None, scheduler_id}:
                connection.rollback()
                raise OMLError(
                    "SUBMISSION_AMBIGUOUS",
                    "attempt already has a different scheduler ID",
                    evidence=(attempt_id, row["scheduler_id"], scheduler_id),
                    recovery="do not retry; inspect both scheduler records",
                )
            if status not in ALLOWED_STATUS_TRANSITIONS[row["status"]]:
                connection.rollback()
                raise OMLError(
                    "STATE_TRANSITION_DENIED",
                    f"attempt status cannot move from {row['status']} to {status}",
                    evidence=(attempt_id,),
                    recovery="preserve the existing attempt receipt",
                )
            connection.execute(
                """
                UPDATE stage_attempts
                SET scheduler_id = ?, status = ?, submitted_at = COALESCE(submitted_at, ?), updated_at = ?
                WHERE attempt_id = ?
                """,
                (scheduler_id, status, now, now, attempt_id),
            )
            connection.commit()
        return self.get_attempt(attempt_id)

    def get_attempt(self, attempt_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM stage_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
        if row is None:
            raise OMLError(
                "ATTEMPT_NOT_FOUND",
                f"stage attempt not found: {attempt_id}",
                evidence=(attempt_id,),
                recovery="use an attempt ID returned by submit_stage or get_status",
            )
        data = dict(row)
        data["preflight"] = _loads(data.pop("preflight_json"))
        return data

    def passed_attempt(self, run_id: str, stage: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM stage_attempts
                WHERE run_id = ? AND stage = ? AND status = 'PASSED'
                ORDER BY attempt_number DESC LIMIT 1
                """,
                (run_id, stage),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["preflight"] = _loads(data.pop("preflight_json"))
        return data

    def list_attempts(self, run_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM stage_attempts
                WHERE run_id = ? ORDER BY stage, attempt_number
                """,
                (run_id,),
            ).fetchall()
        attempts = []
        for row in rows:
            data = dict(row)
            data["preflight"] = _loads(data.pop("preflight_json"))
            attempts.append(data)
        return attempts

    def mark_attempt_submitted(self, attempt_id: str, scheduler_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE stage_attempts
                SET status = 'SUBMITTED', scheduler_id = ?, submitted_at = ?, updated_at = ?
                WHERE attempt_id = ? AND status = 'SUBMITTING'
                """,
                (scheduler_id, now, now, attempt_id),
            )
            connection.commit()
        if cursor.rowcount != 1:
            raise OMLError(
                "STATE_TRANSITION_DENIED",
                "attempt is not awaiting a scheduler ID",
                evidence=(attempt_id,),
                recovery="inspect the existing attempt before changing its state",
            )
        return self.get_attempt(attempt_id)

    def record_attempt_status(self, attempt_id: str, status: str) -> dict[str, Any]:
        if status not in ALL_ATTEMPT_STATUSES:
            raise OMLError(
                "STATE_INVALID",
                f"invalid attempt status: {status}",
                evidence=(attempt_id, status),
                recovery="use a normalized OML attempt status",
            )
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM stage_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if row is None:
                connection.rollback()
                return self.get_attempt(attempt_id)
            current = row["status"]
            if status not in ALLOWED_STATUS_TRANSITIONS[current]:
                connection.rollback()
                raise OMLError(
                    "STATE_TRANSITION_DENIED",
                    f"attempt status cannot move from {current} to {status}",
                    evidence=(attempt_id, current, status),
                    recovery="preserve the terminal receipt and create a new attempt only when policy allows",
                )
            cursor = connection.execute(
                "UPDATE stage_attempts SET status = ?, updated_at = ? WHERE attempt_id = ?",
                (status, utc_now(), attempt_id),
            )
            connection.commit()
        if cursor.rowcount != 1:
            return self.get_attempt(attempt_id)
        return self.get_attempt(attempt_id)

    def record_observation(
        self,
        attempt_id: str,
        *,
        normalized_state: str,
        raw_state: str,
        source: str,
    ) -> dict[str, Any]:
        observed_at = utc_now()
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO observations (
                    attempt_id, normalized_state, raw_state, source, observed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (attempt_id, normalized_state, raw_state, source, observed_at),
            )
            connection.commit()
        return self.latest_observation(attempt_id)

    def latest_observation(self, attempt_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM observations WHERE attempt_id = ?
                ORDER BY observation_id DESC LIMIT 1
                """,
                (attempt_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_inspection(self, attempt_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM stage_inspections WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            attempt = connection.execute(
                "SELECT status FROM stage_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "attempt_id": attempt_id,
            "attempt_status": attempt["status"],
            "accepted": bool(row["accepted"]),
            "inspected_at": row["inspected_at"],
            "report": _loads(row["report_json"]),
        }

    def finalize_inspection(self, attempt_id: str, report: dict[str, Any]) -> dict[str, Any]:
        payload = _json(report)
        accepted = bool(report.get("accepted"))
        target_status = "PASSED" if accepted else "FAILED"
        inspected_at = utc_now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = connection.execute(
                "SELECT stage, status FROM stage_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if attempt is None:
                connection.rollback()
                self.get_attempt(attempt_id)
                raise AssertionError("unreachable")
            if report.get("stage") != attempt["stage"]:
                connection.rollback()
                raise OMLError(
                    "INSPECTION_CONFLICT",
                    "inspection stage does not match the attempt receipt",
                    evidence=(str(report.get("stage")), attempt["stage"]),
                    recovery="inspect the stage recorded by the immutable attempt",
                )
            existing = connection.execute(
                "SELECT report_json FROM stage_inspections WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            if existing is not None:
                connection.rollback()
                if existing["report_json"] != payload:
                    raise OMLError(
                        "INSPECTION_CONFLICT",
                        "an immutable inspection already exists with different evidence",
                        evidence=(attempt_id,),
                        recovery="preserve the existing receipt and create a reviewed retry only when allowed",
                    )
                receipt = self.get_inspection(attempt_id)
                assert receipt is not None
                return receipt
            if target_status not in ALLOWED_STATUS_TRANSITIONS[attempt["status"]]:
                connection.rollback()
                raise OMLError(
                    "STATE_TRANSITION_DENIED",
                    f"inspection cannot move attempt from {attempt['status']} to {target_status}",
                    evidence=(attempt_id,),
                    recovery="preserve the terminal attempt receipt",
                )
            connection.execute(
                "INSERT INTO stage_inspections (attempt_id, accepted, report_json, inspected_at) VALUES (?, ?, ?, ?)",
                (attempt_id, int(accepted), payload, inspected_at),
            )
            connection.execute(
                "UPDATE stage_attempts SET status = ?, updated_at = ? WHERE attempt_id = ?",
                (target_status, inspected_at, attempt_id),
            )
            connection.commit()
        receipt = self.get_inspection(attempt_id)
        assert receipt is not None
        return receipt

    def get_scientific_report(self, report_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM scientific_reports WHERE report_id = ?", (report_id,)
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["report"] = _loads(value.pop("report_json"))
        return value

    def latest_scientific_report(self, run_id: str) -> dict[str, Any] | None:
        self.get_run(run_id)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM scientific_reports
                WHERE run_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        value = dict(row)
        value["report"] = _loads(value.pop("report_json"))
        return value

    def list_scientific_reports(self, run_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scientific_reports
                WHERE run_id = ? ORDER BY created_at, rowid
                """,
                (run_id,),
            ).fetchall()
        reports = []
        for row in rows:
            value = dict(row)
            value["report"] = _loads(value.pop("report_json"))
            reports.append(value)
        return reports

    def record_scientific_report(self, report: dict[str, Any]) -> dict[str, Any]:
        required = {
            "report_id",
            "run_id",
            "plan_digest",
            "benchmark_id",
            "convergence_bundle_id",
            "request_digest",
            "final_attempt_id",
            "manifest_digest",
            "profile_id",
            "scientific_status",
        }
        missing = sorted(required - set(report))
        if missing:
            raise OMLError(
                "SCIENTIFIC_REPORT_CONFLICT",
                "scientific report is missing immutable identity fields",
                evidence=tuple(missing),
                recovery="recreate the report through finalize_case",
            )
        payload = _json(report)
        now = utc_now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT report_json FROM scientific_reports WHERE report_id = ?",
                (report["report_id"],),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                if existing["report_json"] != payload:
                    raise OMLError(
                        "SCIENTIFIC_REPORT_CONFLICT",
                        "an immutable scientific report already exists with different evidence",
                        evidence=(str(report["report_id"]),),
                        recovery="preserve the existing report and finalize a new immutable request identity",
                    )
                receipt = self.get_scientific_report(str(report["report_id"]))
                assert receipt is not None
                return receipt
            run = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (report["run_id"],)
            ).fetchone()
            attempt = connection.execute(
                "SELECT * FROM stage_attempts WHERE attempt_id = ?",
                (report["final_attempt_id"],),
            ).fetchone()
            plan = (
                connection.execute(
                    "SELECT stages_json FROM plans WHERE plan_id = ?", (run["plan_id"],)
                ).fetchone()
                if run is not None
                else None
            )
            identity_matches = (
                run is not None
                and attempt is not None
                and plan is not None
                and report["plan_digest"] == run["plan_digest"]
                and report["manifest_digest"] == run["manifest_digest"]
                and report["profile_id"] == run["execution_profile_id"]
                and attempt["run_id"] == report["run_id"]
                and attempt["stage"] == _loads(plan["stages_json"])[-1]
                and attempt["status"] == "PASSED"
                and report["scientific_status"] in {"PASS", "FAIL", "NOT_EVALUATED", "INCOMPLETE"}
            )
            if not identity_matches:
                connection.rollback()
                raise OMLError(
                    "SCIENTIFIC_REPORT_CONFLICT",
                    "scientific report does not match the immutable run and final attempt",
                    evidence=(str(report["run_id"]), str(report["final_attempt_id"])),
                    recovery="finalize only a passed final stage through finalize_case",
                )
            connection.execute(
                """
                INSERT INTO scientific_reports (
                    report_id, run_id, plan_digest, benchmark_id, convergence_bundle_id,
                    request_digest, final_attempt_id, manifest_digest, profile_id,
                    scientific_status, report_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report["report_id"],
                    report["run_id"],
                    report["plan_digest"],
                    report["benchmark_id"],
                    report["convergence_bundle_id"],
                    report["request_digest"],
                    report["final_attempt_id"],
                    report["manifest_digest"],
                    report["profile_id"],
                    report["scientific_status"],
                    payload,
                    now,
                ),
            )
            connection.commit()
        receipt = self.get_scientific_report(str(report["report_id"]))
        assert receipt is not None
        return receipt
