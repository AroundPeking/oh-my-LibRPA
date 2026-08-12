import pathlib
import tempfile
import unittest


from oml_mcp.intake import ingest_case
from oml_mcp.planner import PlanError, plan_case


class IntakeTest(unittest.TestCase):
    def test_abacus_case_is_classified_and_fingerprinted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "INPUT_scf").write_text("INPUT_PARAMETERS\nrpa 1\n", encoding="utf-8")
            (root / "KPT_scf").write_text("K_POINTS\n0\nGamma\n1 1 1 0 0 0\n", encoding="utf-8")
            (root / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")

            report = ingest_case(root)

        self.assertTrue(report.accepted)
        self.assertEqual(report.stack, "abacus_librpa")
        names = {item["path"] for item in report.files}
        self.assertEqual(names, {"INPUT_scf", "KPT_scf", "STRU"})
        self.assertTrue(all(len(item["sha256"]) == 64 for item in report.files))

    def test_mixed_abacus_and_fhi_aims_markers_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "INPUT_scf").write_text("INPUT_PARAMETERS\n", encoding="utf-8")
            (root / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")
            (root / "control.in").write_text("xc pbe\n", encoding="utf-8")
            (root / "geometry.in").write_text("atom 0 0 0 H\n", encoding="utf-8")

            report = ingest_case(root)

        self.assertFalse(report.accepted)
        self.assertEqual(report.stack, "mixed")
        self.assertEqual(report.gates[0].gate_id, "intake.stack_ownership")

    def test_reader_v1_artifacts_are_classified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            for name in (
                "INPUT_scf",
                "STRU",
                "stru_out",
                "bz_sampling_out",
                "basis_wfc_out",
                "basis_aux_out",
                "v1_coulomb_full_iq_0.txt",
                "v1_Cs_data_0.txt",
            ):
                (root / name).write_text(name, encoding="utf-8")

            report = ingest_case(root)

        kinds = {item["path"]: item["kind"] for item in report.files}
        self.assertEqual(kinds["v1_coulomb_full_iq_0.txt"], "reader_v1_coulomb")
        self.assertEqual(kinds["v1_Cs_data_0.txt"], "reader_v1_lri")
        self.assertEqual(kinds["stru_out"], "producer_metadata")


class PlannerTest(unittest.TestCase):
    def make_abacus_case(self, root: pathlib.Path) -> None:
        (root / "INPUT_scf").write_text("INPUT_PARAMETERS\nrpa 1\n", encoding="utf-8")
        (root / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")

    def test_molecular_gw_short_route(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            plan = plan_case(root, task="gw", system_type="molecule")

        self.assertEqual(plan.route, "molecular_gw")
        self.assertEqual(plan.stages, ("scf", "librpa"))

    def test_periodic_gw_and_symmetry_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            normal = plan_case(root, task="gw", system_type="solid")
            symmetry = plan_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                headwing=True,
            )

        self.assertEqual(normal.route, "periodic_gw")
        self.assertEqual(
            normal.stages,
            ("scf", "pyatb", "nscf", "preprocess", "librpa"),
        )
        self.assertEqual(symmetry.route, "periodic_gw_symmetry")
        self.assertIn("pyatb_full_grid", symmetry.stages)

    def test_rpa_route_has_no_pyatb_or_nscf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            plan = plan_case(root, task="rpa", system_type="solid")

        self.assertEqual(plan.route, "rpa")
        self.assertEqual(plan.stages, ("scf", "librpa"))

    def test_soc_forces_periodic_no_symmetry_route(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            plan = plan_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                soc=True,
            )

        self.assertEqual(plan.route, "periodic_gw")
        self.assertTrue(any("SOC" in item for item in plan.assumptions))

    def test_mixed_stack_cannot_be_planned(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            (root / "control.in").write_text("xc pbe\n", encoding="utf-8")
            (root / "geometry.in").write_text("atom 0 0 0 H\n", encoding="utf-8")

            with self.assertRaisesRegex(PlanError, "mixed"):
                plan_case(root, task="gw", system_type="solid")


if __name__ == "__main__":
    unittest.main()
