import pathlib
import tempfile
import unittest


from oml_mcp.intake import ingest_case
from oml_mcp.planner import PlanError, plan_case
from oml_mcp.profiles import (
    DEFAULT_PROFILE_ID,
    LEGACY_PROFILE_ID,
    V2_PROFILE_ID,
    V3_PROFILE_ID,
)


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
                "v1_sternheimer_coulomb_iq_21_rank0.dat",
                "v1_Cs_data_0.txt",
            ):
                (root / name).write_text(name, encoding="utf-8")

            report = ingest_case(root)

        kinds = {item["path"]: item["kind"] for item in report.files}
        self.assertEqual(kinds["v1_coulomb_full_iq_0.txt"], "reader_v1_coulomb")
        self.assertEqual(
            kinds["v1_sternheimer_coulomb_iq_21_rank0.dat"],
            "sternheimer_coulomb_v1",
        )
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
            plan = plan_case(
                root,
                task="gw",
                system_type="molecule",
                profile_id=LEGACY_PROFILE_ID,
            )

        self.assertEqual(plan.route, "molecular_gw")
        self.assertEqual(plan.stages, ("scf", "librpa"))

    def test_route_incompatible_headwing_and_symmetry_requests_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)

            with self.assertRaisesRegex(PlanError, "symmetry"):
                plan_case(
                    root,
                    task="gw",
                    system_type="molecule",
                    use_symmetry=True,
                    profile_id=LEGACY_PROFILE_ID,
                )
            with self.assertRaisesRegex(PlanError, "head/wing"):
                plan_case(
                    root,
                    task="gw",
                    system_type="molecule",
                    headwing=True,
                    profile_id=LEGACY_PROFILE_ID,
                )

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

    def test_periodic_gw_can_disable_headwing_without_scheduling_pyatb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            normal = plan_case(
                root,
                task="gw",
                system_type="solid",
                headwing=False,
            )
            symmetry = plan_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                headwing=False,
            )

        self.assertEqual(normal.route, "periodic_gw_no_headwing")
        self.assertEqual(normal.stages, ("scf", "nscf", "preprocess", "librpa"))
        self.assertFalse(normal.options["headwing"])
        self.assertEqual(symmetry.route, "periodic_gw_symmetry_no_headwing")
        self.assertNotIn("pyatb", symmetry.stages)

    def test_current_strict_2d_route_is_admission_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            plan = plan_case(root, task="gw", system_type="2d")

        self.assertEqual(plan.route, "strict_2d_gw")
        self.assertEqual(
            plan.stages,
            ("scf", "pyatb", "nscf", "preprocess", "librpa"),
        )
        self.assertTrue(plan.accepted)
        self.assertEqual(plan.gates[0].status, "WARN")
        self.assertEqual(plan.options["capability"]["status"], "TESTABLE")

    def test_rpa_route_has_no_pyatb_or_nscf(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            plan = plan_case(
                root,
                task="rpa",
                system_type="solid",
                profile_id=LEGACY_PROFILE_ID,
            )

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

    def test_v2_profile_plans_the_four_testable_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            periodic = plan_case(
                root,
                task="gw",
                system_type="solid",
                profile_id=V2_PROFILE_ID,
            )
            strict_2d = plan_case(
                root,
                task="gw",
                system_type="2d",
                profile_id=V2_PROFILE_ID,
            )
            molecular_delta = plan_case(
                root,
                task="rpa",
                system_type="molecule",
                response_method="sternheimer",
                profile_id=V2_PROFILE_ID,
            )
            solid_delta = plan_case(
                root,
                task="rpa",
                system_type="solid",
                response_method="sternheimer",
                profile_id=V2_PROFILE_ID,
            )

        self.assertEqual(periodic.route, "periodic_gw")
        self.assertEqual(strict_2d.route, "strict_2d_gw")
        self.assertEqual(
            strict_2d.stages,
            ("scf", "pyatb", "nscf", "preprocess", "librpa"),
        )
        self.assertEqual(molecular_delta.route, "molecular_delta_st_rpa")
        self.assertEqual(
            molecular_delta.stages,
            ("ground_state", "sternheimer", "librpa"),
        )
        self.assertEqual(solid_delta.route, "solid_delta_st_rpa")
        self.assertEqual(
            solid_delta.stages,
            ("ground_state", "sternheimer", "librpa"),
        )
        for plan in (periodic, strict_2d, molecular_delta, solid_delta):
            self.assertEqual(plan.profile_id, V2_PROFILE_ID)
            self.assertEqual(plan.options["reader_format"], "v1")
            self.assertEqual(plan.options["capability"]["status"], "TESTABLE")
            self.assertEqual(plan.gates[0].status, "WARN")

    def test_explicit_current_profile_preserves_default_plan_digest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)
            implicit = plan_case(root, task="gw", system_type="solid")
            explicit = plan_case(
                root,
                task="gw",
                system_type="solid",
                profile_id=DEFAULT_PROFILE_ID,
            )

        self.assertEqual(explicit.digest, implicit.digest)
        self.assertEqual(explicit.options, implicit.options)

    def test_v3_profile_plans_the_definition_matched_sternheimer_route(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)

            plan = plan_case(
                root,
                task="rpa",
                system_type="solid",
                response_method="sternheimer",
                profile_id=V3_PROFILE_ID,
            )

        self.assertEqual(plan.profile_id, V3_PROFILE_ID)
        self.assertEqual(plan.route, "solid_delta_st_rpa")
        self.assertEqual(plan.stages, ("ground_state", "sternheimer", "librpa"))

    def test_current_default_plans_sternheimer_as_admission_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_abacus_case(root)

            plan = plan_case(
                root,
                task="rpa",
                system_type="solid",
                response_method="sternheimer",
            )

        self.assertEqual(plan.profile_id, DEFAULT_PROFILE_ID)
        self.assertEqual(plan.route, "solid_delta_st_rpa")
        self.assertEqual(plan.options["capability"]["status"], "TESTABLE")


if __name__ == "__main__":
    unittest.main()
