from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .artifacts import (
    inspect_coulomb_v1,
    inspect_cs_v1,
    inspect_eigenvector_v1,
    inspect_headwing_directory,
    inspect_shrink_sinvs_v1,
    inspect_split_basis,
    inspect_stru_out,
)
from .models import GateResult, InputDocument, ValidationReport
from .parsers import (
    ParseError,
    parse_abacus_input,
    parse_abacus_kpt,
    parse_band_out,
    parse_bool,
    parse_bz_sampling,
    parse_float,
    parse_int,
    parse_librpa_input,
    parse_vxc_out,
)
from .profiles import is_strict_2d_sos_rpa_profile, load_profile


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


def _screening_grid_alignment_gate(
    case_root: Path,
    bz_sampling: dict[str, object],
) -> GateResult:
    kpt_path = case_root / "KPT_scf"
    try:
        kpt = parse_abacus_kpt(kpt_path)
    except ParseError as exc:
        return _fail(
            "dataset.screening_grid",
            str(exc),
            (str(kpt_path),),
            "provide the exact KPT_scf used by the ABACUS producer",
        )
    if kpt.get("mode") != "mesh":
        return _fail(
            "dataset.screening_grid",
            "KPT_scf does not define a regular screening mesh",
            (str(kpt_path),),
            "use the exact regular-mesh KPT_scf from the ABACUS producer",
        )

    input_grid = tuple(int(value) for value in kpt["grid"])
    producer_grid = tuple(int(value) for value in bz_sampling["grid"])
    input_count = input_grid[0] * input_grid[1] * input_grid[2]
    producer_count = int(bz_sampling["nk_full"])
    if input_grid != producer_grid:
        return _fail(
            "dataset.screening_grid",
            "KPT_scf mesh does not match the grid embedded in bz_sampling_out",
            (
                f"KPT_scf={input_count} ({'x'.join(map(str, input_grid))})",
                f"bz_sampling_out={producer_count} ({'x'.join(map(str, producer_grid))})",
            ),
            "restore KPT_scf from the same ABACUS producer run as bz_sampling_out",
        )
    return GateResult(
        gate_id="dataset.screening_grid",
        status="PASS",
        message="KPT_scf matches the screening grid embedded in bz_sampling_out",
        evidence=(str(kpt_path),),
        measurements={"grid": list(input_grid), "nk_full": input_count},
    )


def _find_by_prefix(root: Path, prefix: str) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(
        sorted(path for path in root.iterdir() if path.is_file() and path.name.startswith(prefix))
    )


def _parse_inputs(
    case_root: Path, *, profile_id: str | None = None
) -> tuple[InputDocument, InputDocument] | ValidationReport:
    profile = load_profile(profile_id=profile_id) if profile_id is not None else load_profile()
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


def _fullcoul_exx_gate(librpa: InputDocument) -> GateResult:
    raw = librpa.value("use_fullcoul_exx")
    enabled = _bool_value(librpa, "use_fullcoul_exx")
    if raw is not None and enabled is None:
        return _fail(
            "librpa.fullcoul_exx",
            "use_fullcoul_exx is not a valid LibRPA boolean switch",
            (str(librpa.path), f"use_fullcoul_exx={raw}"),
            "set use_fullcoul_exx = f, or set t only for an explicit definition-matched full-Coulomb EXX calculation",
        )
    if enabled:
        return _warn(
            "librpa.fullcoul_exx",
            "full-Coulomb EXX changes the physical definition from the LibRPA 0.7.0 ABACUS regression baseline",
            (str(librpa.path), "use_fullcoul_exx=t"),
            "use use_fullcoul_exx = f unless full-Coulomb EXX was explicitly requested, then require a definition-matched benchmark",
        )
    return _pass(
        "librpa.fullcoul_exx",
        "EXX uses the LibRPA 0.7.0 ABACUS regression Coulomb definition",
        str(librpa.path),
    )


