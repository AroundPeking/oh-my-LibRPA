"""Detect in-place parameter drift between a materialized run and what is on disk.

A run directory is an immutable receipt: the plan, the inputs and the stage
scripts were hashed at materialization. Editing `librpa.in`, `INPUT_scf` or a
stage script afterwards is how a lane silently changes mid-run - the 2026-10-30
Si session switched symmetry, nfreq and the Coulomb definition three times that
way, each time discarding hours of compute. This module compares the manifest
against the files that are actually there so the drift is visible before the
next submission instead of after the next wrong result.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class InputDriftError(ValueError):
    """Raised when a run directory has no usable input manifest."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_run_inputs(run_dir: str | Path) -> dict[str, Any]:
    """Compare the run's files against the manifest written at materialization."""
    root = Path(run_dir).expanduser().resolve()
    manifest_path = root / ".oml" / "manifest.json"
    if not manifest_path.is_file():
        raise InputDriftError(f"no manifest at {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputDriftError(f"cannot read {manifest_path}: {exc}") from exc

    changed: list[dict[str, str]] = []
    missing: list[str] = []
    for entry in manifest.get("files", []):
        relative = entry.get("path")
        expected = entry.get("sha256")
        if not relative or not expected:
            continue
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        actual = _sha256(path)
        if actual != expected:
            changed.append({"path": relative, "manifest": expected, "actual": actual})

    return {
        "run_dir": str(root),
        "run_id": manifest.get("run_id"),
        "plan_digest": manifest.get("plan_digest"),
        "manifest_digest": manifest.get("manifest_digest"),
        "checked": len(manifest.get("files", [])),
        "unchanged": len(manifest.get("files", [])) - len(changed) - len(missing),
        "changed": changed,
        "missing": missing,
        "drifted": bool(changed or missing),
    }
