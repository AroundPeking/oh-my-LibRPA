"""Bind the analysis-driven loop to the controlled cluster adapter.

``ControlledLoopRunner`` maps one loop definition onto the existing
``ControlledRunAdapter``: stage the case bundle, materialize an immutable run,
submit every stage through ``ControlledExecutionService``, collect the
declared outputs, and expose the produced band tables to the loop. The
workflow helpers are staged from a reviewed directory and their digests are
verified against the pinned software profile before anything is submitted.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any, Mapping

from .basis_registry import BasisRegistryError, load_registry, resolve_set, verify_asset
from .control import ControlledExecutionService
from .evolution_runner import load_reference_texts
from .execution_profiles import load_execution_profile
from .fast_benchmark import FastCase, evaluate_case_against_reference
from .loop_runner import LoopError, TrialOutcome
from .preflight import preflight
from .profiles import load_profile
from .remote_adapter import (
    ControlledExecutionBinding,
    ControlledRunAdapter,
    locate_case_source,
)
from .stru import species


BAND_KEYS = {
    "KS_band_spin_1.dat": "ks",
    "EXX_band_spin_1.dat": "exx",
    "GW_band_spin_1.dat": "gw",
}

ROUTE_DIMENSIONS = {
    "periodic_3d_gw": "3d",
    "strict_2d_gw": "2d",
    "strict_2d_sos_rpa": "2d",
}


def read_case_scf_grid(source: str | Path) -> list[int] | None:
    """Read the positive three-integer Gamma grid from a case ``KPT_scf``."""
    path = Path(source) / "KPT_scf"
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        tokens = line.split()
        if len(tokens) < 3:
            continue
        try:
            grid = [int(token) for token in tokens[:3]]
        except ValueError:
            continue
        if all(component > 0 for component in grid):
            return grid
    return None


class ControlledLoopRunner:
    """Production runner: one definition becomes one controlled cluster run."""

    def __init__(
        self,
        *,
        case: FastCase,
        execution_profile_id: str,
        staging_root: str | Path,
        helpers_dir: str | Path,
        upstream_root: str | Path,
        artifact_root: str | Path,
        software_profile_id: str | None = None,
        poll_seconds: float = 30.0,
        scheduler_max_polls: int | None = None,
        basis_root: str | Path | None = None,
        basis_family: str | None = None,
        require_abf: bool = True,
        use_database_basis: bool = True,
        policy_mode: str = "production",
    ) -> None:
        profile = load_execution_profile(execution_profile_id)
        if not getattr(profile, "enabled", True):
            raise LoopError(f"execution profile {execution_profile_id} is disabled")
        service = ControlledExecutionService(profile, profile_id=software_profile_id)
        self.basis_family = basis_family
        self.require_abf = require_abf
        self.use_database_basis = use_database_basis
        self.policy_mode = policy_mode
        self.registry = None
        if use_database_basis:
            if not basis_root:
                raise LoopError(
                    "the LibRPA-database basis is the default; pass a basis library root "
                    "(or set OML_BASIS_LIBRARY_ROOT), or opt out with use_database_basis=False"
                )
            self.registry = load_registry(basis_root)
        approved_helpers = (
            load_profile(profile_id=software_profile_id)["contract"]["workflow_helpers"]
            if software_profile_id is not None
            else load_profile()["contract"]["workflow_helpers"]
        )
        self.binding = ControlledExecutionBinding(
            service=service,
            plan_options={
                "task": case.task,
                "system_type": case.system_type,
                "soc": case.soc,
                "use_symmetry": case.use_symmetry,
                "headwing": case.headwing,
                "profile_id": software_profile_id,
            },
            monitor_librpa=profile.transport == "local",
            poll_seconds=poll_seconds,
            scheduler_max_polls=scheduler_max_polls,
        )

        def materialize_with_helpers(bundle: Path, definition: dict[str, Any]) -> dict[str, Any]:
            bundle = Path(bundle)
            for name, digest in approved_helpers.items():
                source = Path(helpers_dir) / name
                if not source.is_file():
                    raise LoopError(
                        f"approved helper {name} is not in the helpers directory {helpers_dir}"
                    )
                destination = bundle / name
                shutil.copy2(source, destination)
                observed = hashlib.sha256(destination.read_bytes()).hexdigest()
                if observed != digest:
                    destination.unlink()
                    raise LoopError(
                        f"helper {name} does not match the approved digest "
                        f"({observed[:16]}... != {digest[:16]}...)"
                    )
            return self.binding.materialize(bundle, definition)

        self.case = case
        self.adapter = ControlledRunAdapter(
            case=case,
            upstream_root=upstream_root,
            staging_root=Path(staging_root),
            materialize=materialize_with_helpers,
            run_stages=self.binding.run_stages,
            collect_outputs=self.binding.collect_outputs,
        )
        self.artifact_root = Path(artifact_root)
        self.upstream_root = upstream_root

    def _resolve_submission(self, definition: Mapping[str, Any]) -> tuple[
        dict[str, Any], dict[str, dict[str, str]] | None, list[str], dict[str, Any]
    ]:
        exact = dict(definition)
        basis_override: dict[str, dict[str, str]] | None = None
        notes: list[str] = []
        missing: list[str] = []
        has_abf = False
        source = locate_case_source(self.case, self.upstream_root)
        if self.use_database_basis:
            stru_path = source.directory / "STRU"
            if not stru_path.is_file():
                raise LoopError("the database basis override needs a STRU in the case source")
            elements = [element for element, _, _ in species(stru_path.read_text(encoding="utf-8"))]
            override: dict[str, dict[str, str]] = {}
            for element in dict.fromkeys(elements):
                try:
                    element_set = resolve_set(
                        self.registry,
                        element,
                        family=self.basis_family,
                        require_abf=self.require_abf,
                    )
                except BasisRegistryError:
                    missing.append(element)
                    continue
                roles: dict[str, str] = {}
                for role in ("pp", "nao", "abf"):
                    asset = element_set.asset(role)
                    if asset is None:
                        continue
                    verify_asset(asset)
                    roles[role] = str(asset.path)
                override[element] = roles
                has_abf = has_abf or "abf" in roles
            basis_override = override
            if has_abf:
                # A prebuilt database ABFS is used through ABFS_ORBITAL; the
                # production contract then screens the PCA basis out and keeps
                # shrink enabled.
                exact["exx_pca_threshold"] = 10.0
                exact["use_shrink_abfs"] = True
                notes.append(
                    "database PP/NAO/ABFS staged; ABFS production contract: "
                    "exx_pca_threshold=10, use_shrink_abfs=t"
                )
        scf_grid = exact.get("scf_kgrid") or read_case_scf_grid(source.directory)
        policy_inputs = {
            "database_basis": self.use_database_basis,
            "missing_elements": tuple(missing),
            "scf_kgrid": scf_grid,
            "dimension": ROUTE_DIMENSIONS.get(self.case.route),
            "abfs_orbital": has_abf if self.use_database_basis else None,
            "exx_pca_threshold": exact.get("exx_pca_threshold"),
            "use_shrink_abfs": exact.get("use_shrink_abfs"),
        }
        return exact, basis_override, notes, policy_inputs

    def audit(
        self, definition: Mapping[str, Any], *, mode: str | None = None
    ) -> dict[str, Any]:
        """Run the preflight audit without submitting anything."""
        exact, basis_override, notes, policy_inputs = self._resolve_submission(definition)
        result = preflight(mode=mode or self.policy_mode, **policy_inputs)
        return {
            "ok": result.ok,
            "preflight": result.to_dict(),
            "effective_definition": exact,
            "basis_override": basis_override,
            "notes": list(notes),
        }

    def run(self, definition: Mapping[str, Any], *, trial: int) -> TrialOutcome:
        # A stale bundle from an earlier crashed attempt is derived data; set
        # it aside (never delete) so this trial starts clean.
        stale = Path(self.adapter.staging_root) / f"{self.case.case_id}-iter{trial}"
        if stale.is_dir():
            import time as _time

            stale.rename(stale.with_name(f"{stale.name}.crashed-{int(_time.time())}"))
        exact, basis_override, notes, policy_inputs = self._resolve_submission(definition)
        audit = preflight(mode=self.policy_mode, **policy_inputs)
        if not audit.ok:
            raise LoopError("policy preflight failed: " + "; ".join(audit.reasons))
        result = self.adapter.run_candidate(
            case=self.case,
            candidate=exact,
            iteration=trial,
            changed_axis=None,
            apply_prescription=False,
            basis_override=basis_override,
        )
        status = str(result.get("status") or "UNKNOWN")
        if status != "COMPLETED":
            return TrialOutcome(
                status=status,
                note="; ".join(notes + [str(result.get("diagnostics") or "")[:1000]]),
            )
        observed = dict(result.get("observed") or {})
        outdir = self.artifact_root / f"trial-{trial}"
        outdir.mkdir(parents=True, exist_ok=True)
        artifacts: dict[str, str] = {}
        for name, text in observed.items():
            path = outdir / name
            path.write_text(text, encoding="utf-8")
            key = BAND_KEYS.get(name)
            if key:
                artifacts[key] = str(path)
        if not artifacts:
            notes.append("the run completed but did not produce the three band tables")
        return TrialOutcome(
            status="COMPLETED",
            artifacts=artifacts,
            note="; ".join(notes),
        )

    def reference_gap_ev(self) -> float | None:
        """Return the frozen reference's GW indirect gap, when one is archived."""
        reference = load_reference_texts(self.case.case_id, self.upstream_root)
        text = reference.get("GW_band_spin_1.dat")
        if not text:
            return None
        import os
        import tempfile

        from .band_analysis import gaps, load_layer

        handle = tempfile.NamedTemporaryFile(
            "w", suffix="_spin_1.dat", delete=False, encoding="utf-8"
        )
        try:
            handle.write(text)
            handle.close()
            return gaps(load_layer(handle.name, quantity="gw"))["indirect_gap_ev"]
        finally:
            if not handle.closed:
                handle.close()
            os.unlink(handle.name)

    def evaluate_reference(self, trial: int) -> dict[str, Any]:
        """Compare one trial's outputs with the frozen fast-case reference."""
        outdir = self.artifact_root / f"trial-{trial}"
        observed: dict[str, str] = {}
        for name in self.case.output_files:
            path = outdir / name
            if path.is_file():
                observed[name] = path.read_text(encoding="utf-8", errors="replace")
        reference = load_reference_texts(self.case.case_id, self.upstream_root)
        if not reference:
            return {"status": "NOT_EVALUATED", "reason": "no frozen reference was found"}
        return evaluate_case_against_reference(self.case, reference, observed)
