from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .artifacts import inspect_headwing_directory, inspect_stru_out
from .models import GateResult, InputDocument, ValidationReport
from .parsers import ParseError, parse_abacus_input, parse_bool, parse_float, parse_int, parse_librpa_input
from .profiles import load_profile


VALID_STAGES = frozenset({"input", "pre_librpa"})


def _pass(gate_id: str, message: str, *evidence: str) -> GateResult:
    return GateResult(gate_id, "PASS", message, tuple(evidence))


def _skip(gate_id: str, message: str) -> GateResult:
    return GateResult(gate_id, "SKIP", message)


def _fail(gate_id: str, message: str, evidence: Iterable[str], repair: str) -> GateResult:
    return GateResult(gate_id, "FAIL", message, tuple(evidence), repair)


def _warn(gate_id: str, message: str, evidence: Iterable[str], repair: str) -> GateResult:
    return GateResult(gate_id, "WARN", message, tuple(evidence), repair)


def _value_gate(
    document: InputDocument,
    gate_id: str,
    required: dict[str, str],
    *,
    label: str,
) -> GateResult:
    mismatches = [
        f"{key}={document.value(key)!r} (expected {expected!r})"
        for key, expected in required.items()
        if (document.value(key) or "").strip().lower() != expected.lower()
    ]
    if mismatches:
        assignments = ", ".join(f"{key} = {value}" for key, value in required.items())
        return _fail(
            gate_id,
            f"{label} does not match the pinned workflow contract",
            (str(document.path), *mismatches),
            f"set {assignments}",
        )
    return _pass(gate_id, f"{label} matches the pinned workflow contract", str(document.path))


def _dataset_root(case_root: Path, librpa: InputDocument) -> Path:
    value = (librpa.value("input_dir", ".") or ".").strip().strip("'\"")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else case_root / path).resolve()


def _find_by_prefix(root: Path, prefix: str) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(sorted((path for path in root.rglob("*") if path.is_file() and path.name.startswith(prefix))))


def _parse_inputs(case_root: Path) -> tuple[InputDocument, InputDocument] | ValidationReport:
    profile = load_profile()
    try:
        abacus = parse_abacus_input(case_root / "INPUT_scf")
        librpa = parse_librpa_input(case_root / "librpa.in")
    except ParseError as exc:
        return ValidationReport(
            profile["profile_id"],
            (
                _fail(
                    "case.inputs",
                    str(exc),
                    (str(case_root),),
                    "provide parseable INPUT_scf and librpa.in files at the case root",
                ),
            ),
        )
    return abacus, librpa


def _duplicates_gate(abacus: InputDocument, librpa: InputDocument) -> GateResult:
    duplicates = [
        *(f"INPUT_scf:{key}" for key in abacus.duplicates),
        *(f"librpa.in:{key}" for key in librpa.duplicates),
    ]
    if duplicates:
        return _fail(
            "inputs.duplicates",
            "duplicate assignments make the effective workflow ambiguous",
            duplicates,
            "keep exactly one assignment for each listed key",
        )
    return _pass("inputs.duplicates", "workflow inputs contain no duplicate assignments")


def _task_gate(librpa: InputDocument, task: str) -> GateResult:
    actual = (librpa.value("task") or "").strip().lower()
    expected = "rpa" if task == "rpa" else "g0w0"
    if actual == "g0w0_band" and expected == "g0w0":
        return _warn(
            "librpa.task",
            "g0w0_band is a deprecated LibRPA 0.7.0 alias",
            (str(librpa.path), "task=g0w0_band"),
            "replace it with task = g0w0",
        )
    if actual != expected:
        return _fail(
            "librpa.task",
            f"LibRPA task {actual!r} does not match the requested {task} route",
            (str(librpa.path),),
            f"set task = {expected}",
        )
    return _pass("librpa.task", f"LibRPA task is {expected}", str(librpa.path))


