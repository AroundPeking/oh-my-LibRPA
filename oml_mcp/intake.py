from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .models import GateResult, IntakeReport


ABACUS_INPUT_NAMES = frozenset({"INPUT", "INPUT_scf", "INPUT_nscf", "KPT", "KPT_scf", "KPT_nscf", "STRU"})
FHI_AIMS_INPUT_NAMES = frozenset({"control.in", "geometry.in"})
SKIP_PARTS = frozenset({".git", "__pycache__", ".venv", "venv"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_file(path: Path) -> str:
    name = path.name
    if name.startswith("INPUT"):
        return "abacus_input"
    if name.startswith("KPT"):
        return "abacus_kpoints"
    if name == "STRU":
        return "abacus_structure"
    if name == "librpa.in":
        return "librpa_input"
    if name in {"stru_out", "bz_sampling_out", "basis_wfc_out", "basis_aux_out", "basis_aux_shrink_out", "band_out"}:
        return "producer_metadata"
    if name.startswith(("v1_coulomb_full_iq_", "v1_coulomb_cut_iq_")):
        return "reader_v1_coulomb"
    if name.startswith(("v1_Cs_data_", "v1_Cs_shrinked_data_", "v1_shrink_sinvS_")):
        return "reader_v1_lri"
    if name.startswith("KS_eigenvector_"):
        return "reader_v1_eigenvector"
    if name.startswith("velocity_matrix"):
        return "reader_v1_velocity"
    if name in {"k_path_info", "band_kpath_info"}:
        return "kpoint_metadata"
    if name in FHI_AIMS_INPUT_NAMES:
        return "fhi_aims_input"
    return "other"


def _files_under(root: Path) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        files.append(path)
    return tuple(sorted(files, key=lambda item: item.relative_to(root).as_posix()))


def ingest_case(path: str | Path) -> IntakeReport:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return IntakeReport(
            source_path=root,
            stack="unknown",
            files=(),
            markers=(),
            gates=(
                GateResult(
                    gate_id="intake.source",
                    status="FAIL",
                    message="case source does not exist",
                    evidence=(str(root),),
                    repair="provide an existing case directory or input file",
                ),
            ),
        )

    root_for_relative = root if root.is_dir() else root.parent
    files: list[dict[str, Any]] = []
    names: set[str] = set()
    for file_path in _files_under(root):
        relative = file_path.relative_to(root_for_relative).as_posix()
        names.add(file_path.name)
        stat = file_path.stat()
        files.append(
            {
                "path": relative,
                "kind": classify_file(file_path),
                "size": stat.st_size,
                "sha256": _sha256(file_path),
            }
        )

    has_abacus = bool(names & ABACUS_INPUT_NAMES) or any(name.startswith("INPUT") for name in names)
    has_aims = FHI_AIMS_INPUT_NAMES.issubset(names)
    markers: list[str] = []
    if has_abacus:
        markers.append("abacus_input")
    if has_aims:
        markers.append("fhi_aims_input")

    gates: list[GateResult] = []
    if has_abacus and has_aims:
        stack = "mixed"
        gates.append(
            GateResult(
                gate_id="intake.stack_ownership",
                status="FAIL",
                message="case contains strong ABACUS and FHI-aims ownership markers",
                evidence=(str(root),),
                repair="split the bundle or explicitly choose the upstream stack before planning",
            )
        )
    elif has_abacus:
        stack = "abacus_librpa"
    elif has_aims:
        stack = "fhi_aims_librpa"
    else:
        stack = "unknown"
        gates.append(
            GateResult(
                gate_id="intake.stack_ownership",
                status="WARN",
                message="no strong ABACUS or FHI-aims ownership markers were found",
                evidence=(str(root),),
                repair="provide INPUT/STRU or control.in/geometry.in ownership files",
            )
        )

    if not gates:
        gates.append(
            GateResult(
                gate_id="intake.stack_ownership",
                status="PASS",
                message=f"case classified as {stack}",
                evidence=(str(root),),
                measurements={"files": len(files)},
            )
        )
    return IntakeReport(root, stack, tuple(files), tuple(markers), tuple(gates))
