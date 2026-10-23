"""Executable policy registry and effective-definition provenance.

A policy entry is not documentation: it names an enforcement gate, and each
entry here is covered by a test that asserts the gate exists. The effective
definition records which layer (case, seed, policy, retry rule) supplied each
value, so a silent override can never happen again.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


POLICY_SCHEMA = "oml.policy.v1"
POLICY_ROOT = Path(__file__).with_name("policy")
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
VIOLATION_CLASSES = frozenset({"fail_closed", "warn"})
ENFORCEMENT_KINDS = frozenset({"gate"})
REQUIRED_FIELDS = ("schema_version", "id", "title", "rule", "scope", "enforcement", "on_violation", "sources")


class PolicyError(ValueError):
    """Raised when a policy entry is malformed or a definition layer conflicts."""


@dataclass(frozen=True)
class Policy:
    id: str
    title: str
    rule: str
    scope: dict[str, Any]
    enforcement_id: str
    on_violation: str
    sources: tuple[dict[str, Any], ...]


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PolicyError(f"cannot read policy {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PolicyError(f"policy root must be an object: {path}")
    return value


def _validate(value: dict[str, Any], path: Path) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in value]
    if missing:
        raise PolicyError(f"{path}: missing fields {missing}")
    if value["schema_version"] != POLICY_SCHEMA:
        raise PolicyError(f"{path}: unsupported schema_version {value['schema_version']!r}")
    if not ID_PATTERN.match(str(value["id"])):
        raise PolicyError(f"{path}: invalid policy id {value['id']!r}")
    if value["on_violation"] not in VIOLATION_CLASSES:
        raise PolicyError(f"{path}: on_violation must be one of {sorted(VIOLATION_CLASSES)}")
    enforcement = value["enforcement"]
    if not isinstance(enforcement, dict) or enforcement.get("kind") not in ENFORCEMENT_KINDS:
        raise PolicyError(f"{path}: enforcement must be a gate")
    if not str(enforcement.get("id", "")).startswith("policy."):
        raise PolicyError(f"{path}: enforcement gate ids must start with 'policy.'")
    sources = value["sources"]
    if not isinstance(sources, list) or not sources:
        raise PolicyError(f"{path}: sources must be a non-empty list")
    for source in sources:
        if not isinstance(source, dict) or not source.get("kind") or not source.get("ref") or not source.get("accessed"):
            raise PolicyError(f"{path}: every source needs kind, ref and accessed")


def load_policies(root: Path | None = None) -> tuple[Policy, ...]:
    root = root or POLICY_ROOT
    policies: list[Policy] = []
    seen: set[str] = set()
    for path in sorted(root.glob("*.json")):
        value = _load_json(path)
        _validate(value, path)
        if value["id"] in seen:
            raise PolicyError(f"duplicate policy id {value['id']!r}")
        seen.add(value["id"])
        policies.append(
            Policy(
                id=value["id"],
                title=value["title"],
                rule=value["rule"],
                scope=dict(value["scope"]),
                enforcement_id=value["enforcement"]["id"],
                on_violation=value["on_violation"],
                sources=tuple(value["sources"]),
            )
        )
    if not policies:
        raise PolicyError(f"no policies under {root}")
    return tuple(sorted(policies, key=lambda policy: policy.id))


def policy_ids(policies: tuple[Policy, ...] | None = None) -> tuple[str, ...]:
    return tuple(policy.id for policy in (policies or load_policies()))


@dataclass(frozen=True)
class EffectiveDefinition:
    values: dict[str, Any]
    provenance: dict[str, tuple[str, ...]]
    policy_ids: tuple[str, ...] = ()

    def with_layer(self, source: str, mapping: Mapping[str, Any]) -> "EffectiveDefinition":
        values = dict(self.values)
        provenance = dict(self.provenance)
        for key, value in mapping.items():
            values[key] = value
            provenance[key] = (*provenance.get(key, ()), source)
        return EffectiveDefinition(values, provenance, self.policy_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": dict(self.values),
            "provenance": {key: list(value) for key, value in self.provenance.items()},
            "policy_ids": list(self.policy_ids),
        }


def merge_layers(
    *layers: tuple[str, Mapping[str, Any]],
    policy_ids_used: tuple[str, ...] = (),
) -> EffectiveDefinition:
    """Merge definition layers in order; later layers override with provenance."""
    result = EffectiveDefinition(values={}, provenance={}, policy_ids=policy_ids_used)
    for source, mapping in layers:
        if not isinstance(mapping, Mapping):
            raise PolicyError(f"definition layer {source!r} must be a mapping")
        result = result.with_layer(source, mapping)
    return result
