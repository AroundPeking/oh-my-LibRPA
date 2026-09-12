from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .stage_inspection import inspect_stage_outputs


KNOWN_ISSUE_SCHEMA = "oml.known-issue.v1"
PACKAGED_KNOWN_ISSUE_ROOT = Path(__file__).with_name("known_issues")
ISSUE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CONFIDENCE_LEVELS = {"established", "tentative"}
# Tokens that are too generic to carry diagnostic signal for a keyword match.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
        "into", "is", "it", "not", "of", "on", "or", "the", "to", "with",
        "file", "files", "input", "output", "path", "dir", "directory", "data",
        "cannot", "found", "missing", "present", "incomplete", "failed",
    }
)
# Characteristic diagnostic terms that are strong enough to match on their own.
_STRONG_TERMS = frozenset(
    {"coulomb", "symmetry", "exx", "ewald", "nbands", "nbasis", "hermitian", "psd"}
)


class KnownIssueError(ValueError):
    """Raised when a known-issue entry is malformed or cannot be loaded."""


@dataclass(frozen=True)
class KnownIssue:
    issue_id: str
    title: str
    symptom: str
    root_cause: str
    minimal_fix: str
    validation: str
    avoid: str
    source: str
    confidence: str
    gate_id: str | None = None
    parameters: dict[str, str] = None  # type: ignore[assignment]

    def to_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(asdict(self), sort_keys=True))


