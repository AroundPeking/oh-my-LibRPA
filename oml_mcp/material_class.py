from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


MATERIAL_CLASS_NAMES = {
    "perovskite_gw": "perovskite_gw.json",
    "transition_metal_oxide_gw": "transition_metal_oxide_gw.json",
    "altermagnet_gw": "altermagnet_gw.json",
    "soc_2d_gw": "soc_2d_gw.json",
}
PACKAGED_MATERIAL_CLASS_ROOT = Path(__file__).with_name("material_classes")

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class MaterialClassError(ValueError):
    """Raised when a material-class benchmark identity is malformed or cannot be validated."""


def _packaged_material_class_dir() -> Path:
    return PACKAGED_MATERIAL_CLASS_ROOT


def _repository_material_class_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "benchmarks" / "materials"


def list_material_classes() -> tuple[str, ...]:
    return tuple(MATERIAL_CLASS_NAMES)


def _material_class_path(material_class_id: str) -> Path:
    try:
        name = MATERIAL_CLASS_NAMES[material_class_id]
    except KeyError as exc:
        raise MaterialClassError(
            f"unknown material class: {material_class_id}"
        ) from exc
    packaged = _packaged_material_class_dir() / name
    return packaged if packaged.is_file() else _repository_material_class_dir() / name


