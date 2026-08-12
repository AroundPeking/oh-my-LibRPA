#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from oml_mcp.profiles import load_profile


@dataclass(frozen=True)
class SourceCheck:
    component: str
    relative_path: str
    needles: tuple[str, ...]


CHECKS = (
    SourceCheck(
        "abacus",
        "source/source_io/module_parameter/input_parameter.h",
        ("int out_librpa_reader_version = 0",),
    ),
    SourceCheck(
        "abacus",
        "source/source_io/module_parameter/read_input_item_output.cpp",
        ("Input_Item item(\"out_librpa_reader_version\")", "supports only 0 (legacy) or 1"),
    ),
    SourceCheck(
        "abacus",
        "source/source_lcao/module_ri/RPA_LRI.hpp",
        (
            '"v1_coulomb_full_iq_"',
            '"v1_Cs_data_"',
            '"v1_Cs_shrinked_data_"',
            '"v1_shrink_sinvS_"',
            'ofs << ucell.symm.nrotk << " row"',
        ),
    ),
    SourceCheck(
        "librpa",
        "driver/driver.cpp",
        ("version_coul_reader(-1)", "version_lri_reader(-1)"),
    ),
    SourceCheck(
        "librpa",
        "driver/inputfile.cpp",
        ("_parse_switch(opts, use_symmetry_exx)", "_parse_switch(opts, use_symmetry_gw)"),
    ),
    SourceCheck(
        "librpa",
        "docs/user_guide/runtime_parameters.yml",
        ("`g0w0_band` is accepted as a deprecated alias of `g0w0`",),
    ),
    SourceCheck(
        "librpa",
        "driver/read_data.cpp",
        ("READER_VELOCITY_MATRIX_V1_MARKER = -12345680", '"pyatb_librpa_df/"'),
    ),
    SourceCheck(
        "pyatb",
        "src/pyatb/tb/solver.py",
        ("def get_velocity_matrix",),
    ),
    SourceCheck(
        "pyatb",
        "src/cpp/interface_python/interface_python.cpp",
        ("void interface_python::get_velocity_matrix",),
    ),
)


def git_head(path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def audit(checkouts: dict[str, Path]) -> list[str]:
    profile = load_profile()
    failures: list[str] = []
    for component, path in checkouts.items():
        expected = profile["components"][component]["revision"]
        try:
            actual = git_head(path)
        except (OSError, subprocess.CalledProcessError) as exc:
            failures.append(f"{component}: cannot read git HEAD at {path}: {exc}")
            continue
        if actual != expected:
            failures.append(f"{component}: revision {actual} != {expected}")
        else:
            print(f"PASS {component} revision {actual}")

    for check in CHECKS:
        path = checkouts[check.component] / check.relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            failures.append(f"{check.component}: cannot read {check.relative_path}: {exc}")
            continue
        missing = [needle for needle in check.needles if needle not in content]
        if missing:
            failures.append(
                f"{check.component}:{check.relative_path}: missing contract evidence {missing}"
            )
        else:
            print(f"PASS {check.component}:{check.relative_path}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit pinned ABACUS/LibRPA/PyATB sources")
    parser.add_argument("--abacus", type=Path, required=True)
    parser.add_argument("--librpa", type=Path, required=True)
    parser.add_argument("--pyatb", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    failures = audit({"abacus": args.abacus, "librpa": args.librpa, "pyatb": args.pyatb})
    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    print("ACCEPTED pinned upstream contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
