from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from .artifacts import inspect_headwing_directory
from .models import GateResult
from .stage_templates import CONTROLLED_PERIODIC_STAGES


NONFINITE_PATTERN = re.compile(r"(?<![A-Za-z])(?:nan|[+-]?inf(?:inity)?)(?![A-Za-z])", re.I)


def _pass(gate_id: str, message: str, *evidence: str) -> GateResult:
    return GateResult(gate_id, "PASS", message, tuple(evidence))


def _fail(gate_id: str, message: str, evidence: Iterable[str], repair: str) -> GateResult:
    return GateResult(gate_id, "FAIL", message, tuple(evidence), repair)


def _safe_nonempty(root: Path, path: Path) -> bool:
    try:
        resolved = path.resolve(strict=True)
        return (
            not path.is_symlink()
            and resolved.is_relative_to(root)
            and resolved.is_file()
            and resolved.stat().st_size > 0
        )
    except OSError:
        return False


def _required_files(
    root: Path,
    gate_id: str,
    paths: Iterable[Path],
    *,
    label: str,
    repair: str,
) -> GateResult:
    paths = tuple(paths)
    failures = tuple(str(path) for path in paths if not _safe_nonempty(root, path))
    if failures:
        return _fail(gate_id, f"{label} are missing, empty, linked, or escaped", failures, repair)
    return _pass(gate_id, f"{label} are present as non-empty regular files", *(str(path) for path in paths))


def _required_glob(
    root: Path,
    gate_id: str,
    patterns: Iterable[str],
    *,
    label: str,
    repair: str,
) -> tuple[GateResult, tuple[Path, ...]]:
    paths: list[Path] = []
    missing: list[str] = []
    for pattern in patterns:
        matches = tuple(sorted(root.glob(pattern)))
        safe = tuple(path for path in matches if _safe_nonempty(root, path))
        if not safe:
            missing.append(pattern)
        paths.extend(safe)
    if missing:
        return (
            _fail(gate_id, f"{label} are incomplete", tuple(missing), repair),
            tuple(paths),
        )
    return (
        _pass(gate_id, f"{label} are present", *(str(path) for path in paths)),
        tuple(paths),
    )


def _completion_log(
    root: Path,
    stage: str,
    relative: str,
    *,
    required_markers: Iterable[tuple[str, re.Pattern[str]]] = (),
) -> GateResult:
    path = root / relative
    repair = f"rerun the {stage} stage and inspect its producer log"
    if not _safe_nonempty(root, path):
        return _fail(
            f"stage.{stage}.completion",
            f"{stage} completion log is missing, empty, linked, or escaped",
            (str(path),),
            repair,
        )
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _fail(
            f"stage.{stage}.completion",
            f"cannot read {stage} completion log: {exc}",
            (str(path),),
            repair,
        )
    markers = (
        ("Finish Time", re.compile(r"(?m)^\s*Finish\s+Time(?:\s*:|\s*$)")),
        ("Total Time", re.compile(r"(?m)^\s*Total\s+Time(?:\s*:|\s*$)")),
        *tuple(required_markers),
    )
    missing = tuple(label for label, pattern in markers if pattern.search(text) is None)
    if missing:
        return _fail(
            f"stage.{stage}.completion",
            f"{stage} completion markers are incomplete",
            (str(path), *missing),
            repair,
        )
    return _pass(
        f"stage.{stage}.completion",
        f"{stage} reached every required ABACUS completion marker",
        str(path),
    )


def _finite_text_files(
    root: Path,
    stage: str,
    paths: Iterable[Path],
    *,
    gate_id: str,
) -> GateResult:
    failures: list[str] = []
    for path in paths:
        if not _safe_nonempty(root, path):
            failures.append(f"{path}: missing, empty, linked, or escaped")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            failures.append(f"{path}: unreadable text ({exc})")
            continue
        if NONFINITE_PATTERN.search(text):
            failures.append(f"{path}: contains NaN or Inf")
    if failures:
        return _fail(
            gate_id,
            f"{stage} text outputs are not complete finite data",
            failures,
            f"inspect the {stage} producer inputs and regenerate the affected outputs",
        )
    return _pass(gate_id, f"{stage} text outputs contain no NaN or Inf", *(str(path) for path in paths))