def _unsupported_key_gate(librpa: InputDocument, unsupported: dict[str, str]) -> GateResult:
    found = [(key, unsupported[key]) for key in unsupported if key in librpa.keys]
    if found:
        return _fail(
            "librpa.unsupported_keys",
            "librpa.in uses OML symmetry keys that LibRPA 0.7.0 does not parse",
            tuple(f"{key} -> {replacement}" for key, replacement in found),
            "replace " + ", ".join(f"{key} with {replacement}" for key, replacement in found),
        )
    return _pass(
        "librpa.unsupported_keys",
        "librpa.in contains no obsolete OML symmetry spellings",
        str(librpa.path),
    )


def _bool_value(document: InputDocument, key: str) -> bool | None:
    try:
        return parse_bool(document.value(key))
    except ParseError:
        return None


def _int_value(document: InputDocument, key: str) -> int | None:
    try:
        return parse_int(document.value(key), name=key)
    except ParseError:
        return None


def _symmetry_gate(
    abacus: InputDocument,
    librpa: InputDocument,
    *,
    task: str,
    requested: bool,
    soc: bool,
) -> GateResult:
    abacus_symmetry = _int_value(abacus, "symmetry")
    actual_soc = _bool_value(librpa, "use_soc")
    keys = ("use_symmetry_rpa",) if task == "rpa" else ("use_symmetry_exx", "use_symmetry_gw")
    switches = {key: _bool_value(librpa, key) for key in keys}
    expected_enabled = requested and not soc
    expected_abacus = 1 if expected_enabled else -1
    problems: list[str] = []
    if abacus_symmetry != expected_abacus:
        problems.append(f"symmetry={abacus_symmetry!r} expected {expected_abacus}")
    if actual_soc is None or actual_soc != soc:
        problems.append(f"use_soc={librpa.value('use_soc')!r} expected {int(soc)}")
    for key, value in switches.items():
        if value is None or value != expected_enabled:
            problems.append(f"{key}={librpa.value(key)!r} expected {'t' if expected_enabled else 'f'}")
    if problems:
        return _fail(
            "symmetry.alignment",
            "ABACUS, LibRPA, requested symmetry, and SOC settings are inconsistent",
            (str(abacus.path), str(librpa.path), *problems),
            (
                f"set ABACUS symmetry = {expected_abacus}, use_soc = {int(soc)}, and "
                + ", ".join(f"{key} = {'t' if expected_enabled else 'f'}" for key in keys)
            ),
        )
    return _pass(
        "symmetry.alignment",
        "ABACUS and LibRPA symmetry settings match the requested SOC lane",
        str(abacus.path),
        str(librpa.path),
    )


def _producer_uses_shrink(abacus: InputDocument) -> bool | None:
    value = abacus.value("shrink_abfs_pca_thr")
    if value is None:
        return False
    try:
        return parse_float(value, name="shrink_abfs_pca_thr") >= 0
    except ParseError:
        return None


def _shrink_alignment_gate(abacus: InputDocument, librpa: InputDocument) -> tuple[GateResult, bool]:
    producer = _producer_uses_shrink(abacus)
    consumer = _bool_value(librpa, "use_shrink_abfs")
    if producer is None or consumer is None or producer != consumer:
        return (
            _fail(
                "shrink.alignment",
                "ABACUS shrink production and LibRPA shrink consumption are inconsistent",
                (
                    str(abacus.path),
                    str(librpa.path),
                    f"producer={producer!r}",
                    f"consumer={consumer!r}",
                ),
                "set shrink_abfs_pca_thr >= 0 together with use_shrink_abfs = t, or disable both",
            ),
            bool(consumer),
        )
    return (
        _pass(
            "shrink.alignment",
            f"ABACUS and LibRPA consistently {'enable' if consumer else 'disable'} shrink",
            str(abacus.path),
            str(librpa.path),
        ),
        bool(consumer),
    )


def _artifact_existence_gate(root: Path, names: Iterable[str], gate_id: str, label: str) -> GateResult:
    missing = tuple(name for name in names if not (root / name).is_file())
    if missing:
        return _fail(
            gate_id,
            f"{label} are incomplete",
            missing,
            f"regenerate the missing {label} with the pinned ABACUS reader-v1 producer",
        )
    return _pass(gate_id, f"all required {label} exist", str(root))


