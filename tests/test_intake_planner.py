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

    def test_route_incompatible_headwing_and_symmetry_requests_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)

            with self.assertRaisesRegex(PlanError, "head/wing"):
                plan_case(root, task="gw", system_type="solid", headwing=False)
            with self.assertRaisesRegex(PlanError, "symmetry"):
                plan_case(root, task="gw", system_type="molecule", use_symmetry=True)
            with self.assertRaisesRegex(PlanError, "head/wing"):
                plan_case(root, task="gw", system_type="molecule", headwing=True)

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
        self.assertEqual(
            symmetry.stages,
            ("scf", "pyatb", "nscf", "preprocess", "librpa"),
        )
        self.assertTrue(symmetry.options["use_symmetry"])

    def test_strict_2d_route_is_discoverable_but_has_no_executable_stages(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            plan = plan_case(root, task="gw", system_type="2d")

        self.assertEqual(plan.route, "strict_2d_gw_deferred")
        self.assertEqual(plan.stages, ())
        self.assertTrue(plan.accepted)
        self.assertEqual(plan.gates[0].status, "WARN")
        self.assertEqual(
            plan.options["capability"]["reason_code"],
            "LIBRPA_070_STRICT_2D_INVALID",
        )

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

    def test_plan_digest_is_stable_and_tracks_only_execution_inputs(self):
        with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
            left = pathlib.Path(left_tmp)
            right = pathlib.Path(right_tmp)
            for root in (left, right):
                self.make_abacus_case(root)
                (root / "KPT_scf").write_text("K_POINTS\n0\nGamma\n2 2 2 0 0 0\n", encoding="utf-8")
                (root / "Si.upf").write_text("pseudo\n", encoding="utf-8")
                (root / "Si.orb").write_text("orbital\n", encoding="utf-8")
                (root / "Si.abfs").write_text("auxiliary\n", encoding="utf-8")
                (root / "get_diel.py").write_text("print('headwing')\n", encoding="utf-8")
                (root / "OUT.ABACUS").mkdir()
                (root / "OUT.ABACUS" / "running_scf.log").write_text("old output\n", encoding="utf-8")
                (root / "v1_Cs_data_0").write_text("old producer output\n", encoding="utf-8")

            first = plan_case(left, task="gw", system_type="solid")
            second = plan_case(right, task="gw", system_type="solid")
            (right / "OUT.ABACUS" / "running_scf.log").write_text("changed output\n", encoding="utf-8")
            output_changed = plan_case(right, task="gw", system_type="solid")
            (right / "KPT_scf").write_text("K_POINTS\n0\nGamma\n3 3 3 0 0 0\n", encoding="utf-8")
            input_changed = plan_case(right, task="gw", system_type="solid")

        self.assertEqual(first.digest, second.digest)
        self.assertNotEqual(first.plan_id, second.plan_id)
        self.assertEqual(second.digest, output_changed.digest)
        self.assertNotEqual(output_changed.digest, input_changed.digest)
        self.assertEqual(len(first.digest), 64)
        manifest_paths = {item["path"] for item in first.source_manifest}
        self.assertIn("Si.upf", manifest_paths)
        self.assertIn("get_diel.py", manifest_paths)
        self.assertNotIn("OUT.ABACUS/running_scf.log", manifest_paths)
        self.assertNotIn("v1_Cs_data_0", manifest_paths)

    def test_plan_digest_changes_with_route_options(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            normal = plan_case(root, task="gw", system_type="solid")
            symmetry = plan_case(root, task="gw", system_type="solid", use_symmetry=True)

        self.assertNotEqual(normal.digest, symmetry.digest)
        self.assertNotEqual(normal.plan_id, symmetry.plan_id)
        self.assertEqual(normal.source_digest, symmetry.source_digest)

    def test_stage_specific_inputs_exclude_mutable_generic_work_copies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            (root / "INPUT_scf").write_text(
                "INPUT_PARAMETERS\nbasis_type lcao\nrpa 1\nout_librpa_reader_version 1\n",
                encoding="utf-8",
            )
            (root / "KPT_scf").write_text("K_POINTS\n0\nGamma\n2 2 2 0 0 0\n")
            (root / "INPUT").write_text("stale working copy\n")
            (root / "KPT").write_text("stale working copy\n")

            plan = plan_case(root, task="gw", system_type="solid")

        paths = {item["path"] for item in plan.source_manifest}
        self.assertIn("INPUT_scf", paths)
        self.assertIn("KPT_scf", paths)
        self.assertNotIn("INPUT", paths)
        self.assertNotIn("KPT", paths)


if __name__ == "__main__":
    unittest.main()
