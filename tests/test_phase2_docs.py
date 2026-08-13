import json
import pathlib
import unittest


REPOSITORY = pathlib.Path(__file__).resolve().parents[1]


class PhaseTwoDocumentationTest(unittest.TestCase):
    def test_thin_skill_routes_controlled_execution_through_mcp(self):
        text = (REPOSITORY / "skills" / "oh-my-librpa" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertLessEqual(len(text.split()), 220)
        for tool in (
            "inspect_profile",
            "ingest_case",
            "plan_case",
            "validate_case",
            "prepare_run",
            "submit_stage",
            "get_status",
            "inspect_stage",
            "finalize_case",
            "score_case",
        ):
            self.assertIn(f"`{tool}`", text)
        self.assertIn("never bypass", text.lower())
        self.assertNotIn("run_gw_workflow.sh", text)

    def test_execution_guide_documents_profile_and_scope_boundaries(self):
        guide = (REPOSITORY / "docs" / "guide" / "controlled-execution.md").read_text(
            encoding="utf-8"
        )

        for text in (
            "OML_EXECUTION_PROFILE_ROOTS",
            "history_program",
            "sources",
            "git_program",
            "prepare_run",
            "submit_stage",
            "inspect_stage",
            "score_case",
            "finalize_case",
            "NOT_EVALUATED",
            "non-SOC periodic GW",
            "sidecars",
            "environment",
            "mpi_ranks",
            "perform.sh",
            "UNKNOWN",
            "squeue",
            "sacct",
            "LIBRPA_070_STRICT_2D_INVALID",
            "0.001 eV",
            "0.05 eV",
            "VBM-3",
            "CBM+3",
        ):
            self.assertIn(text, guide)

    def test_version_metadata_is_consistent(self):
        plugin = json.loads((REPOSITORY / ".codex-plugin" / "plugin.json").read_text())
        pyproject = (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
        package = (REPOSITORY / "oml_mcp" / "__init__.py").read_text(encoding="utf-8")

        self.assertEqual(plugin["version"], "0.3.0")
        self.assertIn('version = "0.3.0"', pyproject)
        self.assertIn('__version__ = "0.3.0"', package)

    def test_siab_first_order_wavefunction_plan_is_preserved(self):
        text = (
            REPOSITORY / "docs" / "research-siab-first-order-wavefunction-plan.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "uniform real-space grid",
            "plane-wave `Ecut`",
            "delta-Sternheimer",
            "first-order atomic and molecular wavefunctions",
            "SIAB `DPSI`",
        ):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
