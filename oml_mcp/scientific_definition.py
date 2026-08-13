from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .parsers import (
    ParseError,
    parse_abacus_input,
    parse_abacus_kpt,
    parse_bool,
    parse_float,
    parse_int,
    parse_librpa_input,
)
from .provenance import digest_json


CONVERGENCE_AXES = {
    "nfreq": frozenset({"librpa.nfreq"}),
    "empty_states": frozenset({"abacus.nbands"}),
    "screening_kgrid": frozenset({"kpoints.scf.grid"}),
}
WORKFLOW_HELPERS = (
    "perform.sh",
    "get_diel.py",
    "output_librpa.py",
    "preprocess_abacus_for_librpa_band.py",
)


class ScientificDefinitionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        fields: tuple[str, ...] = (),
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.fields = fields
        self.details = details or {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScientificDefinitionError(
            "DEFINITION_RECEIPT_INVALID", f"cannot read {path}: {exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ScientificDefinitionError(
            "DEFINITION_RECEIPT_INVALID", f"receipt root must be an object: {path}"
        )
    return value


def _same_input_value(
    scf: Any,
    nscf: Any,
    key: str,
    default: str,
    parser: Any,
) -> Any:
    left = parser(scf.value(key, default), name=key) if parser in {parse_int, parse_float} else parser(scf.value(key, default))
    right = parser(nscf.value(key, default), name=key) if parser in {parse_int, parse_float} else parser(nscf.value(key, default))
    if left != right:
        raise ScientificDefinitionError(
            "DEFINITION_INPUT_MISMATCH",
            f"SCF and NSCF {key} differ",
            fields=(f"abacus.{key}",),
            details={"scf": left, "nscf": right},
        )
    return left


def _optional_float(document: Any, key: str, default: str = "0") -> float:
    return parse_float(document.value(key, default), name=key)


def _optional_bool(document: Any, key: str, default: str = "f") -> bool:
    return parse_bool(document.value(key, default))


def _asset_groups(manifest: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    groups = {
        "pseudopotentials": {},
        "orbitals": {},
        "auxiliary_bases": {},
    }
    for item in manifest:
        name = str(item.get("path", ""))
        digest = str(item.get("sha256", ""))
        suffix = Path(name).suffix.lower()
        if suffix == ".upf":
            groups["pseudopotentials"][name] = digest
        elif suffix == ".orb":
            groups["orbitals"][name] = digest
        elif suffix == ".abfs":
            groups["auxiliary_bases"][name] = digest
    return groups


def _manifest_digest(manifest: list[dict[str, Any]], name: str) -> str | None:
    item = next((entry for entry in manifest if entry.get("path") == name), None)
    return str(item["sha256"]) if item is not None else None


def build_definition_signature(run_root: str | Path) -> dict[str, object]:
    root = Path(run_root).expanduser().resolve()
    try:
        plan = _read_json(root / ".oml" / "plan.json")
        execution = _read_json(root / ".oml" / "execution.json")
        scf = parse_abacus_input(root / "INPUT_scf")
        nscf = parse_abacus_input(root / "INPUT_nscf")
        kpt_scf = parse_abacus_kpt(root / "KPT_scf")
        kpt_nscf = parse_abacus_kpt(root / "KPT_nscf")
        librpa = parse_librpa_input(root / "librpa.in")
    except ParseError as exc:
        raise ScientificDefinitionError("DEFINITION_INPUT_INVALID", str(exc)) from exc

    if kpt_scf.get("mode") != "mesh":
        raise ScientificDefinitionError(
            "DEFINITION_INPUT_INVALID", "KPT_scf must define a regular screening mesh"
        )
    manifest = plan.get("source_manifest")
    if not isinstance(manifest, list):
        raise ScientificDefinitionError(
            "DEFINITION_RECEIPT_INVALID", "plan source_manifest must be an array"
        )
    options = plan.get("options")
    if not isinstance(options, dict):
        raise ScientificDefinitionError(
            "DEFINITION_RECEIPT_INVALID", "plan options must be an object"
        )
    version_evidence = execution.get("version_evidence")
    if not isinstance(version_evidence, dict):
        raise ScientificDefinitionError(
            "DEFINITION_RECEIPT_INVALID", "execution version_evidence must be an object"
        )
    components = version_evidence.get("components")
    executables = version_evidence.get("executables", {})
    if not isinstance(components, dict) or not isinstance(executables, dict):
        raise ScientificDefinitionError(
            "DEFINITION_RECEIPT_INVALID", "software evidence is incomplete"
        )
    revisions = {}
    for name in ("abacus", "librpa", "pyatb"):
        component = components.get(name)
        if not isinstance(component, dict) or not isinstance(component.get("actual_revision"), str):
            raise ScientificDefinitionError(
                "DEFINITION_RECEIPT_INVALID", f"missing actual {name} revision"
            )
        revisions[name] = component["actual_revision"]
    executable_hashes = {}
    for name in ("abacus", "librpa"):
        item = executables.get(name)
        if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
            raise ScientificDefinitionError(
                "DEFINITION_RECEIPT_INVALID", f"missing {name} executable hash"
            )
        executable_hashes[name] = item["sha256"]

    nspin = _same_input_value(scf, nscf, "nspin", "1", parse_int)
    nbands = _same_input_value(scf, nscf, "nbands", "0", parse_int)
    ecutwfc = _same_input_value(scf, nscf, "ecutwfc", "0", parse_float)
    if nspin <= 0 or nbands <= 0 or ecutwfc <= 0:
        raise ScientificDefinitionError(
            "DEFINITION_INPUT_INVALID", "nspin, nbands, and ecutwfc must be positive"
        )
    definition = {
        "profile_id": plan.get("profile_id"),
        "route": plan.get("route"),
        "task": options.get("task"),
        "system_type": options.get("system_type"),
        "soc": bool(options.get("soc")),
        "symmetry": bool(options.get("use_symmetry")),
        "software": {
            "revisions": revisions,
            "executables": executable_hashes,
        },
        "structure": {"stru_sha256": _manifest_digest(manifest, "STRU")},
        "assets": _asset_groups(manifest),
        "workflow_helpers": {
            name: _manifest_digest(manifest, name) for name in WORKFLOW_HELPERS
        },
        "abacus": {
            "basis_type": scf.value("basis_type", ""),
            "nspin": nspin,
            "nbands": nbands,
            "ecutwfc": ecutwfc,
            "smearing_method": scf.value("smearing_method", ""),
            "smearing_sigma": _optional_float(scf, "smearing_sigma"),
            "scf_symmetry": parse_int(scf.value("symmetry", "0"), name="symmetry"),
            "nscf_symmetry": parse_int(nscf.value("symmetry", "0"), name="symmetry"),
            "out_librpa_reader_version": parse_int(
                scf.value("out_librpa_reader_version", "0"),
                name="out_librpa_reader_version",
            ),
            "exx_pca_threshold": _optional_float(scf, "exx_pca_threshold"),
            "shrink_abfs_pca_thr": _optional_float(scf, "shrink_abfs_pca_thr", "-1"),
            "shrink_lu_inv_thr": _optional_float(scf, "shrink_lu_inv_thr"),
        },
        "kpoints": {"scf": kpt_scf, "band_path": kpt_nscf},
        "librpa": {
            "task": librpa.value("task", ""),
            "nfreq": parse_int(librpa.value("nfreq", "0"), name="nfreq"),
            "option_dielect_func": parse_int(
                librpa.value("option_dielect_func", "0"), name="option_dielect_func"
            ),
            "replace_w_head": _optional_bool(librpa, "replace_w_head"),
            "use_fullcoul_exx": _optional_bool(librpa, "use_fullcoul_exx"),
            "use_shrink_abfs": _optional_bool(librpa, "use_shrink_abfs"),
            "use_shrink_chi": _optional_bool(librpa, "use_shrink_chi"),
            "use_soc": parse_int(librpa.value("use_soc", "0"), name="use_soc"),
            "version_coul_reader": parse_int(
                librpa.value("version_coul_reader", "-1"), name="version_coul_reader"
            ),
            "version_lri_reader": parse_int(
                librpa.value("version_lri_reader", "-1"), name="version_lri_reader"
            ),
            "sqrt_coulomb_threshold": _optional_float(librpa, "sqrt_coulomb_threshold"),
            "libri_chi0_threshold_C": _optional_float(librpa, "libri_chi0_threshold_C"),
            "libri_chi0_threshold_G": _optional_float(librpa, "libri_chi0_threshold_G"),
            "libri_g0w0_threshold_C": _optional_float(librpa, "libri_g0w0_threshold_C"),
            "libri_g0w0_threshold_G": _optional_float(librpa, "libri_g0w0_threshold_G"),
            "libri_g0w0_threshold_Wc": _optional_float(librpa, "libri_g0w0_threshold_Wc"),
        },
    }
    return {"schema_version": 1, "digest": digest_json(definition), **definition}


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key in sorted(value):
            if not prefix and key in {"digest", "schema_version"}:
                continue
            child = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(value[key], child))
        return flattened
    return {prefix: value}


def compare_definitions(
    left: dict[str, object],
    right: dict[str, object],
    *,
    allowed_axis: str | None = None,
) -> list[dict[str, object]]:
    left_fields = _flatten(left)
    right_fields = _flatten(right)
    names = sorted(set(left_fields) | set(right_fields))
    differences = [
        {"field": name, "left": left_fields.get(name), "right": right_fields.get(name)}
        for name in names
        if left_fields.get(name) != right_fields.get(name)
    ]
    if allowed_axis is None:
        return differences
    allowed = CONVERGENCE_AXES.get(allowed_axis)
    if allowed is None:
        raise ScientificDefinitionError(
            "CONVERGENCE_AXIS_INVALID",
            f"unsupported convergence axis: {allowed_axis}",
            fields=tuple(item["field"] for item in differences),
        )
    extra = tuple(item["field"] for item in differences if item["field"] not in allowed)
    changed_allowed = {item["field"] for item in differences if item["field"] in allowed}
    if extra or changed_allowed != set(allowed):
        fields = tuple(item["field"] for item in differences)
        raise ScientificDefinitionError(
            "MULTIPLE_DEFINITION_CHANGES",
            "convergence pair changes more than the declared axis",
            fields=fields,
            details={"axis": allowed_axis, "allowed_fields": sorted(allowed)},
        )
    return []
