from __future__ import annotations

import pathlib
import tempfile
import unittest


CONTROL = """xc                pbe
relativistic      atomic_zora scalar
k_grid            4 4 4
output            librpa binary mommat
"""

CONTROL_WITHOUT_LIBRPA = """xc      pbe
k_grid  4 4 4
"""

GEOMETRY = """lattice_vector 5.43 0.00 0.00
lattice_vector 0.00 5.43 0.00
lattice_vector 0.00 0.00 5.43
atom 0.00 0.00 0.00 Si
atom 1.36 1.36 1.36 Si
"""

LIBRPA = """task = g0w0
nfreq = 16
option_dielect_func = 3
replace_w_head = t
"""


class AimsRouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _bundle(self, control=CONTROL):
        (self.root / "control.in").write_text(control, encoding="utf-8")
        (self.root / "geometry.in").write_text(GEOMETRY, encoding="utf-8")
        (self.root / "librpa.in").write_text(LIBRPA, encoding="utf-8")
        return self.root

    def test_an_aims_bundle_is_classified_and_planned(self):
        from oml_mcp.intake import ingest_case
        from oml_mcp.planner import plan_case

        root = self._bundle()
        self.assertEqual(ingest_case(root).stack, "fhi_aims_librpa")
        plan = plan_case(root, task="gw", system_type="solid", headwing=True)
        self.assertEqual(plan.route, "periodic_gw_aims")
        # LibRPA reads the aims Coulomb blocks and eigenvectors directly, so the
        # chain must not contain the ABACUS NSCF/preprocess stages.
        self.assertEqual(tuple(plan.stages), ("aims", "librpa"))

    def test_the_diagnostic_route_is_available(self):
        from oml_mcp.planner import plan_case

        plan = plan_case(
            self._bundle(), task="gw", system_type="solid", headwing=False
        )
        self.assertEqual(plan.route, "periodic_gw_aims_no_headwing")

    def test_out_of_scope_aims_cases_are_refused_with_a_reason(self):
        from oml_mcp.planner import PlanError, plan_case

        root = self._bundle()
        cases = (
            ({"soc": True}, "SOC velocity"),
            ({"use_symmetry": True}, "k-star symmetry"),
            ({"system_type": "molecule"}, "periodic solids only"),
            ({"system_type": "2d"}, "strict-2D"),
        )
        for overrides, expected in cases:
            kwargs = {"task": "gw", "system_type": "solid", "headwing": True}
            kwargs.update(overrides)
            with self.subTest(**overrides):
                with self.assertRaises(PlanError) as caught:
                    plan_case(root, **kwargs)
                self.assertIn(expected, str(caught.exception))

    def test_a_bundle_without_output_librpa_is_refused_before_it_runs(self):
        from oml_mcp.errors import OMLError
        from oml_mcp.materializer import _verify_aims_inputs

        root = self._bundle(control=CONTROL_WITHOUT_LIBRPA)
        with self.assertRaises(OMLError) as caught:
            _verify_aims_inputs(root)
        self.assertIn("output librpa", " ".join(caught.exception.evidence))

    def test_the_output_librpa_scan_ignores_comments_and_subtags(self):
        from oml_mcp.materializer import _control_in_requests_librpa

        self.assertTrue(_control_in_requests_librpa("output librpa binary mommat\n"))
        self.assertTrue(_control_in_requests_librpa("  output   librpa\n"))
        self.assertTrue(_control_in_requests_librpa("output librpa noC\n"))
        self.assertFalse(_control_in_requests_librpa("# output librpa\n"))
        self.assertFalse(_control_in_requests_librpa("xc pbe\n"))
        # A different output directive must not be mistaken for the LibRPA one.
        self.assertFalse(_control_in_requests_librpa("output dipole\n"))

    def test_an_empty_geometry_is_refused(self):
        from oml_mcp.errors import OMLError
        from oml_mcp.materializer import _verify_aims_inputs

        root = self._bundle()
        (root / "geometry.in").write_text("", encoding="utf-8")
        with self.assertRaises(OMLError) as caught:
            _verify_aims_inputs(root)
        self.assertIn("geometry.in", " ".join(caught.exception.evidence))

    def test_control_in_is_recorded_as_an_execution_input(self):
        from oml_mcp.provenance import execution_input_manifest

        root = self._bundle()
        names = {item["path"] for item in execution_input_manifest(root)}
        self.assertIn("control.in", names)
        self.assertIn("geometry.in", names)
        self.assertIn("librpa.in", names)


if __name__ == "__main__":
    unittest.main()


class AimsValidatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "control.in").write_text(CONTROL, encoding="utf-8")
        (self.root / "geometry.in").write_text(GEOMETRY, encoding="utf-8")
        (self.root / "librpa.in").write_text(LIBRPA, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_complete_aims_bundle_is_accepted(self):
        from oml_mcp.validators import validate_case

        report = validate_case(
            self.root, task="gw", system_type="solid", stage="input"
        )
        self.assertTrue(report.accepted, report.to_dict())
        self.assertEqual(
            [g.gate_id for g in report.gates if g.gate_id == "aims.inputs"],
            ["aims.inputs"],
        )

    def test_abacus_only_gates_are_reported_as_skipped_not_passed(self):
        # An aims bundle cannot satisfy the ABACUS gates. Silence would read as
        # a clean bill of health, so each one is reported with its reason.
        from oml_mcp.validators import validate_case

        report = validate_case(
            self.root, task="gw", system_type="solid", stage="input"
        )
        skipped = {g.gate_id for g in report.gates if g.status == "SKIP"}
        self.assertIn("abacus.producer", skipped)
        self.assertIn("symmetry.alignment", skipped)
        self.assertIn("nbands.consistency", skipped)

    def test_a_bundle_without_output_librpa_fails(self):
        from oml_mcp.validators import validate_case

        (self.root / "control.in").write_text(
            CONTROL_WITHOUT_LIBRPA, encoding="utf-8"
        )
        report = validate_case(
            self.root, task="gw", system_type="solid", stage="input"
        )
        self.assertFalse(report.accepted)
        gate = [g for g in report.gates if g.gate_id == "aims.inputs"][0]
        self.assertEqual(gate.status, "FAIL")
        self.assertIn("output librpa", gate.message)


class AimsMaterializationTest(unittest.TestCase):
    """The aims bundle must materialize into a run with the right two stages."""

    def setUp(self):
        import shutil

        from oml_mcp.execution_profiles import ExecutionProfile

        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name).resolve()
        self.src = base / "case"
        self.src.mkdir()
        for name, text in (
            ("control.in", CONTROL),
            ("geometry.in", GEOMETRY),
            ("librpa.in", LIBRPA),
        ):
            (self.src / name).write_text(text, encoding="utf-8")
        runroot = base / "runs"
        runroot.mkdir()
        resources = {
            "partition": "debug",
            "nodes": 1,
            "ntasks_per_node": 4,
            "cpus_per_task": 8,
            "memory_mb": 64000,
            "walltime_minutes": 0,
        }
        self.profile = ExecutionProfile(
            profile_id="aims-probe",
            source_path=base / "p.json",
            transport="local",
            allowed_source_roots=(base,),
            allowed_run_roots=(runroot,),
            state_db=base / "state.db",
            scheduler=resources,
            resources=resources,
            runtime={
                "python": "/usr/bin/python3",
                "mpi_launcher": "/usr/bin/mpirun",
                "abacus": "/x/abacus",
                "librpa": "/x/chi0",
                "aims": "/opt/aims.mpi.x",
                "mpi_ranks": 4,
                "pyatb_mpi_ranks": 1,
                "omp_threads": 8,
            },
            sources={},
            environment={},
            ssh=None,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_run_carries_aims_then_librpa_and_renders_the_buffering(self):
        from oml_mcp.materializer import prepare_run
        from oml_mcp.planner import plan_case

        plan = plan_case(self.src, task="gw", system_type="solid", headwing=True)
        result = prepare_run(
            self.src,
            plan.digest,
            self.profile,
            execution_receipt={"probe": True},
            profile_id=None,
        )
        self.assertEqual(tuple(result["stages"]), ("aims", "librpa"))
        run_dir = pathlib.Path(result["local_run_dir"])
        stage_script = (run_dir / ".oml" / "stages" / "aims.slurm").read_text()
        self.assertIn("export FORT_BUFFERED=TRUE", stage_script)
        self.assertIn('"$OML_AIMS"', stage_script)

    def test_an_aims_run_records_that_the_basis_disclosure_does_not_apply(self):
        # An aims case has no STRU/PP/NAO/ABFS set. Recording "not-applicable"
        # keeps the acknowledgement step from reading silence as a clean bill.
        from oml_mcp.materializer import prepare_run
        from oml_mcp.planner import plan_case

        plan = plan_case(self.src, task="gw", system_type="solid", headwing=True)
        result = prepare_run(
            self.src,
            plan.digest,
            self.profile,
            execution_receipt={"probe": True},
            profile_id=None,
        )
        self.assertEqual(result["basis_disclosure"]["state"], "not-applicable")
        self.assertIn("control.in", result["basis_disclosure"]["reason"])


class AimsScopeGuardTest(unittest.TestCase):
    """Checks that must hold for an aims bundle just as for an ABACUS one."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        (self.root / "control.in").write_text(CONTROL, encoding="utf-8")
        (self.root / "geometry.in").write_text(GEOMETRY, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_input_dir_outside_the_bundle_is_refused(self):
        # input_dir is producer-independent: LibRPA reads from it either way, so
        # a path leaving the immutable bundle must fail on both branches.
        from oml_mcp.errors import OMLError
        from oml_mcp.materializer import _verify_controlled_scope

        (self.root / "librpa.in").write_text(
            "task = g0w0\ninput_dir = ../../elsewhere\nnfreq = 16\n",
            encoding="utf-8",
        )

        class Plan:
            route = "periodic_gw_aims"
            options = {"system_type": "solid", "soc": False}

        with self.assertRaises(OMLError) as caught:
            _verify_controlled_scope(self.root, Plan())
        self.assertIn("immutable run bundle", str(caught.exception))

    def test_an_in_bundle_input_dir_is_accepted(self):
        from oml_mcp.materializer import _verify_controlled_scope

        (self.root / "librpa.in").write_text(
            "task = g0w0\ninput_dir = .\nnfreq = 16\n", encoding="utf-8"
        )

        class Plan:
            route = "periodic_gw_aims"
            options = {"system_type": "solid", "soc": False}

        _verify_controlled_scope(self.root, Plan())

    def test_an_aims_bundle_cannot_run_an_abacus_route(self):
        from oml_mcp.errors import OMLError
        from oml_mcp.materializer import _verify_aims_scope

        class Plan:
            route = "periodic_gw"
            options = {"system_type": "solid", "soc": False}

        with self.assertRaises(OMLError) as caught:
            _verify_aims_scope(self.root, Plan())
        self.assertIn("FHI-aims bundle", str(caught.exception))