def _frequency_grid_gate(
    librpa: InputDocument,
    frequency_contract: dict[str, object],
) -> GateResult:
    default_grid = str(frequency_contract["default"])
    recognized_types = frozenset(
        str(value) for value in frequency_contract["recognized_types"]
    )
    production_types = frozenset(
        str(value) for value in frequency_contract["production_types"]
    )
    debug_only_types = frozenset(
        str(value) for value in frequency_contract["debug_only_types"]
    )
    minimax_counts = tuple(
        int(value) for value in frequency_contract["minimax_nfreq_supported"]
    )
    grid_type = (
        librpa.value("tfgrids_type")
        or librpa.value("tfgrid_type")
        or default_grid
    ).strip()
    try:
        nfreq = parse_int(
            librpa.value("nfreq", str(frequency_contract["default_nfreq"])),
            name="nfreq",
        )
    except ParseError as exc:
        return _fail(
            "librpa.frequency_grid",
            str(exc),
            (str(librpa.path),),
            "set nfreq to a positive integer supported by the selected frequency grid",
        )
    if grid_type not in recognized_types:
        return _fail(
            "librpa.frequency_grid",
            f"LibRPA does not recognize frequency grid type {grid_type!r}",
            (str(librpa.path),),
            "use one of " + ", ".join(sorted(recognized_types)),
        )
    if grid_type not in production_types:
        if grid_type in debug_only_types:
            summary = (
                f"{grid_type} is a debug-only time-frequency grid with placeholder transforms"
            )
        else:
            summary = (
                f"{grid_type} supplies no time grid, while the conventional frequency-domain "
                "chi0 builder is not implemented in the pinned LibRPA source"
            )
        return _fail(
            "librpa.frequency_grid",
            summary,
            (str(librpa.path), f"tfgrids_type={grid_type}"),
            "use minimax with a supported nfreq for production RPA/GW response calculations",
        )
    if nfreq <= 0:
        return _fail(
            "librpa.frequency_grid",
            "nfreq must be positive",
            (str(librpa.path), f"nfreq={nfreq}"),
            "set nfreq to a positive integer supported by the selected frequency grid",
        )
    if grid_type == "minimax" and nfreq not in minimax_counts:
        supported = ", ".join(str(value) for value in minimax_counts)
        return _fail(
            "librpa.frequency_grid",
            f"GreenX minimax does not support nfreq={nfreq} in the pinned LibRPA source",
            (str(librpa.path), f"tfgrids_type={grid_type}", f"nfreq={nfreq}"),
            f"set nfreq to one of {supported}; the pinned production route requires minimax",
        )
    return _pass(
        "librpa.frequency_grid",
        f"{grid_type} accepts nfreq={nfreq} in the pinned LibRPA source",
        str(librpa.path),
    )


def _periodic_3d_gw_continuation_gate(
    librpa: InputDocument,
    profile: dict[str, object],
    *,
    task: str,
    system_type: str,
) -> GateResult:
    route_contract = profile["contract"].get("periodic_3d_gw")
    periodic_3d_gw = task == "gw" and system_type.strip().lower() in {
        "solid",
        "periodic",
    }
    if not isinstance(route_contract, dict) or not periodic_3d_gw:
        return _skip(
            "librpa.periodic_3d_gw_continuation",
            "the current periodic 3D GW continuation contract does not apply",
        )

    required = route_contract["analytic_continuation"]
    actual_grid = (librpa.value("tfgrids_type") or "").strip()
    actual_nparams = _int_value(librpa, "n_params_anacon")
    actual_solver = _int_value(librpa, "option_qpe_solver")
    actual_adaptive = _bool_value(librpa, "use_qpe_adaptive_damp")
    mismatches = []
    if actual_grid != required["tfgrids_type"]:
        mismatches.append(
            f"tfgrids_type={librpa.value('tfgrids_type')!r} "
            f"expected {required['tfgrids_type']}"
        )
    if actual_nparams != required["n_params_anacon"]:
        mismatches.append(
            f"n_params_anacon={librpa.value('n_params_anacon')!r} "
            f"expected {required['n_params_anacon']}"
        )
    if actual_solver != required["option_qpe_solver"]:
        mismatches.append(
            f"option_qpe_solver={librpa.value('option_qpe_solver')!r} "
            f"expected {required['option_qpe_solver']}"
        )
    if actual_adaptive is not required["use_qpe_adaptive_damp"]:
        mismatches.append(
            f"use_qpe_adaptive_damp={librpa.value('use_qpe_adaptive_damp')!r} expected f"
        )
    if mismatches:
        return _fail(
            "librpa.periodic_3d_gw_continuation",
            "periodic 3D GW analytic-continuation controls do not match the current benchmark",
            (str(librpa.path), *mismatches),
            (
                "set tfgrids_type = minimax, n_params_anacon = 6, "
                "option_qpe_solver = 0, and use_qpe_adaptive_damp = f"
            ),
        )
    return _pass(
        "librpa.periodic_3d_gw_continuation",
        "periodic 3D GW analytic-continuation controls match the current benchmark",
        str(librpa.path),
    )


