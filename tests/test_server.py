import pathlib
import sys
import tempfile
import unittest


from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from oml_mcp.server import build_server

from tests.test_artifacts import write_eigenvector_v1
import tests.test_validators as validator_fixtures


class MCPServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = build_server()

    async def test_exact_read_only_tool_surface(self):
        tools = await self.server.list_tools()
        self.assertEqual(
            {tool.name for tool in tools},
            {"inspect_profile", "ingest_case", "plan_case", "validate_case", "inspect_reader_v1"},
        )
        forbidden = ("submit", "shell", "ssh", "cleanup", "delete", "command", "run_job")
        self.assertFalse(any(word in tool.name for tool in tools for word in forbidden))
        for tool in tools:
            annotations = tool.annotations
            self.assertIsNotNone(annotations)
            self.assertTrue(annotations.read_only_hint)
            self.assertFalse(annotations.destructive_hint)

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
        self.assertEqual(len(listed.tools), 5)
        self.assertFalse(called.is_error)
        self.assertEqual(called.structured_content["components"]["librpa"]["ref"], "v0.7.0")


if __name__ == "__main__":
    unittest.main()