def _command_gate(
    root: Path, stage: str, expected_attempt_id: str | None = None
) -> GateResult:
    path = root / ".oml" / "stage-results" / f"{stage}.status"
    if not _safe_nonempty(root, path):
        return _fail(
            f"stage.{stage}.command",
            "generated stage command receipt is missing or unsafe",
            (str(path),),
            "inspect the scheduler output and rerun only through the controlled stage script",
        )
    status = path.read_text(encoding="utf-8", errors="replace").strip()
    expected = (
        "COMMAND_COMPLETED"
        if expected_attempt_id is None
        else f"COMMAND_COMPLETED:{expected_attempt_id}"
    )
    if status != expected:
        return _fail(
            f"stage.{stage}.command",
            "generated stage command did not exit successfully",
            (str(path), status),
            "inspect the stage workload log before a reviewed retry",
        )
    return _pass(f"stage.{stage}.command", "generated stage command exited successfully", str(path))


def _scf_gates(root: Path) -> list[GateResult]:
    return [
        _completion_log(
            root,
            "scf",
            "OUT.ABACUS/running_scf.log",
            required_markers=(("SCF converged", re.compile(r"(?m)^#SCF IS CONVERGED#$")),),
        ),
        _required_files(
            root,
            "stage.scf.artifacts",
            (
                root / "OUT.ABACUS" / "ABACUS-CHARGE-DENSITY.restart",
                root / "vxc_out",
                root / "stru_out",
            ),
            label="SCF restart, vxc_out, and stru_out artifacts",
            repair="rerun the pinned ABACUS SCF producer in a fresh immutable run",
        ),
    ]


def _pyatb_gates(root: Path) -> list[GateResult]:
    headwing = inspect_headwing_directory(root / "pyatb_librpa_df")
    gates = list(headwing.gates)
    main_gate, _ = _required_glob(
        root,
        "stage.pyatb.main_dataset",
        (
            "band_out",
            "basis_wfc_out",
            "basis_aux_out",
            "KS_eigenvector_*",
            "v1_Cs_data_*",
            "v1_coulomb_full_iq_*",
            "v1_coulomb_cut_iq_*",
        ),
        label="main reader-v1 and full/cut Coulomb artifacts",
        repair="regenerate the main ABACUS reader-v1 dataset and rerun the PyATB adapter",
    )
    gates.append(main_gate)
    return gates


def _nscf_gates(root: Path) -> list[GateResult]:
    eig_paths = tuple(
        path
        for name in ("eig.txt", "eig_occ.txt")
        if _safe_nonempty(root, path := root / "OUT.ABACUS" / name)
    )
    if eig_paths:
        eig_gate = _pass("stage.nscf.eigenvalues", "NSCF eigenvalue output is present", *(str(path) for path in eig_paths))
    else:
        eig_gate = _fail(
            "stage.nscf.eigenvalues",
            "NSCF produced neither eig.txt nor eig_occ.txt",
            (str(root / "OUT.ABACUS"),),
            "rerun the pinned ABACUS NSCF band-path stage",
        )
    return [_completion_log(root, "nscf", "OUT.ABACUS/running_nscf.log"), eig_gate]


def _preprocess_gates(root: Path) -> list[GateResult]:
    required_gate, _ = _required_glob(
        root,
        "stage.preprocess.artifacts",
        ("band_kpath_info", "band_KS_eigenvalue_*", "band_KS_eigenvector_*", "band_vxc*"),
        label="band-path LibRPA preprocessing artifacts",
        repair="rerun preprocess_abacus_for_librpa_band.py from the accepted NSCF output",
    )
    finite_paths = (
        root / "band_kpath_info",
        *tuple(sorted(root.glob("band_KS_eigenvalue_*"))),
        *tuple(sorted(root.glob("band_vxc*"))),
    )
    return [
        required_gate,
        _finite_text_files(root, "preprocess", finite_paths, gate_id="stage.preprocess.finite"),
    ]


