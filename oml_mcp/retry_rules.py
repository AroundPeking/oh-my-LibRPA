"""Structured symptom-to-candidate-experiment rules for the retry card.

Each rule records the observable symptom, the evidence to collect first, the
candidate experiments with their expected improvement and guard, the stop
condition, and dated sources. Candidate experiments are proposals: they never
change boundaries or parameters automatically.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RETRY_RULE_SCHEMA = "oml.retry-rule.v1"
PACKAGED_RULE_ROOT = Path(__file__).with_name("retry_rules")
RULE_ID_PATTERN = re.compile(r"^r[1-9][0-9]?$")
LAYERS = frozenset({"exx", "gw", "both", "any"})
REQUIRED_FIELDS = (
    "schema_version",
    "id",
    "title",
    "symptom",
    "layer",
    "evidence_required",
    "candidate_experiments",
    "stop_condition",
    "sources",
)


class RetryRuleError(ValueError):
    """Raised when a retry rule is malformed or cannot be loaded."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RetryRuleError(f"cannot read retry rule {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RetryRuleError(f"retry rule root must be an object: {path}")
    return value


def _validate(rule: dict[str, Any], path: Path) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in rule]
    if missing:
        raise RetryRuleError(f"{path}: missing fields {missing}")
    if rule["schema_version"] != RETRY_RULE_SCHEMA:
        raise RetryRuleError(f"{path}: unsupported schema_version {rule['schema_version']!r}")
    if not RULE_ID_PATTERN.match(str(rule["id"])):
        raise RetryRuleError(f"{path}: invalid rule id {rule['id']!r}")
    if rule["layer"] not in LAYERS:
        raise RetryRuleError(f"{path}: layer must be one of {sorted(LAYERS)}")
    for field in ("title", "symptom", "stop_condition"):
        if not isinstance(rule[field], str) or not rule[field].strip():
            raise RetryRuleError(f"{path}: {field} must be a non-empty string")
    evidence = rule["evidence_required"]
    if not isinstance(evidence, list) or not evidence:
        raise RetryRuleError(f"{path}: evidence_required must be a non-empty list")
    experiments = rule["candidate_experiments"]
    if not isinstance(experiments, list) or not experiments:
        raise RetryRuleError(f"{path}: candidate_experiments must be a non-empty list")
    for experiment in experiments:
        if (
            not isinstance(experiment, dict)
            or not experiment.get("action")
            or not experiment.get("expected_improvement")
        ):
            raise RetryRuleError(
                f"{path}: every candidate experiment needs action and expected_improvement"
            )
    sources = rule["sources"]
    if not isinstance(sources, list) or not sources:
        raise RetryRuleError(f"{path}: sources must be a non-empty list")
    for source in sources:
        if not isinstance(source, dict) or not source.get("kind") or not source.get("ref"):
            raise RetryRuleError(f"{path}: every source needs kind and ref")
        if not source.get("accessed"):
            raise RetryRuleError(f"{path}: every source needs an accessed date")


def load_rules(root: Path | None = None) -> tuple[dict[str, Any], ...]:
    root = root or PACKAGED_RULE_ROOT
    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.json")):
        rule = _load_json(path)
        _validate(rule, path)
        if rule["id"] in seen:
            raise RetryRuleError(f"duplicate retry rule id {rule['id']!r}")
        seen.add(rule["id"])
        rules.append(rule)
    if not rules:
        raise RetryRuleError(f"no retry rules under {root}")
    return tuple(sorted(rules, key=lambda rule: int(str(rule["id"])[1:])))


def lookup(rule_id: str, rules: tuple[dict[str, Any], ...] | None = None) -> dict[str, Any]:
    for rule in rules or load_rules():
        if rule["id"] == rule_id:
            return rule
    raise RetryRuleError(f"unknown retry rule {rule_id!r}")


def rule_ids(rules: tuple[dict[str, Any], ...] | None = None) -> tuple[str, ...]:
    return tuple(rule["id"] for rule in (rules or load_rules()))