def _positive_finite(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise MaterialClassError(f"{label} must be a positive finite number")
    return float(value)


def _validate_sha_tree(value: Any, label: str) -> None:
    if isinstance(value, dict):
        if not value:
            raise MaterialClassError(f"{label} must not be empty")
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise MaterialClassError(f"{label} contains an invalid key")
            _validate_sha_tree(child, f"{label}.{key}")
        return
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise MaterialClassError(f"{label} must contain SHA-256 digests")


def _validate_optional_sha_tree(value: Any, label: str) -> None:
    if value is None:
        return
    _validate_sha_tree(value, label)


def _validate_asset_group(
    value: Any,
    label: str,
    *,
    required: bool,
) -> None:
    if value is None:
        if required:
            raise MaterialClassError(f"{label} is required but was not provided")
        return
    if not isinstance(value, dict):
        raise MaterialClassError(f"{label} must be an object")
    for name, digest in value.items():
        if not isinstance(name, str) or not name:
            raise MaterialClassError(f"{label} contains an invalid asset name")
        if not isinstance(digest, str) or SHA256_PATTERN.fullmatch(digest) is None:
            raise MaterialClassError(f"{label}.{name} must be a SHA-256 digest")


def _validate_magnetic_order(value: Any) -> None:
    if not isinstance(value, dict):
        raise MaterialClassError("magnetic_order must be an object")
    allowed = {
        "none",
        "collinear",
        "antiferromagnetic",
        "ferromagnetic",
        "noncollinear",
        "soc",
    }
    if value.get("type") not in allowed:
        raise MaterialClassError("magnetic_order.type is not a recognised magnetic order")
    if value.get("type") == "none" and value.get("nspin", 1) != 1:
        raise MaterialClassError("a non-magnetic order requires nspin=1")
    if value.get("type") != "none" and int(value.get("nspin", 1)) < 2:
        raise MaterialClassError("a magnetic or SOC order requires nspin>=2")


def validate_material_class(entry: dict[str, Any]) -> None:
    if entry.get("schema") != "oml.material-class.v1":
        raise MaterialClassError("material-class schema must be oml.material-class.v1")
    material_class_id = entry.get("material_class_id")
    if material_class_id not in MATERIAL_CLASS_NAMES:
        raise MaterialClassError("material_class_id is not registered")

    material = entry.get("material")
    if not isinstance(material, dict):
        raise MaterialClassError("material must be an object")
    if not isinstance(material.get("formula"), str) or not material["formula"]:
        raise MaterialClassError("material.formula must be a non-empty string")

    reference_status = entry.get("reference_status")
    # The input-file hash tree is only frozen once a reference run exists. For a
    # REFERENCE_PENDING entry the structure/input identity has not been frozen yet.
    identity = material.get("identity_sha256")
    if reference_status == "REFERENCE_AVAILABLE":
        _validate_sha_tree(identity, "material.identity_sha256")
    else:
        _validate_optional_sha_tree(identity, "material.identity_sha256")

    _validate_asset_group(
        material.get("pseudopotentials"), "material.pseudopotentials", required=True
    )
    _validate_asset_group(
        material.get("orbitals"), "material.orbitals", required=True
    )
    # The auxiliary basis (ABFS) is generated separately on the remote host. It is
    # frozen for materials whose ABFS is already produced; it is pending (None) for
    # those that still need generation. A frozen reference must carry its ABFS.
    _validate_asset_group(
        material.get("auxiliary_bases"),
        "material.auxiliary_bases",
        required=(reference_status == "REFERENCE_AVAILABLE"),
    )

    structure = material.get("structure")
    if not isinstance(structure, dict):
        raise MaterialClassError("material.structure must be an object")
    if not isinstance(structure.get("space_group"), str):
        raise MaterialClassError("material.structure.space_group must be a string")
    if not isinstance(structure.get("prototype"), str):
        raise MaterialClassError("material.structure.prototype must be a string")

    _validate_magnetic_order(material.get("magnetic_order"))

    software = entry.get("software_identity")
    if not isinstance(software, dict):
        raise MaterialClassError("software_identity must be an object")
    # Software identity is only fully frozen once a reference run exists. For a
    # REFERENCE_PENDING entry the executable hashes and full revisions may be
    # unknown (null) and a short branch/revision tag may be supplied instead.
    for key in ("abacus_revision", "librpa_revision", "pyatb_revision"):
        value = software.get(key)
        if value is None:
            if reference_status == "REFERENCE_AVAILABLE":
                raise MaterialClassError(
                    f"software_identity.{key} is required for a frozen reference"
                )
            continue
        if isinstance(value, str) and GIT_REVISION_PATTERN.fullmatch(value) is not None:
            continue
        # A short descriptive revision tag (e.g. branch head) is acceptable while pending.
        if reference_status == "REFERENCE_PENDING" and isinstance(value, str) and value:
            continue
        raise MaterialClassError(f"software_identity.{key} is invalid")
    for key in ("abacus_executable_sha256", "librpa_executable_sha256"):
        value = software.get(key)
        if value is None:
            if reference_status == "REFERENCE_AVAILABLE":
                raise MaterialClassError(
                    f"software_identity.{key} is required for a frozen reference"
                )
            continue
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            raise MaterialClassError(f"software_identity.{key} is invalid")

    reference = entry.get("reference")
    if reference is None:
        if entry.get("reference_status") != "REFERENCE_PENDING":
            raise MaterialClassError(
                "reference_status must be REFERENCE_PENDING when no reference is frozen"
            )
    else:
        if not isinstance(reference, dict):
            raise MaterialClassError("reference must be an object when provided")
        if entry.get("reference_status") != "REFERENCE_AVAILABLE":
            raise MaterialClassError(
                "reference_status must be REFERENCE_AVAILABLE when a reference is frozen"
            )


def load_material_class(
    material_class_id: str,
    *,
    hydrate_reference: bool = False,
) -> dict[str, Any]:
    path = _material_class_path(material_class_id)
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterialClassError(
            f"cannot read material-class {path}: {exc}"
        ) from exc
    if not isinstance(entry, dict):
        raise MaterialClassError("material-class root must be an object")
    validate_material_class(entry)
    if hydrate_reference and entry.get("reference_status") == "REFERENCE_AVAILABLE":
        _hydrate_reference_candidate(entry, path)
    return entry


def _hydrate_reference_candidate(entry: dict[str, Any], identity_path: Path) -> None:
    """Attach the frozen numerical reference candidate to a REFERENCE_AVAILABLE entry.

    The identity JSON stores only reference metadata (source, produced date, a
    compact window summary and the artifact digest) so that inspecting an identity
    stays lightweight. The full candidate (window states) lives in a sibling
    artifact file and is hydrated on demand, matching the route-benchmark pattern
    of a small identity plus separately loaded evidence.
    """
    reference = entry.get("reference")
    if not isinstance(reference, dict):
        raise MaterialClassError(
            "a REFERENCE_AVAILABLE entry must carry a reference object"
        )
    artifact_name = reference.get("artifact")
    if not isinstance(artifact_name, str) or not artifact_name:
        raise MaterialClassError(
            "a REFERENCE_AVAILABLE entry must name its reference artifact"
        )
    artifact_path = identity_path.with_name(artifact_name)
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MaterialClassError(
            f"cannot read reference artifact {artifact_path}: {exc}"
        ) from exc
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict):
        raise MaterialClassError(
            "reference artifact must contain a candidate object"
        )
    reference["candidate"] = candidate