def _librpa_gates(root: Path) -> list[GateResult]:
    rank0 = tuple(sorted(root.glob("librpa_para_nprocs_*_myid_0.out")))
    if not rank0:
        rank0 = tuple(sorted(root.glob("LibRPA*.out")))
    safe_rank0 = tuple(path for path in rank0 if _safe_nonempty(root, path))
    if not safe_rank0:
        completion = _fail(
            "stage.librpa.completion",
            "LibRPA rank-0 output is missing, empty, linked, or escaped",
            (str(root),),
            "inspect the scheduler workload output and rerun LibRPA after repairing the cause",
        )
    else:
        log = safe_rank0[0]
        text = log.read_text(encoding="utf-8", errors="replace")
        if "Timer stop:  total." in text or "libRPA finished successfully" in text:
            completion = _pass("stage.librpa.completion", "LibRPA reached a recognized final marker", str(log))
        else:
            completion = _fail(
                "stage.librpa.completion",
                "LibRPA did not reach a recognized final marker",
                (str(log),),
                "inspect the rank-0 output and repair the first failure before retrying",
            )
    gw_paths = tuple(sorted(root.glob("GW_band_spin_*.dat")))
    gw_gate = _finite_text_files(root, "librpa", gw_paths, gate_id="stage.librpa.gw_data")
    if not gw_paths:
        gw_gate = _fail(
            "stage.librpa.gw_data",
            "periodic GW band output is missing",
            (str(root / "GW_band_spin_*.dat"),),
            "repair the LibRPA run until finite GW_band_spin_*.dat files are produced",
        )
    shape_failures: list[str] = []
    expected_kpoints: int | None = None
    kpath = root / "band_kpath_info"
    if not _safe_nonempty(root, kpath):
        shape_failures.append(f"{kpath}: missing, empty, linked, or escaped")
    else:
        try:
            header = kpath.read_text(encoding="utf-8").splitlines()[0].split()
            if len(header) != 4:
                raise ValueError("header must contain nbasis nstates nspin nkpoints")
            expected_kpoints = int(header[3])
            if expected_kpoints <= 0:
                raise ValueError("nkpoints must be positive")
        except (OSError, ValueError, IndexError) as exc:
            shape_failures.append(f"{kpath}: invalid header ({exc})")
    expected_columns: int | None = None
    for path in gw_paths:
        try:
            rows = [line.split() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeDecodeError) as exc:
            shape_failures.append(f"{path}: unreadable text ({exc})")
            continue
        widths = {len(row) for row in rows}
        if expected_kpoints is not None and len(rows) != expected_kpoints:
            shape_failures.append(
                f"{path}: rows={len(rows)} != band_kpath_info nkpoints={expected_kpoints}"
            )
        if len(widths) != 1 or not widths or next(iter(widths)) < 6:
            shape_failures.append(f"{path}: inconsistent or too few columns")
            continue
        width = next(iter(widths))
        if expected_columns is None:
            expected_columns = width
        elif width != expected_columns:
            shape_failures.append(f"{path}: columns={width} != expected {expected_columns}")
    if shape_failures:
        shape_gate = _fail(
            "stage.librpa.gw_shape",
            "GW band table shape is inconsistent with band_kpath_info",
            shape_failures,
            "repair band preprocessing or LibRPA output generation before using the GW bands",
        )
    else:
        shape_gate = _pass(
            "stage.librpa.gw_shape",
            "GW band rows match the band-path k-point count and column shape",
            str(kpath),
            *(str(path) for path in gw_paths),
        )
    return [completion, gw_gate, shape_gate]


def inspect_stage_outputs(
    run_path: str | Path,
    stage: str,
    *,
    expected_attempt_id: str | None = None,
) -> dict[str, object]:
    root = Path(run_path).expanduser().resolve()
    if stage not in CONTROLLED_PERIODIC_STAGES:
        raise ValueError(f"unsupported controlled stage: {stage}")
    gates = [_command_gate(root, stage, expected_attempt_id)]
    gates.extend(
        {
            "scf": _scf_gates,
            "pyatb": _pyatb_gates,
            "nscf": _nscf_gates,
            "preprocess": _preprocess_gates,
            "librpa": _librpa_gates,
        }[stage](root)
    )
    counts = {status: sum(gate.status == status for gate in gates) for status in ("PASS", "WARN", "FAIL", "SKIP")}
    return {
        "schema_version": 1,
        "stage": stage,
        "accepted": counts["FAIL"] == 0,
        "counts": counts,
        "gates": [gate.to_dict() for gate in gates],
    }
