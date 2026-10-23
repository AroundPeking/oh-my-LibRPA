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

from .control import ControlledExecutionService
from .evolution_runner import load_reference_texts
from .execution_profiles import load_execution_profile
from .fast_benchmark import FastCase, evaluate_case_against_reference
from .loop_runner import LoopError, TrialOutcome
from .profiles import load_profile
from .remote_adapter import ControlledExecutionBinding, ControlledRunAdapter


BAND_KEYS = {
    "KS_band_spin_1.dat": "ks",
    "EXX_band_spin_1.dat": "exx",
    "GW_band_spin_1.dat": "gw",
}


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
    ) -> None:
        profile = load_execution_profile(execution_profile_id)
        if not getattr(profile, "enabled", True):
            raise LoopError(f"execution profile {execution_profile_id} is disabled")
        service = ControlledExecutionService(profile, profile_id=software_profile_id)
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

    def run(self, definition: Mapping[str, Any], *, trial: int) -> TrialOutcome:
        # A stale bundle from an earlier crashed attempt is derived data; set
        # it aside (never delete) so this trial starts clean.
        stale = Path(self.adapter.staging_root) / f"{self.case.case_id}-iter{trial}"
        if stale.is_dir():
            import time as _time

            stale.rename(stale.with_name(f"{stale.name}.crashed-{int(_time.time())}"))
        result = self.adapter.run_candidate(
            case=self.case,
            candidate=dict(definition),
            iteration=trial,
            changed_axis=None,
            apply_prescription=False,
        )
        status = str(result.get("status") or "UNKNOWN")
        if status != "COMPLETED":
            return TrialOutcome(
                status=status,
                note=str(result.get("diagnostics") or "")[:1000],
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
        note = ""
        if not artifacts:
            note = "the run completed but did not produce the three band tables"
        return TrialOutcome(
            status="COMPLETED",
            artifacts=artifacts,
            note=note,
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
