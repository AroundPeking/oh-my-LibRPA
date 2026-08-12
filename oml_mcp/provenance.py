from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


EXECUTION_INPUT_NAMES = frozenset(
    {
        "INPUT",
        "INPUT_scf",
        "INPUT_nscf",
        "KPT",
        "KPT_scf",
        "KPT_nscf",
        "STRU",
        "librpa.in",
        "geometry.in",
        "get_diel.py",
        "output_librpa.py",
        "preprocess_abacus_for_librpa_band.py",
        "perform.sh",
    }
)
EXECUTION_ASSET_SUFFIXES = frozenset({".upf", ".orb", ".abfs"})
SKIP_PARTS = frozenset({".git", ".oml", ".venv", "__pycache__", "OUT.ABACUS"})


class ProvenanceError(ValueError):
    """Raised when an execution-input snapshot cannot be reproduced safely."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_execution_input(path: Path) -> bool:
    return path.name in EXECUTION_INPUT_NAMES or path.suffix.lower() in EXECUTION_ASSET_SUFFIXES


def execution_input_manifest(source: str | Path) -> tuple[dict[str, Any], ...]:
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise ProvenanceError(f"execution source must be a directory: {root}")

    items: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts) or not _is_execution_input(path):
            continue
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise ProvenanceError(f"execution input escapes the source root: {relative.as_posix()}")
        stat = resolved.stat()
        items.append(
            {
                "path": relative.as_posix(),
                "size": stat.st_size,
                "sha256": sha256_file(resolved),
            }
        )
    if not items:
        raise ProvenanceError(f"no approved execution inputs found under {root}")
    return tuple(items)


def source_manifest_digest(manifest: Iterable[dict[str, Any]]) -> str:
    normalized = [
        {
            "path": str(item["path"]),
            "size": int(item["size"]),
            "sha256": str(item["sha256"]),
        }
        for item in manifest
    ]
    return digest_json(normalized)