def _prefix_artifact_gate(
    root: Path,
    prefixes: Iterable[str],
    *,
    gate_id: str = "dataset.v1_prefixes",
    label: str = "reader-v1 dataset file families",
) -> GateResult:
    missing = tuple(prefix for prefix in prefixes if not _find_by_prefix(root, prefix))
    if missing:
        return _fail(
            gate_id,
            f"{label} are incomplete",
            missing,
            f"regenerate the missing {label} with ABACUS out_librpa_reader_version = 1",
        )
    return _pass(gate_id, f"required {label} exist", str(root))


def _format_family_gate(root: Path, v1_prefixes: Iterable[str], legacy_prefixes: Iterable[str]) -> GateResult:
    v1 = tuple(prefix for prefix in v1_prefixes if _find_by_prefix(root, prefix))
    legacy = tuple(prefix for prefix in legacy_prefixes if _find_by_prefix(root, prefix))
    if v1 and legacy:
        return _fail(
            "dataset.format_families",
            "dataset mixes legacy and reader-v1 file families",
            (*v1, *legacy),
            "remove the stale family and regenerate a single reader-v1 dataset",
        )
    if legacy:
        return _fail(
            "dataset.format_families",
            "dataset contains legacy files while OML production requires reader-v1",
            legacy,
            "regenerate the dataset with out_librpa_reader_version = 1 and reader versions = 1",
        )
    return _pass("dataset.format_families", "dataset contains only reader-v1 file families", str(root))


