#!/usr/bin/env python3
"""Check a case's real inputs against the selected LibRPA-database element sets.

Run this before submitting any compute (including a LibRPA-only rerun on an
existing data set). It hashes the PP/NAO/ABFS payloads that are actually on
disk, compares them with the database set bound to the reference record, and
exits non-zero on any mismatch, missing payload or competing payload.

Example:

    .venv/bin/python scripts/verify_case_inputs.py \
      --case ~/.local/share/oh-my-librpa/upstream/bn-k222-sym-v1-shrink-head-g0w0 \
      --basis-root ~/Downloads/abacus-librpa-gw-database \
      --basis-family SG15 \
      --dimension 3d
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oml_mcp.basis_registry import (  # noqa: E402
    BasisRegistryError,
    load_registry,
    resolve_set,
)
from oml_mcp.input_identity import (  # noqa: E402
    compare_basis,
    expected_basis_hashes,
    expected_set_ids,
    observed_basis,
    observed_element_names,
)
from oml_mcp.orbital_info import OrbitalInfoError, parse_orbital_header  # noqa: E402
from oml_mcp.policy_gates import (  # noqa: E402
    FAIL,
    check_basis_identity,
    check_kpoint_standard,
    check_shrink_standard,
    check_abfs_contract,
)
from oml_mcp.stru import StruError, atom_counts, species  # noqa: E402


def _read_kgrid(path: Path) -> tuple[int, int, int] | None:
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        fields = line.split()
        if len(fields) < 3:
            continue
        try:
            grid = tuple(int(field) for field in fields[:3])
        except ValueError:
            continue
        if all(component > 0 for component in grid):
            return grid  # type: ignore[return-value]
    return None


def _read_input_scalar(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("#", 1)[0].split()
        if fields[:1] == [key] and len(fields) >= 2:
            return fields[1]
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True, help="case or reused-data directory")
    parser.add_argument(
        "--basis-root",
        default=os.environ.get("OML_BASIS_LIBRARY_ROOT"),
        help="LibRPA-database root (default: $OML_BASIS_LIBRARY_ROOT)",
    )
    parser.add_argument(
        "--basis-family",
        default="SG15",
        help="element-set family the reference record binds (default: SG15)",
    )
    parser.add_argument("--dimension", default="3d", choices=("3d", "2d"))
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    case = Path(args.case).expanduser().resolve()
    if not case.is_dir():
        print(f"case directory does not exist: {case}", file=sys.stderr)
        return 2
    if not args.basis_root:
        print("pass --basis-root or set OML_BASIS_LIBRARY_ROOT", file=sys.stderr)
        return 2
    registry = load_registry(args.basis_root)

    stru = case / "STRU"
    elements = [element for element, _, _ in species(stru.read_text(encoding="utf-8"))] if stru.is_file() else []
    observed = observed_basis(case, elements or None)
    if not elements:
        elements = list(observed_element_names(observed))

    resolved: dict[str, object] = {}
    errors: dict[str, str] = {}
    for element in dict.fromkeys(elements):
        try:
            resolved[element] = resolve_set(
                registry, element, family=args.basis_family, require_abf=True
            )
        except BasisRegistryError as exc:
            errors[element] = str(exc)

    expected = expected_basis_hashes(resolved)  # type: ignore[arg-type]
    set_ids = expected_set_ids(resolved)  # type: ignore[arg-type]
    names = {
        f"{element}/{role}": asset.path.name
        for element, element_set in resolved.items()  # type: ignore[union-attr]
        for role, asset in element_set.files.items()
    }
    identity = check_basis_identity(
        expected_basis=expected,
        observed_basis=observed.hashes,
        observed_duplicates=observed.duplicates,
    )
    problems = compare_basis(expected, observed, expected_names=names)

    kgrid = _read_kgrid(case / "KPT_scf") or _read_kgrid(case / "bz_sampling_out")
    kpoint = check_kpoint_standard(scf_kgrid=kgrid, dimension=args.dimension)
    abfs_orbital = any(path.suffix.lower() == ".abfs" for path in case.rglob("*") if path.is_file())
    exx_pca = _read_input_scalar(case / "INPUT_scf", "exx_pca_threshold")
    shrink_flag = _read_input_scalar(case / "INPUT_scf", "use_shrink_abfs")
    abfs = check_abfs_contract(
        abfs_orbital=abfs_orbital,
        exx_pca_threshold=float(exx_pca) if exx_pca is not None else None,
        use_shrink_abfs=None if shrink_flag is None else shrink_flag.lower() in {"t", "true", "1"},
    )
    shrink_raw = _read_input_scalar(case / "INPUT_scf", "shrink_abfs_pca_thr")
    shrink = check_shrink_standard(
        shrink_abfs_pca_thr=float(shrink_raw) if shrink_raw is not None else None
    )

    nbands_raw = _read_input_scalar(case / "INPUT_scf", "nbands")
    soc = (_read_input_scalar(case / "INPUT_scf", "lspinorb") or "").lower() in {"1", "t", "true"}
    nbands = None
    if nbands_raw is not None and stru.is_file():
        try:
            counts = atom_counts(stru.read_text(encoding="utf-8"))
            nbasis = 0
            for element, count in counts.items():
                relative = observed.paths.get(f"{element}/nao")
                if relative is None:
                    raise KeyError(f"{element}/nao")
                nbasis += count * parse_orbital_header(case / relative).basis_dimension_for(soc=soc)
        except (StruError, OrbitalInfoError, KeyError, ValueError) as exc:
            nbands = {"declared": int(nbands_raw), "error": str(exc), "match": False}
        else:
            nbands = {
                "declared": int(nbands_raw),
                "nbasis": nbasis,
                "match": int(nbands_raw) == nbasis,
            }

    rows = []
    for key in sorted(set(expected) | set(observed.hashes)):
        rows.append(
            {
                "element_role": key,
                "expected_file": names.get(key),
                "expected_sha256": expected.get(key),
                "observed_file": observed.paths.get(key),
                "observed_sha256": observed.hashes.get(key),
                "match": key in expected
                and key in observed.hashes
                and expected[key] == observed.hashes[key],
            }
        )

    report = {
        "case": str(case),
        "basis_family": args.basis_family,
        "element_sets": set_ids,
        "elements": elements,
        "rows": rows,
        "problems": problems,
        "identity": identity.to_dict(),
        "kgrid": list(kgrid) if kgrid else None,
        "kpoint": kpoint.to_dict(),
        "abfs": abfs.to_dict(),
        "shrink": shrink.to_dict(),
        "nbands": nbands,
        "unattributed": list(observed.unattributed),
        "ok": identity.status != FAIL
        and not errors
        and (nbands is None or nbands.get("match", False)),
    }

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"case: {case}")
        print(f"family: {args.basis_family}  sets: {set_ids}")
        print(f"{'element/role':<14} {'expected':<42} {'observed':<42} match")
        for row in rows:
            print(
                f"{row['element_role']:<14} "
                f"{(row['expected_file'] or '-') + ' ' + (row['expected_sha256'] or '')[:12]:<42} "
                f"{(row['observed_file'] or '-') + ' ' + (row['observed_sha256'] or '')[:12]:<42} "
                f"{'yes' if row['match'] else 'NO'}"
            )
        for element, message in sorted(errors.items()):
            print(f"  {element}: {message}")
        for problem in problems:
            print(f"  mismatch: {problem}")
        print(f"identity: {identity.status} - {identity.message}")
        print(f"k grid: {kgrid} -> {kpoint.status} ({kpoint.message})")
        print(f"abfs: {abfs.status} ({abfs.message})")
        print(f"shrink: {shrink.status} ({shrink.message})")
        if nbands is not None:
            if "error" in nbands:
                print(f"nbands: declared {nbands['declared']}, cannot derive nbasis ({nbands['error']})")
            else:
                print(
                    f"nbands: declared {nbands['declared']} vs basis dimension {nbands['nbasis']} "
                    f"-> {'match' if nbands['match'] else 'MISMATCH'}"
                )
        if observed.unattributed:
            print(f"unattributed payloads: {', '.join(observed.unattributed)}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