@dataclass(frozen=True)
class DiagnosticMatch:
    """A ranked match between a gate failure and a known issue."""

    gate_id: str
    issue: KnownIssue
    rank: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "issue": self.issue.to_dict(),
            "rank": self.rank,
            "reason": self.reason,
        }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KnownIssueError(f"cannot read known issue {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise KnownIssueError(f"known-issue root must be an object: {path}")
    return value


def _validate_known_issue(value: dict[str, Any]) -> None:
    if value.get("schema") != KNOWN_ISSUE_SCHEMA:
        raise KnownIssueError(f"known-issue schema must be {KNOWN_ISSUE_SCHEMA}")
    issue_id = value.get("issue_id")
    if not isinstance(issue_id, str) or ISSUE_ID_PATTERN.fullmatch(issue_id) is None:
        raise KnownIssueError("known-issue issue_id is invalid")
    for field in ("title", "symptom", "root_cause", "minimal_fix", "validation", "avoid", "source"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise KnownIssueError(f"known-issue {field} must be a non-empty string")
    if value.get("confidence") not in CONFIDENCE_LEVELS:
        raise KnownIssueError("known-issue confidence must be established or tentative")
    gate_id = value.get("gate_id")
    if gate_id is not None and not isinstance(gate_id, str):
        raise KnownIssueError("known-issue gate_id must be a string or null")
    parameters = value.get("parameters")
    if parameters is not None and not isinstance(parameters, dict):
        raise KnownIssueError("known-issue parameters must be an object or null")


def _issue_from_json(value: dict[str, Any]) -> KnownIssue:
    _validate_known_issue(value)
    return KnownIssue(
        issue_id=value["issue_id"],
        title=value["title"],
        symptom=value["symptom"],
        root_cause=value["root_cause"],
        minimal_fix=value["minimal_fix"],
        validation=value["validation"],
        avoid=value["avoid"],
        source=value["source"],
        confidence=value["confidence"],
        gate_id=value.get("gate_id"),
        parameters=value.get("parameters") or {},
    )


def list_known_issues() -> tuple[KnownIssue, ...]:
    """Return every packaged known issue in a deterministic order."""
    entries: list[KnownIssue] = []
    for path in sorted(PACKAGED_KNOWN_ISSUE_ROOT.glob("*.json")):
        entries.append(_issue_from_json(_load_json(path)))
    return tuple(entries)


def load_known_issue(issue_id: str) -> KnownIssue:
    """Load a single known issue by id."""
    if not isinstance(issue_id, str) or ISSUE_ID_PATTERN.fullmatch(issue_id) is None:
        raise KnownIssueError(f"invalid known-issue id: {issue_id!r}")
    path = PACKAGED_KNOWN_ISSUE_ROOT / f"{issue_id}.json"
    if not path.is_file():
        raise KnownIssueError(f"known-issue is not available: {issue_id}")
    return _issue_from_json(_load_json(path))


def _gate_to_keywords(gate_id: str | None, message: str) -> set[str]:
    """Lowercase keyword set from a gate id and message for loose matching.

    Stopwords are dropped so generic words such as 'not' or 'file' do not
    produce false matches; characteristic diagnostic terms are kept.
    """
    text = f"{gate_id or ''} {message}".lower()
    tokens = set(re.findall(r"[a-z0-9_]+", text))
    return {token for token in tokens if token not in _STOPWORDS}


def _gate_family(gate_id: str) -> str:
    """Return the leading family token of a gate id.

    Both framework gate ids (``coulomb.psd_hermitian.iq_1``) and descriptive
    curated ids (``coulomb-negative-eig-sqrt-threshold-gate``) start with a
    characteristic family word, so this lets a curated issue attach to the
    real framework gate for the same physics.
    """
    head = re.split(r"[.\-]", gate_id, maxsplit=1)[0]
    return head.lower()


def _matches_gate(issue: KnownIssue, gate_id: str, tokens: set[str]) -> bool:
    """Match a known issue to a gate by gate id family or keyword overlap."""
    issue_gate = issue.gate_id
    if issue_gate:
        if issue_gate == gate_id:
            return True
        # A dotted issue gate (``coulomb.psd_hermitian``) is the namespace of a
        # per-instance real gate (``coulomb.psd_hermitian.iq_7``).
        if "." in issue_gate and gate_id.startswith(issue_gate + "."):
            return True
        if issue_gate.startswith("stage.") and gate_id.startswith("stage."):
            # Compare the stage segment only so a generic issue can match any
            # stage-specific gate (e.g. stage.scf.completion matches stage.scf.*).
            if issue_gate.split(".")[1] == gate_id.split(".")[1]:
                return True
        # Same characteristic family word (coulomb/symmetry/exx/...).
        family = _gate_family(issue_gate)
        if family in _STRONG_TERMS and family == _gate_family(gate_id):
            return True
    issue_keywords = set(re.findall(r"[a-z0-9_]+", issue.title.lower())) - _STOPWORDS
    # Require a meaningful overlap: at least one strong diagnostic term shared,
    # or at least two non-generic keywords shared.
    strong = tokens & issue_keywords & _STRONG_TERMS
    overlap = tokens & issue_keywords
    return bool(strong) or len(overlap) >= 2


def _rank_match(issue: KnownIssue, gate_id: str, tokens: set[str]) -> int:
    """Higher rank means a stronger match. Exact gate id > namespace > family > keyword."""
    issue_gate = issue.gate_id
    if issue_gate and issue_gate == gate_id:
        return 100
    if issue_gate and "." in issue_gate and gate_id.startswith(issue_gate + "."):
        # The issue names the exact gate namespace that produced this failure.
        return 95
    if issue_gate and issue_gate.startswith("stage.") and gate_id.startswith("stage."):
        if issue_gate.split(".")[1] == gate_id.split(".")[1]:
            return 50
    family = _gate_family(issue_gate) if issue_gate else ""
    if family in _STRONG_TERMS and family == _gate_family(gate_id):
        return 70
    issue_keywords = set(re.findall(r"[a-z0-9_]+", issue.title.lower())) - _STOPWORDS
    strong = len(tokens & issue_keywords & _STRONG_TERMS)
    overlap = len(tokens & issue_keywords)
    if strong:
        return 30 + 10 * strong
    if overlap >= 2:
        return 20 + overlap
    return 0


def diagnose_run(
    run_path: str | Path,
    *,
    stage: str | None = None,
    max_matches: int = 5,
) -> dict[str, Any]:
    """Match gate failures in a run against the curated known-issue store.

    This is a reference-free diagnostic: it replays the stage inspection gate
    battery and maps any FAIL/WARN gate to the most likely known issue by gate
    id, shared stage, and keyword overlap. It never auto-submits a fix; it
    returns ranked remediation candidates for the human or agent to review.
    """
    if stage is not None:
        report = inspect_stage_outputs(run_path, stage)
        reports = [report]
    else:
        from .stage_templates import CONTROLLED_PERIODIC_STAGES

        reports = [inspect_stage_outputs(run_path, s) for s in CONTROLLED_PERIODIC_STAGES]

    issues = list_known_issues()
    matches: list[DiagnosticMatch] = []
    failing_gates: list[dict[str, Any]] = []
    for report in reports:
        for gate in report["gates"]:
            if gate["status"] not in {"FAIL", "WARN"}:
                continue
            gate_id = str(gate["gate_id"])
            failing_gates.append(gate)
            tokens = _gate_to_keywords(gate_id, str(gate["message"]))
            for issue in issues:
                if not _matches_gate(issue, gate_id, tokens):
                    continue
                rank = _rank_match(issue, gate_id, tokens)
                if rank <= 0:
                    continue
                matches.append(DiagnosticMatch(gate_id=gate_id, issue=issue, rank=rank, reason="gate/keyword match"))

    # Keep the single best match per issue so one issue that fires for several
    # gates (e.g. the Coulomb PSD gate for each q block) is reported once.
    best_by_issue: dict[str, DiagnosticMatch] = {}
    for match in matches:
        previous = best_by_issue.get(match.issue.issue_id)
        if previous is None or match.rank > previous.rank:
            best_by_issue[match.issue.issue_id] = match
    matches = list(best_by_issue.values())

    # Sort by rank (descending), then by issue id for determinism.
    matches.sort(key=lambda m: (-m.rank, m.issue.issue_id))
    top = matches[:max_matches]
    return {
        "schema_version": 1,
        "run_path": str(Path(run_path).expanduser().resolve()),
        "stage": stage,
        "failing_gates": failing_gates,
        "matches": [match.to_dict() for match in top],
        "matched_count": len(top),
    }


def resolve_run(
    run_path: str | Path,
    *,
    stage: str | None = None,
    route_id: str | None = None,
    material_class: str | None = None,
    max_actions: int = 3,
) -> dict[str, Any]:
    """Turn a run's gate failures into an ordered, actionable resolution plan.

    ``diagnose_run`` answers "what is probably wrong"; this answers "what do I
    actually do next". Each action carries the concrete fix, the check that
    proves the fix worked, and the dead end to avoid. When the issue names
    parameters and a prescription exists for the route/system family, the
    prescribed value is attached so the caller does not have to guess a number.

    Nothing is applied or submitted here: the plan is returned for review, which
    keeps the no-automatic-mutation rule intact.
    """
    diagnosis = diagnose_run(run_path, stage=stage, max_matches=max_actions)
    actions: list[dict[str, Any]] = []
    for match in diagnosis["matches"]:
        issue = match["issue"]
        parameters = issue.get("parameters") or {}
        action: dict[str, Any] = {
            "priority": len(actions) + 1,
            "gate_id": match["gate_id"],
            "issue_id": issue["issue_id"],
            "title": issue["title"],
            "match_rank": match["rank"],
            "confidence": issue["confidence"],
            "do": issue["minimal_fix"],
            "verify": issue["validation"],
            "avoid": issue["avoid"],
            "source": issue["source"],
        }
        if parameters:
            action["parameters"] = dict(parameters)
        if route_id is not None and material_class is not None and parameters:
            prescribed = prescribed_values(route_id, material_class, tuple(parameters))
            if prescribed:
                action["prescribed_parameters"] = prescribed
        actions.append(action)

    return {
        "schema": "oml.resolution-plan.v1",
        "schema_version": 1,
        "run_path": diagnosis["run_path"],
        "stage": diagnosis["stage"],
        "actionable": bool(actions),
        "action_count": len(actions),
        "failing_gate_count": len(diagnosis["failing_gates"]),
        "failing_gates": diagnosis["failing_gates"],
        "actions": actions,
        "note": (
            "This plan is advisory. No fix is applied and no job is submitted; "
            "review each action before acting."
        ),
    }


def prescribed_values(
    route_id: str, material_class: str, axes: tuple[str, ...]
) -> dict[str, Any]:
    """Return prescribed values for the named axes, when the prescription pins them."""
    try:
        from .parameter_prescriptions import load_prescription

        prescription = load_prescription(route_id, material_class)
    except (ImportError, ValueError):
        return {}
    values: dict[str, Any] = {}
    for axis in axes:
        rule = prescription.parameters.get(axis)
        if rule is None or rule.target is None:
            continue
        values[axis] = {
            "target": rule.target,
            "allowed_range": list(rule.allowed_range),
            "rule": rule.per_system_override_rule,
        }
    return values


def write_resolution_plan(plan: dict[str, Any], path: str | Path) -> Path:
    """Persist a resolution plan for later review."""
    if plan.get("schema") != "oml.resolution-plan.v1":
        raise KnownIssueError("resolution plan schema must be oml.resolution-plan.v1")
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    return target