def validate_case(
    path: str | Path,
    *,
    task: str,
    system_type: str,
    use_symmetry: bool = False,
    soc: bool = False,
    stage: str = "pre_librpa",
) -> ValidationReport:
    del system_type  # Reserved for route-specific numerical gates in later milestones.
    profile = load_profile()
    profile_id = profile["profile_id"]
    case_root = Path(path).expanduser().resolve()
    normalized_stage = stage.strip().lower()
    if normalized_stage not in VALID_STAGES:
        return ValidationReport(
            profile_id,
            (
                _fail(
                    "validation.stage",
                    f"unsupported validation stage: {stage}",
                    (stage,),
                    "use stage = input or stage = pre_librpa",
                ),
            ),
        )
    parsed = _parse_inputs(case_root)
    if isinstance(parsed, ValidationReport):
        return parsed
    abacus, librpa = parsed
    contract = profile["contract"]
    production = contract["librpa"]["production"]
    normalized_task = task.strip().lower()

    gates: list[GateResult] = [
        _duplicates_gate(abacus, librpa),
        _value_gate(
            abacus,
            "abacus.producer",
            {"basis_type": "lcao", "rpa": "1"},
            label="ABACUS producer settings",
        ),
        _value_gate(
            abacus,
            "abacus.reader_v1",
            {"out_librpa_reader_version": "1"},
            label="ABACUS reader-v1 selector",
        ),
        _unsupported_key_gate(librpa, contract["librpa"]["unsupported_oml_keys"]),
        _task_gate(librpa, normalized_task),
        _value_gate(
            librpa,
            "librpa.reader_v1",
            {"version_coul_reader": "1", "version_lri_reader": "1"},
            label="LibRPA reader-v1 selectors",
        ),
        _value_gate(
            librpa,
            "librpa.v1_names",
            {
                "prefix_coul_full": production["prefix_coul_full"],
                "prefix_coul_cut": production["prefix_coul_cut"],
                "prefix_lri_coeff": production["prefix_lri_coeff"],
                "fn_stru": production["fn_stru"],
                "fn_bz_sampling": production["fn_bz_sampling"],
                "fn_basis_wfc": production["fn_basis_wfc"],
                "fn_basis_aux": production["fn_basis_aux"],
            },
            label="LibRPA reader-v1 names",
        ),
        _symmetry_gate(
            abacus,
            librpa,
            task=normalized_task,
            requested=use_symmetry,
            soc=soc,
        ),
    ]
    shrink_gate, shrink = _shrink_alignment_gate(abacus, librpa)
    gates.append(shrink_gate)
    if shrink:
        gates.append(
            _value_gate(
                librpa,
                "shrink.names",
                {
                    "prefix_lri_coeff_shrink": production["prefix_lri_coeff_shrink"],
                    "prefix_shrink_sinvs": production["prefix_shrink_sinvS"],
                    "fn_basis_aux_shrink": production["fn_basis_aux_shrink"],
                },
                label="reader-v1 shrink names",
            )
        )
        if librpa.value("prefix_lri_coeff") == librpa.value("prefix_lri_coeff_shrink"):
            gates.append(
                _fail(
                    "shrink.prefix_separation",
                    "full and shrink LRI prefixes overlap",
                    (librpa.value("prefix_lri_coeff") or "",),
                    "use distinct v1_Cs_data_ and v1_Cs_shrinked_data_ prefixes",
                )
            )
        else:
            gates.append(_pass("shrink.prefix_separation", "full and shrink LRI prefixes are distinct"))

    gates.append(
        _pass(
            "symmetry.sidecars",
            "legacy symmetry sidecars are not required; LibRPA reconstructs rotations from stru_out",
        )
    )
    if normalized_stage == "input":
        gates.extend(
            (
                _skip("dataset.artifacts", "producer outputs are not required at the input stage"),
                _skip("dataset.v1_prefixes", "producer outputs are not required at the input stage"),
                _skip("dataset.format_families", "producer outputs are not required at the input stage"),
                _skip("shrink.artifacts", "producer outputs are not required at the input stage"),
                _skip("stru_out.format", "stru_out is not required at the input stage"),
                _skip("symmetry.stru_out", "stru_out is not required at the input stage"),
                _skip("pyatb.headwing", "PyATB outputs are not required at the input stage"),
            )
        )
        return ValidationReport(profile_id, tuple(gates))

    dataset = _dataset_root(case_root, librpa)
    base_names = (
        production["fn_stru"],
        production["fn_bz_sampling"],
        production["fn_basis_wfc"],
        production["fn_basis_aux"],
        "band_out",
    )
    gates.append(_artifact_existence_gate(dataset, base_names, "dataset.artifacts", "base artifacts"))
    required_prefixes = (
        production["prefix_coul_full"],
        production["prefix_coul_cut"],
        production["prefix_lri_coeff"],
    )
    gates.append(_prefix_artifact_gate(dataset, required_prefixes))
    gates.append(
        _format_family_gate(
            dataset,
            contract["artifacts"]["v1_prefixes"],
            contract["artifacts"]["legacy_prefixes"],
        )
    )
    if shrink:
        shrink_names = (production["fn_basis_aux_shrink"],)
        gates.append(_artifact_existence_gate(dataset, shrink_names, "shrink.artifacts", "shrink artifacts"))
        gates.append(
            _prefix_artifact_gate(
                dataset,
                (production["prefix_lri_coeff_shrink"], production["prefix_shrink_sinvS"]),
                gate_id="shrink.v1_prefixes",
                label="reader-v1 shrink file families",
            )
        )
    else:
        gates.append(_skip("shrink.artifacts", "shrink is disabled consistently"))

    stru_info = inspect_stru_out(dataset / production["fn_stru"])
    gates.extend(stru_info.gates)
    expected_stru_symmetry = use_symmetry and not soc
    if stru_info.accepted and bool(stru_info.metadata["has_symmetry"]) != expected_stru_symmetry:
        gates.append(
            _fail(
                "symmetry.stru_out",
                "stru_out symmetry metadata does not match the selected route",
                (str(stru_info.path),),
                "regenerate stru_out with the matching ABACUS SCF symmetry setting",
            )
        )
    elif stru_info.accepted:
        gates.append(_pass("symmetry.stru_out", "stru_out symmetry metadata matches the selected route"))
    else:
        gates.append(
            _skip("symmetry.stru_out", "stru_out symmetry cannot be checked until its format is valid")
        )

    headwing = _bool_value(librpa, "replace_w_head")
    if headwing:
        gates.extend(inspect_headwing_directory(case_root / contract["pyatb_adapter"]["directory"]).gates)
    elif headwing is False:
        gates.append(_skip("pyatb.headwing", "replace_w_head is disabled"))
    else:
        gates.append(
            _fail(
                "pyatb.headwing",
                "replace_w_head is missing or invalid",
                (str(librpa.path),),
                "set replace_w_head = t for periodic head/wing or f for the molecular short route",
            )
        )
    return ValidationReport(profile_id, tuple(gates))
