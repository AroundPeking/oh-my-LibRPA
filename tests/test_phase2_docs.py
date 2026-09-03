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
            "inspect_admission_manifest",
            "inspect_route_benchmark",
            "evaluate_route_benchmark",
            "evaluate_route_benchmark_suite",
            "ingest_case",
            "plan_case",
            "validate_case",
            "inspect_grid_coulomb_consistency",
            "inspect_sternheimer_comparison",
            "evaluate_admission",
            "propose_evolution_candidate",
            "prepare_run",
            "submit_stage",
            "get_status",
            "inspect_stage",
            "finalize_case",
            "score_case",
        ):
            self.assertIn(f"`{tool}`", text)
        self.assertIn("never bypass", text.lower())
        self.assertIn("FHI-aims writes on existing reviewed routes", text)
        self.assertNotIn("run_gw_workflow.sh", text)

    def test_installation_guide_separates_production_and_admission_profiles(self):
        text = (REPOSITORY / "docs" / "guide" / "installation.md").read_text(
            encoding="utf-8"
        )

        for phrase in (
            "19 MCP tools",
            "inspect_admission_manifest",
            "inspect_route_benchmark",
            "evaluate_route_benchmark",
            "evaluate_route_benchmark_suite",
            "inspect_grid_coulomb_consistency",
            "inspect_sternheimer_comparison",
            "evaluate_admission",
            "propose_evolution_candidate",
            "abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08",
            "abacus-librpa-2026-08-30-v2",
            "abacus-librpa-2026-08-30-v3",
            "v1_sternheimer_coulomb_iq_",
            "TESTABLE",
            "not promoted automatically",
        ):
            self.assertIn(phrase, text)

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
            "COMPLETED",
            "FAILED",
            "CANCELLED",
            "PyATB",
            "nbands",
            "COMPLETE_BASIS_STATE_SPACE",
            "basis completeness",
        ):
            self.assertIn(text, guide)

    def test_df_bn_followup_checkpoint_keeps_execution_and_science_separate(self):
        checkpoint = json.loads(
            (
                REPOSITORY
                / "benchmarks"
                / "live"
                / "df-bn-reader-v1-2026-08-18.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(checkpoint["evaluator_version"], 6)
        self.assertEqual(checkpoint["status"]["execution"], "PASS")
        self.assertEqual(checkpoint["status"]["scientific_acceptance"], "FAIL")
        self.assertEqual(checkpoint["status"]["strict_2d"], "NOT_RUN")
        self.assertEqual(len(checkpoint["runs"]), 4)
        self.assertTrue(
            all(
                stage["state"] == "COMPLETED" and stage["exit_code"] == "0:0"
                for run in checkpoint["runs"]
                for stage in run["jobs"].values()
            )
        )
        axes = {item["comparison_id"]: item for item in checkpoint["convergence"]}
        self.assertEqual(axes["empty-states-25-26"]["status"], "PASS")
        self.assertEqual(
            axes["empty-states-25-26"]["reason_code"],
            "COMPLETE_BASIS_STATE_SPACE",
        )
        self.assertEqual(axes["nfreq-16-24"]["status"], "FAIL")
        self.assertEqual(axes["screening-kgrid-4-8"]["status"], "FAIL")

    def test_version_metadata_is_consistent(self):
        plugin = json.loads((REPOSITORY / ".codex-plugin" / "plugin.json").read_text())
        pyproject = (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
        package = (REPOSITORY / "oml_mcp" / "__init__.py").read_text(encoding="utf-8")
        server = (REPOSITORY / "oml_mcp" / "server.py").read_text(encoding="utf-8")

        self.assertEqual(plugin["version"], "0.4.5")
        self.assertIn('version = "0.4.5"', pyproject)
        self.assertIn('"benchmark_suites/*.json"', pyproject)
        self.assertIn('"route_benchmarks/*.json"', pyproject)
        self.assertIn('__version__ = "0.4.5"', package)
        self.assertIn('version="0.4.5"', server)

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

    def test_admission_scope_and_evolution_boundary_are_documented(self):
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        skill = (REPOSITORY / "skills" / "oh-my-librpa" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        for text in (readme, skill):
            for phrase in (
                "abacus-librpa-2026-08-30-v2",
                "abacus-librpa-2026-08-30-v3",
                "periodic 3D GW",
                "strict-2D GW",
                "molecular Delta-Sternheimer RPA",
                "solid Delta-Sternheimer RPA",
                "reader v1",
                "PROPOSAL_ONLY",
            ):
                self.assertIn(phrase, text)
            self.assertIn("sidecars", text)


if __name__ == "__main__":
    unittest.main()
