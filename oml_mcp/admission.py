from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .provenance import digest_json


GIT_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_COMPONENTS = frozenset({"abacus", "librpa", "pyatb"})
PROCESS_STATUSES = frozenset({"PASSED", "FAILED", "INCOMPLETE", "CANCELLED", "UNKNOWN"})
SCIENTIFIC_STATUSES = frozenset({"NOT_EVALUATED", "INCOMPLETE", "PASS", "FAIL"})
PROMOTION_STATES = frozenset({"BLOCKED", "TESTABLE", "EXPERIMENTAL"})
GATE_STATUSES = frozenset({"PASS", "WARN", "FAIL", "NOT_EVALUATED"})


class AdmissionError(ValueError):
    """Raised when admission evidence cannot form a trustworthy receipt."""


@dataclass(frozen=True)
class AdmissionResources:
    compile_jobs: int = 0
    execution_threads: int = 1
    cpu_hours: float = 0.0
    wall_seconds: int = 0
    disk_bytes: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.compile_jobs, bool) or not 0 <= self.compile_jobs <= 16:
            raise AdmissionError("resources.compile_jobs must be between 0 and 16")
        if isinstance(self.execution_threads, bool) or not 1 <= self.execution_threads <= 48:
            raise AdmissionError("resources.execution_threads must be between 1 and 48")
        for name in ("cpu_hours", "wall_seconds", "disk_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise AdmissionError(f"resources.{name} must be a non-negative number")


@dataclass(frozen=True)
class AdmissionReceipt:
    payload: dict[str, Any]
    receipt_digest: str

    def to_dict(self) -> dict[str, Any]:
        data = json.loads(json.dumps(self.payload, sort_keys=True))
        data["receipt_digest"] = self.receipt_digest
        return data


def _require_id(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AdmissionError(f"{label} must be a non-empty string")


def _validate_component_hashes(
    values: dict[str, str],
    *,
    label: str,
    pattern: re.Pattern[str],
) -> None:
    if set(values) != REQUIRED_COMPONENTS:
        raise AdmissionError(f"{label} must contain abacus, librpa, and pyatb")
    for name, value in values.items():
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise AdmissionError(f"{label}.{name} has an invalid digest")


def _parse_time(value: str, label: str) -> datetime:
    _require_id(value, label)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdmissionError(f"{label} must be an ISO-8601 timestamp") from exc


def _validate_artifacts(artifacts: tuple[dict[str, object], ...]) -> None:
    for index, artifact in enumerate(artifacts):
        path = artifact.get("path")
        digest = artifact.get("sha256")
        size = artifact.get("size")
        if not isinstance(path, str) or not path:
            raise AdmissionError(f"artifact_manifest[{index}].path must be non-empty")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise AdmissionError(f"artifact_manifest[{index}].sha256 is invalid")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise AdmissionError(f"artifact_manifest[{index}].size must be non-negative")


def _validate_gates(gates: tuple[dict[str, object], ...]) -> None:
    seen = set()
    for index, gate in enumerate(gates):
        gate_id = gate.get("gate_id")
        status = gate.get("status")
        evidence = gate.get("evidence")
        if not isinstance(gate_id, str) or not gate_id or gate_id in seen:
            raise AdmissionError(f"gate_results[{index}].gate_id is missing or duplicated")
        seen.add(gate_id)
        if status not in GATE_STATUSES:
            raise AdmissionError(f"gate_results[{index}].status is invalid")
        if not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence):
            raise AdmissionError(f"gate_results[{index}].evidence must be a string array")


def build_admission_receipt(
    *,
    campaign_id: str,
    case_id: str,
    route_id: str,
    profile_id: str,
    source_revisions: dict[str, str],
    build_fingerprints: dict[str, str],
    host_fingerprint: dict[str, object],
    input_manifest_sha256: str,
    plan_digest: str,
    stage: str,
    attempt_id: str,
    started_at: str,
    finished_at: str,
    resources: AdmissionResources,
    process_status: str,
    artifact_manifest: tuple[dict[str, object], ...],
    gate_results: tuple[dict[str, object], ...],
    scientific_status: str = "NOT_EVALUATED",
    promotion_eligibility: str = "BLOCKED",
) -> AdmissionReceipt:
    for label, value in (
        ("campaign_id", campaign_id),
        ("case_id", case_id),
        ("route_id", route_id),
        ("profile_id", profile_id),
        ("stage", stage),
        ("attempt_id", attempt_id),
    ):
        _require_id(value, label)
    _validate_component_hashes(
        source_revisions,
        label="source_revisions",
        pattern=GIT_REVISION_PATTERN,
    )
    _validate_component_hashes(
        build_fingerprints,
        label="build_fingerprints",
        pattern=SHA256_PATTERN,
    )
    if not isinstance(host_fingerprint, dict) or not host_fingerprint:
        raise AdmissionError("host_fingerprint must be a non-empty object")
    for label, value in (
        ("input_manifest_sha256", input_manifest_sha256),
        ("plan_digest", plan_digest),
    ):
        if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
            raise AdmissionError(f"{label} must be a SHA-256 digest")
    started = _parse_time(started_at, "started_at")
    finished = _parse_time(finished_at, "finished_at")
    if finished < started:
        raise AdmissionError("finished_at cannot precede started_at")
    if process_status not in PROCESS_STATUSES:
        raise AdmissionError("process_status is invalid")
    if scientific_status not in SCIENTIFIC_STATUSES:
        raise AdmissionError("scientific_status is invalid")
    if promotion_eligibility == "ENABLED":
        raise AdmissionError("ENABLED promotion requires a reviewed profile commit")
    if promotion_eligibility not in PROMOTION_STATES:
        raise AdmissionError("promotion_eligibility is invalid")
    _validate_artifacts(artifact_manifest)
    _validate_gates(gate_results)

    payload: dict[str, Any] = {
        "receipt_schema": "oml.receipt.v2",
        "campaign_id": campaign_id,
        "case_id": case_id,
        "route_id": route_id,
        "profile_id": profile_id,
        "source_revisions": dict(source_revisions),
        "build_fingerprints": dict(build_fingerprints),
        "host_fingerprint": dict(host_fingerprint),
        "input_manifest_sha256": input_manifest_sha256,
        "plan_digest": plan_digest,
        "stage": stage,
        "attempt_id": attempt_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "resources": asdict(resources),
        "process_status": process_status,
        "artifact_manifest": [dict(item) for item in artifact_manifest],
        "gate_results": [dict(item) for item in gate_results],
        "scientific_status": scientific_status,
        "promotion_eligibility": promotion_eligibility,
    }
    return AdmissionReceipt(payload=payload, receipt_digest=digest_json(payload))