def _unsupported_key_gate(librpa: InputDocument, unsupported: dict[str, str]) -> GateResult:
    found = [(key, unsupported[key]) for key in unsupported if key in librpa.keys]
    if found:
        return _fail(
            "librpa.unsupported_keys",
            "librpa.in uses obsolete OML keys that the pinned LibRPA does not parse",
            tuple(f"{key} -> {replacement}" for key, replacement in found),
            "replace " + ", ".join(f"{key} with {replacement}" for key, replacement in found),
        )
    return _pass(
        "librpa.unsupported_keys",
        "librpa.in contains no obsolete OML key spellings",
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


def _headwing_policy_gate(
    librpa: InputDocument,
    task: str,
    system_type: str,
    requested: bool | None,
    strict_2d_sos_rpa: bool = False,
) -> GateResult:
    actual = _bool_value(librpa, "replace_w_head")
    normalized_system = system_type.strip().lower()
    periodic_3d = task == "gw" and normalized_system in {"solid", "periodic"}
    strict_2d = (
        task == "gw" or (task == "rpa" and strict_2d_sos_rpa)
    ) and normalized_system in {"2d", "two-dimensional"}
    expected = (True if requested is None else requested) if periodic_3d else strict_2d
    if actual is None or actual != expected:
        return _fail(
            "pyatb.policy",
            "replace_w_head does not match the selected task and system route",
            (
                str(librpa.path),
                f"task={task}",
                f"system_type={system_type}",
                f"replace_w_head={librpa.value('replace_w_head')!r}",
            ),
            f"set replace_w_head = {'t' if expected else 'f'}",
        )
    return _pass(
        "pyatb.policy",
        f"replace_w_head is {'enabled' if expected else 'disabled'} for the selected route",
        str(librpa.path),
    )


def _route_policy_gate(
    task: str,
    system_type: str,
    use_symmetry: bool,
    profile: dict[str, Any],
    response_method: str,
) -> GateResult:
    normalized_system = system_type.strip().lower()
    if is_strict_2d_sos_rpa_profile(profile["profile_id"]):
        if (
            task != "rpa"
            or normalized_system not in {"2d", "two-dimensional"}
            or response_method != "sos"
        ):
            return _fail(
                "route.strict_2d_sos_rpa",
                "the selected profile only admits strict-2D SOS-RPA",
                (
                    f"task={task}",
                    f"system_type={system_type}",
                    f"response_method={response_method}",
                ),
                "select task=rpa, system_type=2d, and response_method=sos",
            )
        return _pass(
            "route.strict_2d_sos_rpa",
            "task, system type, and response method select strict-2D SOS-RPA",
        )
    if task == "gw" and normalized_system in {"2d", "two-dimensional"}:
        blocked = profile["capabilities"]["strict_2d_gw"]
        return _fail(
            "route.strict_2d_capability",
            "strict 2D GW is blocked for the pinned LibRPA profile",
            (
                blocked["reason_code"],
                blocked["component_revision"],
            ),
            "pin a corrected LibRPA revision and add every declared strict-2D gate",
        )
    molecular = normalized_system in {"atom", "molecule", "molecular"}
    if task == "gw" and molecular and use_symmetry:
        return _fail(
            "route.policy",
            "molecular GW does not support the periodic spatial-symmetry lane",
            (f"task={task}", f"system_type={system_type}", f"use_symmetry={use_symmetry}"),
            "set use_symmetry = false for molecular GW",
        )
    return _pass("route.policy", "task and system type select a supported OML route")


def _strict_2d_sos_rpa_input_gate(
    librpa: InputDocument,
    profile: dict[str, Any],
) -> GateResult:
    if not is_strict_2d_sos_rpa_profile(profile["profile_id"]):
        return _skip(
            "librpa.strict_2d_sos_rpa",
            "the selected profile is not the strict-2D SOS-RPA replay route",
        )
    required = profile["contract"]["strict_2d_sos_rpa"]["required_input"]
    mismatches: list[str] = []
    for key in ("replace_w_head", "use_2d_dielectric", "use_pyatb"):
        actual = _bool_value(librpa, key)
        if actual is not required[key]:
            mismatches.append(f"{key}={librpa.value(key)!r} expected t")
    mode = (librpa.value("rpa_headwing_mode") or "").strip().lower()
    if mode != required["rpa_headwing_mode"]:
        mismatches.append(
            f"rpa_headwing_mode={librpa.value('rpa_headwing_mode')!r} expected qavg"
        )
    if _int_value(librpa, "option_dielect_func") != required["option_dielect_func"]:
        mismatches.append(
            f"option_dielect_func={librpa.value('option_dielect_func')!r} expected 3"
        )
    if _int_value(librpa, "rpa_headwing_body_start") != required["rpa_headwing_body_start"]:
        mismatches.append(
            "rpa_headwing_body_start="
            f"{librpa.value('rpa_headwing_body_start')!r} expected 1"
        )
    if "head_only" in librpa.keys:
        mismatches.append("head_only must be absent")
    if mismatches:
        return _fail(
            "librpa.strict_2d_sos_rpa",
            "librpa.in does not match the strict-2D SOS-RPA qavg contract",
            (str(librpa.path), *mismatches),
            (
                "enable replace_w_head/use_2d_dielectric/use_pyatb, set "
                "option_dielect_func=3, rpa_headwing_mode=qavg and "
                "rpa_headwing_body_start=1, and remove head_only"
            ),
        )
    return _pass(
        "librpa.strict_2d_sos_rpa",
        "librpa.in matches the strict-2D SOS-RPA qavg contract",
        str(librpa.path),
    )


def _map_kpoints_by_coordinates(
    targets: Iterable[tuple[float, float, float]],
    sources: Iterable[tuple[float, float, float]],
    *,
    tolerance: float = 1e-5,
) -> tuple[int, ...]:
    source_list = tuple(sources)
    used: set[int] = set()
    mapping: list[int] = []
    for target_index, target in enumerate(targets, start=1):
        match = next(
            (
                source_index
                for source_index, source in enumerate(source_list)
                if source_index not in used
                and all(
                    abs((lhs - rhs) - round(lhs - rhs)) <= tolerance
                    for lhs, rhs in zip(target, source, strict=True)
                )
            ),
            None,
        )
        if match is None:
            raise ValueError(f"SCF k-point {target_index} has no unique PyATB full-grid match")
        used.add(match)
        mapping.append(match + 1)
    return tuple(mapping)


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


def _strict2d_coulomb_head_gate(root: Path, filename: str) -> GateResult:
    path = root / filename
    if not path.is_file() or path.stat().st_size <= 0:
        return _fail(
            "strict2d.coulomb_head",
            "strict-2D Coulomb head artifact is missing or empty",
            (str(path),),
            "reuse the non-empty librpa_2d_coulomb_head.dat from the validated producer",
        )
    return _pass(
        "strict2d.coulomb_head",
        "strict-2D Coulomb head artifact exists and is non-empty",
        str(path),
    )


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


def _reader_v1_payload_gates(
    root: Path,
    production: dict[str, object],
    *,
    shrink: bool,
    atom_types: tuple[int, ...],
    expected_q_points: frozenset[int] | None,
    require_cut_coulomb: bool,
) -> tuple[GateResult, ...]:
    wfc_info = inspect_split_basis(root / str(production["fn_basis_wfc"]), atom_types)
    aux_info = inspect_split_basis(root / str(production["fn_basis_aux"]), atom_types)
    shrink_info = (
        inspect_split_basis(root / str(production["fn_basis_aux_shrink"]), atom_types)
        if shrink
        else None
    )
    basis_infos = (wfc_info, aux_info) + ((shrink_info,) if shrink_info is not None else ())
    basis_failures = tuple(
        f"{info.path}: {gate.message}"
        for info in basis_infos
        for gate in info.gates
        if gate.status == "FAIL"
    )
    if basis_failures:
        basis_gate = _fail(
            "basis.v1",
            "split-basis metadata is not readable by the pinned LibRPA contract",
            basis_failures,
            "regenerate basis_wfc_out, basis_aux_out, and enabled shrink basis metadata with ABACUS reader-v1",
        )
        basis_ready = False
    else:
        basis_gate = _pass(
            "basis.v1",
            "split-basis metadata is internally consistent with stru_out",
            *(str(info.path) for info in basis_infos),
        )
        basis_ready = True

    full_paths = _find_by_prefix(root, str(production["prefix_coul_full"]))
    cut_paths = (
        _find_by_prefix(root, str(production["prefix_coul_cut"]))
        if require_cut_coulomb
        else ()
    )
    cs_paths = _find_by_prefix(root, str(production["prefix_lri_coeff"]))
    shrink_cs_paths = (
        _find_by_prefix(root, str(production["prefix_lri_coeff_shrink"])) if shrink else ()
    )
    sinvs_paths = (
        _find_by_prefix(root, str(production["prefix_shrink_sinvS"])) if shrink else ()
    )

    full_infos = tuple(inspect_coulomb_v1(path) for path in full_paths)
    cut_infos = tuple(inspect_coulomb_v1(path) for path in cut_paths)
    payload_infos = [*full_infos, *cut_infos]
    sinvs_infos = ()
    cross_check_failures: list[str] = []
    if basis_ready:
        wfc_sizes = tuple(wfc_info.metadata["atom_sizes"])
        aux_sizes = tuple(aux_info.metadata["atom_sizes"])
        coulomb_sizes = (
            tuple(shrink_info.metadata["atom_sizes"])
            if shrink_info is not None
            else aux_sizes
        )
        for info in (*full_infos, *cut_infos):
            if info.accepted and tuple(info.metadata["atom_naux"]) != coulomb_sizes:
                cross_check_failures.append(
                    f"{info.path}: Coulomb per-atom auxiliary sizes "
                    f"{tuple(info.metadata['atom_naux'])} != selected basis {coulomb_sizes}"
                )
        payload_infos.extend(
            inspect_cs_v1(path, wfc_atom_sizes=wfc_sizes, aux_atom_sizes=aux_sizes)
            for path in cs_paths
        )
        if shrink_info is not None:
            shrink_sizes = tuple(shrink_info.metadata["atom_sizes"])
            payload_infos.extend(
                inspect_cs_v1(path, wfc_atom_sizes=wfc_sizes, aux_atom_sizes=shrink_sizes)
                for path in shrink_cs_paths
            )
            sinvs_infos = tuple(
                inspect_shrink_sinvs_v1(
                    path,
                    expected_rows=sum(shrink_sizes),
                    expected_cols=sum(aux_sizes),
                )
                for path in sinvs_paths
            )
            payload_infos.extend(sinvs_infos)

    if expected_q_points is not None and shrink:
        sinvs_q = {
            int(iq)
            for info in sinvs_infos
            if info.accepted
            for iq in info.metadata["q_indices"]
        }
        if sinvs_q != expected_q_points:
            cross_check_failures.append(
                "shrink_sinvS q-point coverage "
                f"{sorted(sinvs_q)} != expected {sorted(expected_q_points)}"
            )

    payload_failures = tuple(
        f"{info.path}: {gate.message}"
        for info in payload_infos
        for gate in info.gates
        if gate.status == "FAIL"
    ) + tuple(cross_check_failures)
    if not basis_ready:
        payload_gate = _skip(
            "dataset.v1_payloads",
            "reader-v1 matrix payloads cannot be fully checked until split-basis metadata is valid",
        )
    elif payload_failures:
        payload_gate = _fail(
            "dataset.v1_payloads",
            "one or more reader-v1 matrix files have invalid headers or payload bounds",
            payload_failures,
            "regenerate the listed reader-v1 file families from one pinned ABACUS run",
        )
    else:
        payload_gate = _pass(
            "dataset.v1_payloads",
            "Coulomb, Cs, and enabled shrink reader-v1 files have valid headers and payload bounds",
            str(root),
        )

    full_q = {int(info.metadata["iq"]) for info in full_infos if info.accepted}
    cut_q = {int(info.metadata["iq"]) for info in cut_infos if info.accepted}
    if expected_q_points is not None and (
        full_q != expected_q_points
        or (require_cut_coulomb and cut_q != expected_q_points)
    ):
        q_gate = _fail(
            "dataset.coulomb_q",
            "Coulomb reader-v1 q-point coverage does not match bz_sampling_out",
            (
                f"expected={sorted(expected_q_points)}",
                f"full={sorted(full_q)}",
                f"cut={sorted(cut_q) if require_cut_coulomb else 'not required'}",
            ),
            "regenerate bz_sampling_out and both Coulomb families from the same ABACUS producer run",
        )
    elif require_cut_coulomb and full_q and cut_q and full_q != cut_q:
        q_gate = _fail(
            "dataset.coulomb_q",
            "full and cut Coulomb reader-v1 families cover different q-point sets",
            (f"full={sorted(full_q)}", f"cut={sorted(cut_q)}"),
            "regenerate full and cut Coulomb files from the same ABACUS producer run",
        )
    elif not full_q or (require_cut_coulomb and not cut_q):
        q_gate = _skip(
            "dataset.coulomb_q",
            "required Coulomb q-point sets cannot be checked until their files are valid",
        )
    else:
        q_gate = _pass(
            "dataset.coulomb_q",
            (
                "full and cut Coulomb reader-v1 families cover the expected q-point set"
                if require_cut_coulomb
                else "full Coulomb reader-v1 family covers the expected q-point set"
            ),
            str(root),
        )
    return basis_gate, payload_gate, q_gate


def validate_case(
    path: str | Path,
    *,
    task: str,
    system_type: str,
    use_symmetry: bool = False,
    soc: bool = False,
    headwing: bool | None = None,
    stage: str = "pre_librpa",
    response_method: str = "sos",
    profile_id: str | None = None,
) -> ValidationReport:
    profile = load_profile(profile_id=profile_id) if profile_id is not None else load_profile()
    selected_profile_id = profile["profile_id"]
    case_root = Path(path).expanduser().resolve()
    normalized_stage = stage.strip().lower()
    if normalized_stage not in VALID_STAGES:
        return ValidationReport(
            selected_profile_id,
            (
                _fail(
                    "validation.stage",
                    f"unsupported validation stage: {stage}",
                    (stage,),
                    "use stage = input or stage = pre_librpa",
                ),
            ),
        )
    parsed = _parse_inputs(case_root, profile_id=selected_profile_id)
    if isinstance(parsed, ValidationReport):
        return parsed
    abacus, librpa = parsed
    contract = profile["contract"]
    production = contract["librpa"]["production"]
    normalized_task = task.strip().lower()
    normalized_response = response_method.strip().lower()
    required_v1_names = {
        "prefix_coul_full": production["prefix_coul_full"],
        "prefix_eigvecs_scf": production["prefix_eigvecs_scf"],
        "prefix_lri_coeff": production["prefix_lri_coeff"],
        "fn_stru": production["fn_stru"],
        "fn_bz_sampling": production["fn_bz_sampling"],
        "fn_basis_wfc": production["fn_basis_wfc"],
        "fn_basis_aux": production["fn_basis_aux"],
        "fn_eigocc_scf": production["fn_eigocc_scf"],
    }
    if normalized_task == "gw":
        required_v1_names.update(
            {
                "prefix_coul_cut": production["prefix_coul_cut"],
                "fn_vxc_scf": production["fn_vxc_scf"],
            }
        )

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
        _fullcoul_exx_gate(librpa),
        _frequency_grid_gate(librpa, contract["librpa"]["frequency_grids"]),
        _periodic_3d_gw_continuation_gate(
            librpa,
            profile,
            task=normalized_task,
            system_type=system_type,
        ),
        _route_policy_gate(
            normalized_task,
            system_type,
            use_symmetry,
            profile,
            normalized_response,
        ),
        _headwing_policy_gate(
            librpa,
            normalized_task,
            system_type,
            headwing,
            strict_2d_sos_rpa=is_strict_2d_sos_rpa_profile(selected_profile_id),
        ),
        _strict_2d_sos_rpa_input_gate(librpa, profile),
        _value_gate(
            librpa,
            "librpa.reader_v1",
            {"version_coul_reader": "1", "version_lri_reader": "1"},
            label="LibRPA reader-v1 selectors",
        ),
        _value_gate(
            librpa,
            "librpa.v1_names",
            required_v1_names,
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
                _skip("bz_sampling.format", "bz_sampling_out is not required at the input stage"),
                _skip("band_out.format", "band_out is not required at the input stage"),
                _skip("dataset.kpoints", "producer k-point metadata is not required at the input stage"),
                _skip(
                    "dataset.screening_grid",
                    "producer screening-grid metadata is not required at the input stage",
                ),
                _skip("dataset.eigenvectors", "KS eigenvectors are not required at the input stage"),
                _skip("gw.vxc", "vxc_out is not required at the input stage"),
                _skip("stru_out.format", "stru_out is not required at the input stage"),
                _skip("symmetry.stru_out", "stru_out is not required at the input stage"),
                _skip("basis.v1", "reader-v1 basis metadata is not required at the input stage"),
                _skip("dataset.v1_payloads", "reader-v1 matrix payloads are not required at the input stage"),
                _skip("dataset.coulomb_q", "Coulomb q-point files are not required at the input stage"),
                _skip("pyatb.headwing", "PyATB outputs are not required at the input stage"),
                _skip("pyatb.alignment", "PyATB outputs are not required at the input stage"),
            )
        )
        return ValidationReport(selected_profile_id, tuple(gates))

    dataset = _dataset_root(case_root, librpa)
    base_names = (
        production["fn_stru"],
        production["fn_bz_sampling"],
        production["fn_basis_wfc"],
        production["fn_basis_aux"],
        production["fn_eigocc_scf"],
    )
    gates.append(_artifact_existence_gate(dataset, base_names, "dataset.artifacts", "base artifacts"))
    if is_strict_2d_sos_rpa_profile(selected_profile_id):
        gates.append(
            _strict2d_coulomb_head_gate(
                dataset,
                profile["contract"]["strict_2d_sos_rpa"]["coulomb_head_artifact"],
            )
        )
    required_prefixes = (
        (production["prefix_coul_full"], production["prefix_coul_cut"], production["prefix_lri_coeff"])
        if normalized_task == "gw"
        else (production["prefix_coul_full"], production["prefix_lri_coeff"])
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

    bz_sampling: dict[str, object] | None = None
    try:
        bz_sampling = parse_bz_sampling(dataset / str(production["fn_bz_sampling"]))
        gates.append(
            GateResult(
                gate_id="bz_sampling.format",
                status="PASS",
                message="bz_sampling_out matches the LibRPA 0.7.0 sampling contract",
                evidence=(str(dataset / str(production["fn_bz_sampling"])),),
                measurements={
                    "nk_full": int(bz_sampling["nk_full"]),
                    "nk_scf": int(bz_sampling["nk_scf"]),
                    "nk_ibz": int(bz_sampling["nk_ibz"]),
                },
            )
        )
    except ParseError as exc:
        gates.append(
            _fail(
                "bz_sampling.format",
                str(exc),
                (str(dataset / str(production["fn_bz_sampling"])),),
                "regenerate bz_sampling_out with the pinned ABACUS producer",
            )
        )

    if bz_sampling is not None:
        gates.append(_screening_grid_alignment_gate(case_root, bz_sampling))
    else:
        gates.append(
            _skip(
                "dataset.screening_grid",
                "KPT_scf cannot be compared until bz_sampling_out is valid",
            )
        )

    band_out: dict[str, int | float] | None = None
    try:
        band_out = parse_band_out(dataset / str(production["fn_eigocc_scf"]))
        gates.append(
            GateResult(
                gate_id="band_out.format",
                status="PASS",
                message="band_out has complete finite mean-field data",
                evidence=(str(dataset / str(production["fn_eigocc_scf"])),),
                measurements={
                    "nkpoints": int(band_out["nkpoints"]),
                    "nspin": int(band_out["nspin"]),
                    "nstates": int(band_out["nstates"]),
                    "nbasis": int(band_out["nbasis"]),
                },
            )
        )
    except ParseError as exc:
        gates.append(
            _fail(
                "band_out.format",
                str(exc),
                (str(dataset / str(production["fn_eigocc_scf"])),),
                "regenerate band_out with the pinned ABACUS producer",
            )
        )

    if bz_sampling is not None and band_out is not None:
        if int(bz_sampling["nk_scf"]) != int(band_out["nkpoints"]):
            gates.append(
                _fail(
                    "dataset.kpoints",
                    "bz_sampling_out SCF k-point count does not match band_out",
                    (
                        f"bz_sampling_out={bz_sampling['nk_scf']}",
                        f"band_out={band_out['nkpoints']}",
                    ),
                    "regenerate bz_sampling_out and band_out from the same ABACUS producer run",
                )
            )
        else:
            gates.append(
                _pass(
                    "dataset.kpoints",
                    "bz_sampling_out and band_out use the same SCF k-point count",
                )
            )
    else:
        gates.append(
            _skip(
                "dataset.kpoints",
                "SCF k-point counts cannot be compared until both metadata files are valid",
            )
        )

    eigenvector_paths = _find_by_prefix(dataset, str(production["prefix_eigvecs_scf"]))
    eigenvector_infos = tuple(inspect_eigenvector_v1(path) for path in eigenvector_paths)
    eigenvector_failures = [
        f"{info.path}: {gate.message}"
        for info in eigenvector_infos
        for gate in info.gates
        if gate.status == "FAIL"
    ]
    eigenvector_indices = tuple(
        index
        for info in eigenvector_infos
        if info.accepted
        for index in info.metadata["k_indices"]
    )
    if band_out is not None:
        for info in eigenvector_infos:
            if info.accepted and (
                int(info.metadata["nspin"]) != int(band_out["nspin"])
                or int(info.metadata["nstates"]) != int(band_out["nstates"])
                or int(info.metadata["nbasis"]) != int(band_out["nbasis"])
            ):
                eigenvector_failures.append(
                    f"{info.path}: eigenvector dimensions do not match band_out"
                )
        expected_indices = set(range(1, int(band_out["nkpoints"]) + 1))
        actual_indices = set(eigenvector_indices)
        if actual_indices != expected_indices:
            eigenvector_failures.append(
                f"k-point coverage {sorted(actual_indices)} != expected {sorted(expected_indices)}"
            )
    duplicates = sorted(
        index for index in set(eigenvector_indices) if eigenvector_indices.count(index) > 1
    )
    if duplicates:
        eigenvector_failures.append(f"duplicate k-point blocks across files: {duplicates}")
    if not eigenvector_paths:
        eigenvector_failures.append(
            f"no files start with {production['prefix_eigvecs_scf']!r} in {dataset}"
        )
    if eigenvector_failures:
        gates.append(
            _fail(
                "dataset.eigenvectors",
                "main KS eigenvector reader-v1 files are incomplete or inconsistent",
                tuple(eigenvector_failures),
                "regenerate all KS_eigenvector reader-v1 files with the same ABACUS producer run",
            )
        )
    elif band_out is None:
        gates.append(
            _skip(
                "dataset.eigenvectors",
                "main KS eigenvector dimensions cannot be checked until band_out is valid",
            )
        )
    else:
        gates.append(
            _pass(
                "dataset.eigenvectors",
                "main KS eigenvector reader-v1 files match band_out and cover every SCF k-point",
                *(str(path) for path in eigenvector_paths),
            )
        )

    if normalized_task == "gw":
        try:
            vxc = parse_vxc_out(dataset / str(production["fn_vxc_scf"]))
            if band_out is None:
                gates.append(
                    _skip("gw.vxc", "vxc_out dimensions cannot be checked until band_out is valid")
                )
            elif any(
                int(vxc[key]) != int(band_out[band_key])
                for key, band_key in (
                    ("nkpoints", "nkpoints"),
                    ("nspin", "nspin"),
                    ("nstates", "nstates"),
                )
            ):
                gates.append(
                    _fail(
                        "gw.vxc",
                        "vxc_out dimensions do not match band_out",
                        (
                            f"vxc_out={(vxc['nkpoints'], vxc['nspin'], vxc['nstates'])}",
                            f"band_out={(band_out['nkpoints'], band_out['nspin'], band_out['nstates'])}",
                        ),
                        "regenerate vxc_out and band_out from the same ABACUS producer run",
                    )
                )
            else:
                gates.append(
                    _pass(
                        "gw.vxc",
                        "vxc_out is complete and matches the mean-field dimensions",
                        str(dataset / str(production["fn_vxc_scf"])),
                    )
                )
        except ParseError as exc:
            gates.append(
                _fail(
                    "gw.vxc",
                    str(exc),
                    (str(dataset / str(production["fn_vxc_scf"])),),
                    "regenerate vxc_out with the same ABACUS producer run",
                )
            )
    else:
        gates.append(_skip("gw.vxc", "vxc_out is not consumed by the RPA task"))

    stru_info = inspect_stru_out(dataset / production["fn_stru"])
    gates.extend(stru_info.gates)
    expected_stru_symmetry = use_symmetry and not soc
    expected_convention = contract["abacus"]["symmetry"]["stru_out_convention"]
    actual_stru_symmetry = bool(stru_info.metadata.get("has_symmetry")) if stru_info.accepted else None
    actual_convention = stru_info.metadata.get("convention") if stru_info.accepted else None
    if stru_info.accepted and (
        actual_stru_symmetry != expected_stru_symmetry
        or (expected_stru_symmetry and actual_convention != expected_convention)
    ):
        gates.append(
            _fail(
                "symmetry.stru_out",
                "stru_out symmetry metadata does not match the selected route",
                (
                    str(stru_info.path),
                    f"has_symmetry={actual_stru_symmetry!r}",
                    f"convention={actual_convention!r}",
                ),
                (
                    "regenerate stru_out with the matching ABACUS SCF symmetry setting"
                    + (f" and {expected_convention} convention" if expected_stru_symmetry else "")
                ),
            )
        )
    elif stru_info.accepted:
        gates.append(_pass("symmetry.stru_out", "stru_out symmetry metadata matches the selected route"))
    else:
        gates.append(
            _skip("symmetry.stru_out", "stru_out symmetry cannot be checked until its format is valid")
        )

    if stru_info.accepted:
        gates.extend(
            _reader_v1_payload_gates(
                dataset,
                production,
                shrink=shrink,
                atom_types=tuple(stru_info.metadata["atom_types"]),
                expected_q_points=(
                    frozenset(range(1, int(bz_sampling["nk_ibz"]) + 1))
                    if bz_sampling is not None
                    else None
                ),
                require_cut_coulomb=normalized_task == "gw",
            )
        )
    else:
        gates.extend(
            (
                _skip("basis.v1", "split-basis metadata cannot be checked until stru_out is valid"),
                _skip("dataset.v1_payloads", "reader-v1 payloads cannot be checked until stru_out is valid"),
                _skip("dataset.coulomb_q", "Coulomb q sets cannot be checked until stru_out is valid"),
            )
        )

    headwing = _bool_value(librpa, "replace_w_head")
    if headwing:
        headwing_info = inspect_headwing_directory(
            dataset / contract["pyatb_adapter"]["directory"]
        )
        gates.extend(headwing_info.gates)
        if headwing_info.accepted and bz_sampling is not None and band_out is not None:
            expected_nbasis = int(band_out["nbasis"])
            mismatches = []
            if int(headwing_info.metadata["nkpoints"]) != int(bz_sampling["nk_full"]):
                mismatches.append(
                    f"PyATB nkpoints={headwing_info.metadata['nkpoints']} "
                    f"!= full grid {bz_sampling['nk_full']}"
                )
            if int(headwing_info.metadata["nbasis"]) != expected_nbasis:
                mismatches.append(
                    f"PyATB nbasis={headwing_info.metadata['nbasis']} "
                    f"!= mean-field AO basis {expected_nbasis}"
                )
            if int(headwing_info.metadata["nstates"]) != int(band_out["nstates"]):
                mismatches.append(
                    f"PyATB nstates={headwing_info.metadata['nstates']} "
                    f"!= band_out {band_out['nstates']}"
                )
            if int(headwing_info.metadata["nspin"]) != int(band_out["nspin"]):
                mismatches.append(
                    f"PyATB nspin={headwing_info.metadata['nspin']} "
                    f"!= band_out {band_out['nspin']}"
                )
            try:
                _map_kpoints_by_coordinates(
                    bz_sampling["fractional_kpoints"],
                    headwing_info.metadata["kpoints"],
                )
            except ValueError as exc:
                mismatches.append(str(exc))
            if mismatches:
                gates.append(
                    _fail(
                        "pyatb.alignment",
                        "PyATB full-grid metadata does not match the ABACUS producer dataset",
                        tuple(mismatches),
                        "regenerate pyatb_librpa_df from the same ABACUS Hamiltonian and full regular k-grid",
                    )
                )
            else:
                gates.append(
                    _pass(
                        "pyatb.alignment",
                        "PyATB dimensions match the ABACUS mean field and full regular k-grid",
                    )
                )
        else:
            gates.append(
                _skip(
                    "pyatb.alignment",
                    "PyATB alignment cannot be checked until all producer metadata is valid",
                )
            )
    elif headwing is False:
        gates.append(_skip("pyatb.headwing", "replace_w_head is disabled"))
        gates.append(_skip("pyatb.alignment", "replace_w_head is disabled"))
    else:
        gates.append(
            _fail(
                "pyatb.headwing",
                "replace_w_head is missing or invalid",
                (str(librpa.path),),
                "set replace_w_head = t for periodic head/wing or f for the molecular short route",
            )
        )
        gates.append(
            _skip("pyatb.alignment", "replace_w_head is missing or invalid")
        )
    return ValidationReport(selected_profile_id, tuple(gates))
