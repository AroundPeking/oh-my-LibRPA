"""Enforcement gates for the policy registry.

Each policy id maps to one implementation here; the registry test asserts the
mapping is complete. A gate reports PASS, FAIL or NOT_EVALUATED; only FAIL
blocks a production run, and NOT_EVALUATED is never treated as a pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence


PASS = "PASS"
FAIL = "FAIL"
NOT_EVALUATED = "NOT_EVALUATED"
PRODUCTION = "production"


@dataclass(frozen=True)
class PolicyFinding:
    gate_id: str
    status: str
    message: str
    repair: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "message": self.message,
            "repair": self.repair,
        }


def _not_evaluated(gate_id: str, reason: str) -> PolicyFinding:
    return PolicyFinding(gate_id, NOT_EVALUATED, reason)


def check_basis_source(
    *,
    database_basis: bool | None,
    missing_elements: Sequence[str] = (),
    mode: str = PRODUCTION,
) -> PolicyFinding:
    gate = "policy.basis_source"
    if mode != PRODUCTION:
        return _not_evaluated(gate, "replay runs are outside the production policy scope")
    if missing_elements:
        return PolicyFinding(
            gate,
            FAIL,
            f"elements {list(missing_elements)} are missing from the database basis",
            "build a matched PP/NAO/ABFS set with the abacus-librpa-gw-basis-skill method",
        )
    if database_basis is None:
        return _not_evaluated(gate, "the basis source was not recorded")
    if not database_basis:
        return PolicyFinding(
            gate,
            FAIL,
            "case-bundled PP/NAO/ABFS were used",
            "resolve PP/NAO/ABFS from the LibRPA database (--basis-root / OML_BASIS_LIBRARY_ROOT)",
        )
    return PolicyFinding(gate, PASS, "PP/NAO/ABFS come from the LibRPA database")


def check_kpoint_standard(
    *,
    scf_kgrid: Sequence[int] | None,
    dimension: str | None,
    mode: str = PRODUCTION,
) -> PolicyFinding:
    gate = "policy.kpoint_standard"
    if mode != PRODUCTION:
        return _not_evaluated(gate, "replay runs are outside the production policy scope")
    if scf_kgrid is None or dimension is None:
        return _not_evaluated(gate, "the k grid or dimension was not recorded")
    try:
        grid = tuple(int(component) for component in scf_kgrid)
    except (TypeError, ValueError):
        return PolicyFinding(gate, FAIL, f"invalid k grid {scf_kgrid!r}", "use three positive integers")
    if len(grid) != 3 or any(component <= 0 for component in grid):
        return PolicyFinding(gate, FAIL, f"invalid k grid {scf_kgrid!r}", "use three positive integers")
    if dimension == "3d":
        ok = all(component >= 8 for component in grid)
        target = "8x8x8"
    elif dimension == "2d":
        ok = grid[0] >= 12 and grid[1] >= 12 and grid[2] == 1
        target = "12x12x1 (kz = 1)"
    else:
        return _not_evaluated(gate, f"unknown dimension {dimension!r}")
    if not ok:
        return PolicyFinding(
            gate,
            FAIL,
            f"production k grid {grid} is below the standard {target}",
            f"start from {target}; a larger grid is a convergence-ladder step",
        )
    return PolicyFinding(gate, PASS, f"k grid {grid} meets the {target} standard")


def check_abfs_contract(
    *,
    abfs_orbital: bool | None,
    exx_pca_threshold: float | None,
    use_shrink_abfs: bool | None,
    mode: str = PRODUCTION,
) -> PolicyFinding:
    gate = "policy.abfs_contract"
    if mode != PRODUCTION:
        return _not_evaluated(gate, "replay runs are outside the production policy scope")
    if abfs_orbital is None:
        return _not_evaluated(gate, "the ABFS source was not recorded")
    if not abfs_orbital:
        return PolicyFinding(gate, PASS, "no prebuilt ABFS; the PCA generation lane applies")
    if exx_pca_threshold is None or use_shrink_abfs is None:
        return _not_evaluated(gate, "ABFS_ORBITAL is staged but the production knobs were not recorded")
    try:
        threshold = float(exx_pca_threshold)
    except (TypeError, ValueError):
        return PolicyFinding(gate, FAIL, f"invalid exx_pca_threshold {exx_pca_threshold!r}", "set it to 10")
    if threshold < 10.0:
        return PolicyFinding(
            gate,
            FAIL,
            f"exx_pca_threshold={exx_pca_threshold} would stack a PCA basis on the prebuilt ABFS",
            "set exx_pca_threshold = 10 with ABFS_ORBITAL",
        )
    if not use_shrink_abfs:
        return PolicyFinding(
            gate,
            FAIL,
            "use_shrink_abfs is off while a prebuilt ABFS is staged",
            "set use_shrink_abfs = t",
        )
    return PolicyFinding(gate, PASS, "prebuilt ABFS uses exx_pca_threshold=10 and shrink")


GATE_IMPLEMENTATIONS: dict[str, Callable[..., PolicyFinding]] = {
    "policy.basis_source": check_basis_source,
    "policy.kpoint_standard": check_kpoint_standard,
    "policy.abfs_contract": check_abfs_contract,
}


def run_gates(
    *,
    mode: str = PRODUCTION,
    database_basis: bool | None = None,
    missing_elements: Sequence[str] = (),
    scf_kgrid: Sequence[int] | None = None,
    dimension: str | None = None,
    abfs_orbital: bool | None = None,
    exx_pca_threshold: float | None = None,
    use_shrink_abfs: bool | None = None,
) -> tuple[PolicyFinding, ...]:
    return (
        check_basis_source(database_basis=database_basis, missing_elements=missing_elements, mode=mode),
        check_kpoint_standard(scf_kgrid=scf_kgrid, dimension=dimension, mode=mode),
        check_abfs_contract(
            abfs_orbital=abfs_orbital,
            exx_pca_threshold=exx_pca_threshold,
            use_shrink_abfs=use_shrink_abfs,
            mode=mode,
        ),
    )
