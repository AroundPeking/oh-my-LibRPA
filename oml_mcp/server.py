from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .artifacts import (
    inspect_eigenvector_v1,
    inspect_headwing_directory,
    inspect_velocity_v1,
)
from .admission_manifest import load_admission_manifest
from .benchmark_suite import evaluate_registered_route_benchmark_suite
from .control import ControlledExecutionService
from .evals import evaluate_evidence, load_scorecard
from .errors import OMLError
from .evolution import EvolutionBudget, EvolutionUsage, propose_candidate
from .execution_profiles import load_execution_profile
from .intake import ingest_case as ingest_case_data
from .planner import plan_case as plan_case_data
from .profiles import load_profile
from .route_benchmark import (
    evaluate_registered_route_benchmark,
    load_route_benchmark,
)
from .sternheimer_diagnostics import (
    inspect_grid_coulomb_consistency as inspect_grid_coulomb_consistency_data,
    inspect_sternheimer_comparison as inspect_sternheimer_comparison_data,
)
from .validators import validate_case as validate_case_data


ArtifactKind = Literal["eigenvector", "velocity", "headwing"]
ControlledStage = Literal["scf", "pyatb", "nscf", "preprocess", "librpa"]
AdmissionRoute = Literal[
    "periodic_3d_gw",
    "strict_2d_gw",
    "molecular_delta_st_rpa",
    "solid_delta_st_rpa",
    "strict_2d_sos_rpa",
]


def _read_only_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def _write_annotations(*, idempotent: bool) -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=idempotent,
        openWorldHint=True,
    )


def _external_read_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )


def _controlled_service(
    execution_profile_id: str, *, initialize_state: bool = True
) -> ControlledExecutionService:
    return ControlledExecutionService(
        load_execution_profile(execution_profile_id), initialize_state=initialize_state
    )


def _controlled_call(operation: Any) -> dict[str, Any]:
    try:
        return operation()
    except OMLError as exc:
        return exc.to_dict()


