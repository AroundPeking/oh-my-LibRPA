import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from oml_mcp.server import build_server
from oml_mcp.profiles import V2_PROFILE_ID

from tests.test_artifacts import write_eigenvector_v1
import tests.test_validators as validator_fixtures


class MCPServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = build_server()

    async def test_exact_tool_surface_and_annotations(self):
        tools = await self.server.list_tools()
        self.assertEqual(
            {tool.name for tool in tools},
            {
                "inspect_profile",
                "inspect_admission_manifest",
                "ingest_case",
                "plan_case",
                "validate_case",
                "inspect_reader_v1",
                "evaluate_admission",
                "propose_evolution_candidate",
                "prepare_run",
                "submit_stage",
                "get_status",
                "inspect_stage",
                "finalize_case",
                "score_case",
            },
        )
        forbidden = ("shell", "ssh", "cleanup", "delete", "command", "run_job")
        self.assertFalse(any(word in tool.name for tool in tools for word in forbidden))
        by_name = {tool.name: tool for tool in tools}
        read_only = {
            "inspect_profile",
            "inspect_admission_manifest",
            "ingest_case",
            "plan_case",
            "validate_case",
            "inspect_reader_v1",
            "evaluate_admission",
            "propose_evolution_candidate",
            "get_status",
            "score_case",
        }
        for tool in tools:
            annotations = tool.annotations
            self.assertIsNotNone(annotations)
            self.assertEqual(annotations.read_only_hint, tool.name in read_only)
            self.assertFalse(annotations.destructive_hint)
        self.assertFalse(by_name["prepare_run"].annotations.idempotent_hint)
        self.assertFalse(by_name["submit_stage"].annotations.idempotent_hint)
        self.assertTrue(by_name["inspect_stage"].annotations.idempotent_hint)
        self.assertTrue(by_name["finalize_case"].annotations.idempotent_hint)
        self.assertFalse(by_name["finalize_case"].annotations.read_only_hint)
        self.assertTrue(by_name["get_status"].annotations.open_world_hint)

        finalize_schema = by_name["finalize_case"].input_schema
        self.assertEqual(
            set(finalize_schema["properties"]),
            {
                "run_id",
                "plan_digest",
                "benchmark_id",
                "execution_profile_id",
                "convergence_bundle_id",
            },
        )

        stage_schema = by_name["submit_stage"].input_schema
        self.assertEqual(
            stage_schema["properties"]["stage"]["enum"],
            ["scf", "pyatb", "nscf", "preprocess", "librpa"],
        )

    async def call(self, name: str, arguments: dict):
        result = await self.server.call_tool(name, arguments)
        self.assertFalse(result.is_error, result.content)
        self.assertIsNotNone(result.structured_content)
        return result.structured_content

    async def test_profile_intake_plan_and_validation_return_structured_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            validator_fixtures.WorkflowValidatorTest().make_case(root)

            profile = await self.call("inspect_profile", {})
            intake = await self.call("ingest_case", {"path": str(root)})
            plan = await self.call(
                "plan_case",
                {
                    "path": str(root),
                    "task": "gw",
                    "system_type": "solid",
                    "use_symmetry": True,
                },
            )
            report = await self.call(
                "validate_case",
                {
                    "path": str(root),
                    "task": "gw",
                    "system_type": "solid",
                    "use_symmetry": True,
                    "stage": "pre_librpa",
                },
            )

        self.assertEqual(profile["components"]["librpa"]["ref"], "v0.7.0")
        self.assertEqual(intake["stack"], "abacus_librpa")
        self.assertEqual(plan["route"], "periodic_gw_symmetry")
        self.assertTrue(report["accepted"], report)

    async def test_profile_and_planner_expose_v2_admission_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "INPUT_scf").write_text("INPUT_PARAMETERS\nrpa 1\n", encoding="utf-8")
            (root / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")

            profile = await self.call("inspect_profile", {"profile_id": V2_PROFILE_ID})
            plan = await self.call(
                "plan_case",
                {
                    "path": str(root),
                    "task": "rpa",
                    "system_type": "molecule",
                    "response_method": "sternheimer",
                    "profile_id": V2_PROFILE_ID,
                },
            )

        self.assertEqual(profile["profile_id"], V2_PROFILE_ID)
        self.assertEqual(plan["route"], "molecular_delta_st_rpa")
        self.assertEqual(plan["stages"], ["ground_state", "sternheimer", "librpa"])
        self.assertEqual(plan["options"]["capability"]["status"], "TESTABLE")

    async def test_reader_v1_dispatches_by_artifact_kind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "KS_eigenvector_0.dat"
            write_eigenvector_v1(path)
            info = await self.call(
                "inspect_reader_v1",
                {"path": str(path), "artifact_kind": "eigenvector"},
            )

        self.assertTrue(info["accepted"])
        self.assertEqual(info["format_version"], "v1")
        self.assertEqual(info["metadata"]["nstates"], 3)

    async def test_stdio_protocol_initializes_lists_and_calls_tools(self):
        repository = pathlib.Path(__file__).resolve().parents[1]
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "oml_mcp.server"],
            cwd=repository,
        )
        with open("/dev/null", "w", encoding="utf-8") as devnull:
            async with stdio_client(parameters, errlog=devnull) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    initialized = await session.initialize()
                    listed = await session.list_tools()
                    called = await session.call_tool("inspect_profile", {})

        self.assertEqual(initialized.server_info.name, "oh-my-librpa")
        self.assertEqual(len(listed.tools), 14)
        self.assertFalse(called.is_error)
        self.assertEqual(called.structured_content["components"]["librpa"]["ref"], "v0.7.0")

    async def test_admission_and_evolution_tools_are_deterministic_and_read_only(self):
        manifest = await self.call("inspect_admission_manifest", {})
        score = await self.call(
            "evaluate_admission",
            {
                "evidence": {
                    "dimensions": {
                        "reproducibility": 1.0,
                        "prevention": 1.0,
                        "stage_evidence": 1.0,
                        "numerical_evaluation": 1.0,
                        "scientific_evaluation": None,
                        "diagnosis_quality": 1.0,
                    },
                    "hard_gates": {
                        "stack_identity": True,
                        "file_contract": True,
                        "finite_output": True,
                        "channel_completeness": True,
                        "scientific_acceptance": None,
                    },
                    "penalties": {"failed_attempts": 0, "ambiguous_attempts": 0},
                },
                "scorecard_version": "v2",
            },
        )
        proposal = await self.call(
            "propose_evolution_candidate",
            {
                "route_id": "periodic_3d_gw",
                "baseline": {"nfreq": 12, "nbands": 40},
                "candidate": {"nfreq": 16, "nbands": 40},
                "existing_definition_digests": [],
                "max_candidates": 4,
                "max_cpu_hours": 20.0,
                "max_wall_seconds": 7200,
                "max_disk_bytes": 1000000000,
            },
        )

        self.assertEqual(manifest["profile_id"], V2_PROFILE_ID)
        self.assertEqual(score["verdict"], "INCOMPLETE")
        self.assertEqual(proposal["status"], "PROPOSAL_ONLY")
        self.assertEqual(proposal["changed_axis"], "nfreq")

    async def test_controlled_tools_forward_only_typed_receipt_identifiers(self):
        class FakeService:
            def prepare_run(self, source_path, plan_digest):
                return {"operation": "prepare", "source_path": source_path, "plan_digest": plan_digest}

            def submit_stage(self, run_id, stage, plan_digest):
                return {"operation": "submit", "run_id": run_id, "stage": stage, "plan_digest": plan_digest}

            def get_status(self, run_id, attempt_id):
                return {"operation": "status", "run_id": run_id, "attempt_id": attempt_id}

            def inspect_stage(self, run_id, attempt_id, plan_digest):
                return {
                    "operation": "inspect",
                    "run_id": run_id,
                    "attempt_id": attempt_id,
                    "plan_digest": plan_digest,
                }

            def score_case(self, run_id, plan_digest):
                return {"operation": "score", "run_id": run_id, "plan_digest": plan_digest}

            def finalize_case(
                self, run_id, plan_digest, benchmark_id, convergence_bundle_id=None
            ):
                return {
                    "operation": "finalize",
                    "run_id": run_id,
                    "plan_digest": plan_digest,
                    "benchmark_id": benchmark_id,
                    "convergence_bundle_id": convergence_bundle_id,
                }

        calls = (
            (
                "prepare_run",
                {"source_path": "/approved/source", "plan_digest": "a" * 64, "execution_profile_id": "hpc"},
                "prepare",
            ),
            (
                "submit_stage",
                {"run_id": "run-1", "stage": "scf", "plan_digest": "a" * 64, "execution_profile_id": "hpc"},
                "submit",
            ),
            (
                "get_status",
                {"run_id": "run-1", "attempt_id": "attempt-1", "execution_profile_id": "hpc"},
                "status",
            ),
            (
                "inspect_stage",
                {
                    "run_id": "run-1",
                    "attempt_id": "attempt-1",
                    "plan_digest": "a" * 64,
                    "execution_profile_id": "hpc",
                },
                "inspect",
            ),
            (
                "finalize_case",
                {
                    "run_id": "run-1",
                    "plan_digest": "a" * 64,
                    "benchmark_id": "bn-reader-v1-3d-v1",
                    "execution_profile_id": "hpc",
                    "convergence_bundle_id": "bn-nfreq-v1",
                },
                "finalize",
            ),
            (
                "score_case",
                {"run_id": "run-1", "plan_digest": "a" * 64, "execution_profile_id": "hpc"},
                "score",
            ),
        )
        with patch("oml_mcp.server._controlled_service", return_value=FakeService()) as service:
            for name, arguments, operation in calls:
                result = await self.call(name, arguments)
                self.assertEqual(result["operation"], operation)

        self.assertEqual([item.args[0] for item in service.call_args_list], ["hpc"] * 6)
        self.assertEqual(
            [item.kwargs.get("initialize_state", True) for item in service.call_args_list],
            [True, True, False, True, True, False],
        )

    async def test_controlled_tool_returns_stable_structured_profile_error(self):
        result = await self.call(
            "prepare_run",
            {
                "source_path": "/approved/source",
                "plan_digest": "a" * 64,
                "execution_profile_id": "not-installed",
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "PROFILE_NOT_FOUND")
        self.assertTrue(result["error"]["recovery"])


if __name__ == "__main__":
    unittest.main()
