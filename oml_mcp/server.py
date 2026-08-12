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
from .intake import ingest_case as ingest_case_data
from .planner import plan_case as plan_case_data
from .profiles import load_profile
from .validators import validate_case as validate_case_data


ArtifactKind = Literal["eigenvector", "velocity", "headwing"]


def _read_only_annotations() -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )


def build_server() -> MCPServer:
    server = MCPServer(
        name="oh-my-librpa",
        title="Oh-My-LibRPA",
        description="Read-only ABACUS, LibRPA, and PyATB workflow inspection",
        instructions=(
            "Use these tools before preparing or running ABACUS plus LibRPA cases. "
            "They inspect local files and return deterministic gates; they never modify or submit work."
        ),
        version="0.1.0",
    )
    annotations = _read_only_annotations()

    @server.tool(
        name="inspect_profile",
        description="Return the pinned ABACUS, LibRPA, PyATB revisions and workflow contract.",
        annotations=annotations,
        structured_output=True,
    )
    def inspect_profile(profile_path: str | None = None) -> dict[str, Any]:
        """Inspect a pinned OML compatibility profile without changing it."""
        return load_profile(profile_path)

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
    ) -> dict[str, Any]:
        """Plan a supported ABACUS plus LibRPA route without writing files."""
        return plan_case_data(
            Path(path),
            task=task,
            system_type=system_type,
            use_symmetry=use_symmetry,
            soc=soc,
            headwing=headwing,
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
        stage: Literal["input", "pre_librpa"] = "pre_librpa",
    ) -> dict[str, Any]:
        """Validate an ABACUS plus LibRPA case and return every gate."""
        return validate_case_data(
            Path(path),
            task=task,
            system_type=system_type,
            use_symmetry=use_symmetry,
            soc=soc,
            stage=stage,
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

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