def build_server() -> MCPServer:
    server = MCPServer(
        name="oh-my-librpa",
        title="Oh-My-LibRPA",
        description="Deterministic ABACUS, LibRPA, and PyATB validation and controlled execution",
        instructions=(
            "Inspect and validate before execution. Controlled writes require an administrator-managed "
            "execution profile, immutable plan digest, fixed stage name, and registered run receipt. "
            "No tool accepts arbitrary shell, SSH, Slurm, cleanup, or retry commands."
        ),
        version="0.4.8",
    )
    annotations = _read_only_annotations()

    @server.tool(
        name="inspect_profile",
        description="Return the pinned ABACUS, LibRPA, PyATB revisions and workflow contract.",
        annotations=annotations,
        structured_output=True,
    )
    def inspect_profile(
        profile_path: str | None = None,
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Inspect a pinned OML compatibility profile without changing it."""
        return load_profile(profile_path, profile_id=profile_id)

    @server.tool(
        name="inspect_admission_manifest",
        description="Return a pinned route admission matrix, resource limits, and required gates.",
        annotations=annotations,
        structured_output=True,
    )
    def inspect_admission_manifest(
        path: str | None = None,
        manifest_id: str | None = None,
    ) -> dict[str, Any]:
        """Inspect a deterministic admission campaign without running it."""
        return load_admission_manifest(path, manifest_id=manifest_id)

    @server.tool(
        name="evaluate_admission",
        description="Evaluate structured route evidence with a versioned non-compensating scorecard.",
        annotations=annotations,
        structured_output=True,
    )
    def evaluate_admission(
        evidence: dict[str, Any],
        scorecard_version: Literal["v1", "v2", "v3"] = "v3",
    ) -> dict[str, Any]:
        """Score evidence while preserving hard failures and missing evidence."""
        scorecard_path = (
            Path(__file__).resolve().parent
            / "benchmarks"
            / f"scorecard-{scorecard_version}.json"
        )
        return evaluate_evidence(evidence, scorecard=load_scorecard(scorecard_path))

    @server.tool(
        name="inspect_route_benchmark",
        description="Return one immutable route-specific scientific benchmark and its hard tolerances.",
        annotations=annotations,
        structured_output=True,
    )
    def inspect_route_benchmark(benchmark_id: str) -> dict[str, Any]:
        """Inspect a registered route benchmark without changing evidence or policy."""
        return load_route_benchmark(benchmark_id)

    @server.tool(
        name="evaluate_route_benchmark",
        description="Recompute non-compensating scientific gates from a registered route benchmark and admission manifest.",
        annotations=annotations,
        structured_output=True,
    )
    def evaluate_route_benchmark(
        benchmark_id: str,
        manifest_id: str,
    ) -> dict[str, Any]:
        """Evaluate immutable registered evidence without submitting or promoting a route."""
        return evaluate_registered_route_benchmark(
            benchmark_id=benchmark_id,
            manifest_id=manifest_id,
        )

    @server.tool(
        name="evaluate_route_benchmark_suite",
        description="Replay frozen good and bad fixtures and report false-pass and false-block counts.",
        annotations=annotations,
        structured_output=True,
    )
    def evaluate_route_benchmark_suite(suite_id: str) -> dict[str, Any]:
        """Run a registered, read-only benchmark regression suite."""
        return evaluate_registered_route_benchmark_suite(suite_id=suite_id)

    @server.tool(
        name="propose_evolution_candidate",
        description="Validate one registered parameter change and return a proposal-only candidate.",
        annotations=annotations,
        structured_output=True,
    )
    def propose_evolution_candidate(
        route_id: AdmissionRoute,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        existing_definition_digests: list[str],
        max_candidates: int,
        max_cpu_hours: float,
        max_wall_seconds: int,
        max_disk_bytes: int,
        used_candidates: int = 0,
        used_cpu_hours: float = 0.0,
        used_wall_seconds: int = 0,
        used_disk_bytes: int = 0,
    ) -> dict[str, Any]:
        """Create no command, submission, or promotion side effect."""
        proposal = propose_candidate(
            route_id=route_id,
            baseline=baseline,
            candidate=candidate,
            existing_definition_digests=frozenset(existing_definition_digests),
            budget=EvolutionBudget(
                max_candidates=max_candidates,
                cpu_hours=max_cpu_hours,
                wall_seconds=max_wall_seconds,
                disk_bytes=max_disk_bytes,
            ),
            usage=EvolutionUsage(
                candidates=used_candidates,
                cpu_hours=used_cpu_hours,
                wall_seconds=used_wall_seconds,
                disk_bytes=used_disk_bytes,
            ),
        )
        return proposal.to_dict()

    @server.tool(
        name="ingest_case",
        description="Classify a local case and fingerprint every discovered input or artifact.",
        annotations=annotations,
        structured_output=True,
    )
    def ingest_case(path: str) -> dict[str, Any]:
        """Inspect case ownership and immutable input fingerprints."""
        return ingest_case_data(Path(path)).to_dict()

    @server.tool(
        name="plan_case",
        description="Select the deterministic read-only GW or RPA stage graph for a case.",
        annotations=annotations,
        structured_output=True,
    )
    def plan_case(
        path: str,
        task: Literal["gw", "rpa"],
        system_type: Literal["atom", "molecule", "solid", "2d"],
        use_symmetry: bool = False,
        soc: bool = False,
        headwing: bool | None = None,
        response_method: Literal["sos", "sternheimer"] = "sos",
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Plan a supported ABACUS plus LibRPA route without writing files."""
        return plan_case_data(
            Path(path),
            task=task,
            system_type=system_type,
            use_symmetry=use_symmetry,
            soc=soc,
            headwing=headwing,
            response_method=response_method,
            profile_id=profile_id,
        ).to_dict()

    @server.tool(
        name="validate_case",
        description="Run all pinned parameter, symmetry, shrink, dataset, and PyATB gates.",
        annotations=annotations,
        structured_output=True,
    )
    def validate_case(
        path: str,
        task: Literal["gw", "rpa"],
        system_type: Literal["atom", "molecule", "solid", "2d"],
        use_symmetry: bool = False,
        soc: bool = False,
        headwing: bool | None = None,
        stage: Literal["input", "pre_librpa"] = "pre_librpa",
        response_method: Literal["sos", "sternheimer"] = "sos",
        profile_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate an ABACUS plus LibRPA case and return every gate."""
        return validate_case_data(
            Path(path),
            task=task,
            system_type=system_type,
            use_symmetry=use_symmetry,
            soc=soc,
            headwing=headwing,
            stage=stage,
            response_method=response_method,
            profile_id=profile_id,
        ).to_dict()

    @server.tool(
        name="inspect_reader_v1",
        description="Validate a LibRPA reader-v1 eigenvector, velocity, or PyATB directory.",
        annotations=annotations,
        structured_output=True,
    )
    def inspect_reader_v1(path: str, artifact_kind: ArtifactKind) -> dict[str, Any]:
        """Inspect reader-v1 metadata and payload bounds without loading matrices."""
        artifact_path = Path(path)
        if artifact_kind == "eigenvector":
            return inspect_eigenvector_v1(artifact_path).to_dict()
        if artifact_kind == "velocity":
            return inspect_velocity_v1(artifact_path).to_dict()
        return inspect_headwing_directory(artifact_path).to_dict()

    @server.tool(
        name="inspect_grid_coulomb_consistency",
        description="Validate the dedicated Sternheimer Coulomb v1 metric and compare optional grid and ordinary reader metrics.",
        annotations=annotations,
        structured_output=True,
    )
    def inspect_grid_coulomb_consistency(
        path: str,
        iq: int,
        sqrt_coulomb_threshold: float = 0.0,
        hermitian_tolerance: float = 1.0e-10,
        metric_relative_tolerance: float = 1.0e-6,
    ) -> dict[str, Any]:
        """Read pre-response Coulomb diagnostics without changing inputs or jobs."""
        return inspect_grid_coulomb_consistency_data(
            Path(path),
            iq=iq,
            sqrt_coulomb_threshold=sqrt_coulomb_threshold,
            hermitian_tolerance=hermitian_tolerance,
            metric_relative_tolerance=metric_relative_tolerance,
        )

    @server.tool(
        name="inspect_sternheimer_comparison",
        description="Evaluate one Delta-ST response family with its dedicated Coulomb v1 metric and same-state diagnostics.",
        annotations=annotations,
        structured_output=True,
    )
    def inspect_sternheimer_comparison(
        path: str,
        iq: int,
        ifreq: int,
        sqrt_coulomb_threshold: float = 0.0,
        hermitian_tolerance: float = 1.0e-10,
        reconstruction_tolerance: float = 1.0e-8,
        metric_relative_tolerance: float = 1.0e-6,
    ) -> dict[str, Any]:
        """Read numerical diagnostics without changing inputs, jobs, or route status."""
        return inspect_sternheimer_comparison_data(
            Path(path),
            iq=iq,
            ifreq=ifreq,
            sqrt_coulomb_threshold=sqrt_coulomb_threshold,
            hermitian_tolerance=hermitian_tolerance,
            reconstruction_tolerance=reconstruction_tolerance,
            metric_relative_tolerance=metric_relative_tolerance,
        )

    @server.tool(
        name="prepare_run",
        description=(
            "Verify pinned source revisions and create a fresh immutable periodic-GW run from a reviewed plan digest."
        ),
        annotations=_write_annotations(idempotent=False),
        structured_output=True,
    )
    def prepare_run(
        source_path: str,
        plan_digest: str,
        execution_profile_id: str,
    ) -> dict[str, Any]:
        """Materialize one fresh controlled run without accepting command text."""
        return _controlled_call(
            lambda: _controlled_service(execution_profile_id).prepare_run(
                source_path, plan_digest
            )
        )

    @server.tool(
        name="submit_stage",
        description="Submit exactly one generated stage after provenance, version, order, and duplicate-job gates.",
        annotations=_write_annotations(idempotent=False),
        structured_output=True,
    )
    def submit_stage(
        run_id: str,
        stage: ControlledStage,
        plan_digest: str,
        execution_profile_id: str,
    ) -> dict[str, Any]:
        """Submit only a fixed stage from the immutable periodic-GW route."""
        return _controlled_call(
            lambda: _controlled_service(execution_profile_id).submit_stage(
                run_id, stage, plan_digest
            )
        )

    @server.tool(
        name="get_status",
        description="Read and normalize current or historical Slurm state for one registered attempt.",
        annotations=_external_read_annotations(),
        structured_output=True,
    )
    def get_status(
        run_id: str,
        attempt_id: str,
        execution_profile_id: str,
    ) -> dict[str, Any]:
        """Observe a registered attempt without claiming scientific stage success."""
        return _controlled_call(
            lambda: _controlled_service(
                execution_profile_id, initialize_state=False
            ).get_status(run_id, attempt_id)
        )

    @server.tool(
        name="inspect_stage",
        description="Snapshot and validate fixed stage artifacts, then record an immutable PASS or FAIL receipt.",
        annotations=_write_annotations(idempotent=True),
        structured_output=True,
    )
    def inspect_stage(
        run_id: str,
        attempt_id: str,
        plan_digest: str,
        execution_profile_id: str,
    ) -> dict[str, Any]:
        """Snapshot a terminal stage and accept only successful scheduler and artifact gates."""
        return _controlled_call(
            lambda: _controlled_service(execution_profile_id).inspect_stage(
                run_id, attempt_id, plan_digest
            )
        )

    @server.tool(
        name="finalize_case",
        description="Evaluate one passed 3D GW run against registered regression and convergence policy.",
        annotations=_write_annotations(idempotent=True),
        structured_output=True,
    )
    def finalize_case(
        run_id: str,
        plan_digest: str,
        benchmark_id: str,
        execution_profile_id: str,
        convergence_bundle_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a lineage-bound scientific verdict from registered evidence."""
        return _controlled_call(
            lambda: _controlled_service(execution_profile_id).finalize_case(
                run_id,
                plan_digest,
                benchmark_id,
                convergence_bundle_id,
            )
        )

    @server.tool(
        name="score_case",
        description="Score a registered run against the versioned 100-point scorecard and hard gates.",
        annotations=annotations,
        structured_output=True,
    )
    def score_case(
        run_id: str,
        plan_digest: str,
        execution_profile_id: str,
    ) -> dict[str, Any]:
        """Read receipts and report evaluated, failed, and not-evaluated dimensions separately."""
        return _controlled_call(
            lambda: _controlled_service(
                execution_profile_id, initialize_state=False
            ).score_case(run_id, plan_digest)
        )

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
