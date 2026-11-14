from __future__ import annotations

import unittest


class FortranBufferingTest(unittest.TestCase):
    """The Fortran producer stage must run with its runtime buffering on.

    FHI-aims writes its Coulomb export one complex number per WRITE. At 128 atoms
    that is about 9.7e8 calls; measured on fisherd with ifx, 3e7 values took
    36.4 s unbuffered and 20.6 s buffered for byte-identical output.
    """

    def test_both_vendor_runtimes_are_pinned_on(self):
        from oml_mcp.stage_templates import FORTRAN_BUFFERED_ENVIRONMENT

        # ifx/ifort: this is the switch that turns buffering on.
        self.assertEqual(FORTRAN_BUFFERED_ENVIRONMENT["FORT_BUFFERED"], "TRUE")
        # gfortran buffers by default, so its variable must assert "not disabled"
        # rather than be left to inherit whatever the module system set - setting
        # it to 1 measured 1.53x SLOWER than the default.
        self.assertEqual(FORTRAN_BUFFERED_ENVIRONMENT["GFORTRAN_UNBUFFERED_ALL"], "0")

    def test_every_controlled_stage_exports_it(self):
        from oml_mcp.stage_templates import (
            CONTROLLED_PERIODIC_STAGES,
            render_stage_script,
        )

        resources = {
            "partition": "debug",
            "nodes": 1,
            "ntasks_per_node": 1,
            "cpus_per_task": 24,
            "memory_mb": 8000,
        }
        for stage in CONTROLLED_PERIODIC_STAGES:
            with self.subTest(stage=stage):
                script = render_stage_script(stage, run_id="r", resources=resources)
                self.assertIn("export FORT_BUFFERED=TRUE", script)
                self.assertIn("export GFORTRAN_UNBUFFERED_ALL=0", script)

    def test_the_login_node_path_exports_it_too(self):
        # The scheduled path exports this in its SBATCH prologue; the login-node
        # path renders its own script and would otherwise differ from it.
        from oml_mcp.stage_execution import render_login_node_script

        runtime = {
            "python": "/usr/bin/python3",
            "mpi_launcher": "/usr/bin/mpirun",
            "abacus": "/x/abacus",
            "librpa": "/x/chi0_main.exe",
            "mpi_ranks": 1,
            "pyatb_mpi_ranks": 1,
            "omp_threads": 8,
        }
        script = render_login_node_script(
            "nscf", runtime=runtime, run_id="r", attempt_id="a"
        )
        self.assertIn("export FORT_BUFFERED=TRUE", script)
        self.assertIn("export GFORTRAN_UNBUFFERED_ALL=0", script)

    def test_a_profile_may_still_override_a_value(self):
        from oml_mcp.stage_templates import render_fortran_environment

        rendered = render_fortran_environment({"FORT_BUFFERED": "FALSE"})
        self.assertIn("export FORT_BUFFERED=FALSE", rendered)
        self.assertIn("export GFORTRAN_UNBUFFERED_ALL=0", rendered)

    def test_the_override_survives_into_the_rendered_script(self):
        # The rendered script sources .oml/env.sh first and then exports its own
        # lines, so a bare default there would always beat the profile. The
        # profile's value has to be threaded through or it is silently ignored.
        from oml_mcp.stage_templates import render_stage_script

        resources = {
            "partition": "debug",
            "nodes": 1,
            "ntasks_per_node": 1,
            "cpus_per_task": 4,
            "memory_mb": 4000,
        }
        overridden = render_stage_script(
            "scf",
            run_id="r",
            resources=resources,
            environment={"FORT_BUFFERED": "FALSE"},
        )
        self.assertIn("export FORT_BUFFERED=FALSE", overridden)
        self.assertNotIn("export FORT_BUFFERED=TRUE", overridden)
        # An unrelated profile variable must not leak into the buffering block.
        other = render_stage_script(
            "scf",
            run_id="r",
            resources=resources,
            environment={"PATH": "/usr/bin"},
        )
        self.assertIn("export FORT_BUFFERED=TRUE", other)


if __name__ == "__main__":
    unittest.main()


class AimsStageTest(unittest.TestCase):
    """The FHI-aims producer stage and the route that reaches it."""

    def _resources(self):
        return {
            "partition": "debug",
            "nodes": 1,
            "ntasks_per_node": 4,
            "cpus_per_task": 8,
            "memory_mb": 64000,
        }

    def _runtime(self, with_aims=True):
        runtime = {
            "python": "/usr/bin/python3",
            "mpi_launcher": "/usr/bin/mpirun",
            "abacus": "/x/abacus",
            "librpa": "/x/chi0_main.exe",
            "mpi_ranks": 4,
            "pyatb_mpi_ranks": 1,
            "omp_threads": 8,
        }
        if with_aims:
            runtime["aims"] = "/opt/aims/aims.mpi.x"
        return runtime

    def test_the_aims_stage_runs_the_producer_and_checks_the_output(self):
        from oml_mcp.stage_templates import render_stage_script

        script = render_stage_script(
            "aims", run_id="r", resources=self._resources()
        )
        # It reads control.in/geometry.in in place; there is no copy-to-INPUT step
        # and no KPT file, unlike the ABACUS stages.
        self.assertIn('test -s "geometry.in"', script)
        self.assertIn('test -s "control.in"', script)
        self.assertIn('"$OML_AIMS"', script)
        self.assertNotIn('cp -- "KPT_scf"', script)
        # A silent producer that wrote nothing must fail here, not three stages
        # later inside LibRPA's reader.
        self.assertIn("coulomb_mat_*", script)

    def test_the_aims_stage_carries_the_fortran_buffering(self):
        # This is the stage the buffering exists for: FHI-aims writes one complex
        # number per WRITE. 36.4 s -> 20.6 s for 3e7 values.
        from oml_mcp.stage_templates import render_stage_script

        script = render_stage_script(
            "aims", run_id="r", resources=self._resources()
        )
        self.assertIn("export FORT_BUFFERED=TRUE", script)
        self.assertIn("export GFORTRAN_UNBUFFERED_ALL=0", script)

    def test_a_profile_without_an_aims_binary_fails_loudly(self):
        from oml_mcp.stage_templates import render_env, render_stage_script

        env = render_env(
            self._runtime(with_aims=False),
            environment={},
            run_id="r",
            plan_digest="d",
        )
        self.assertNotIn("OML_AIMS", env)
        # The body must name the missing setting rather than exec an empty path.
        script = render_stage_script(
            "aims", run_id="r", resources=self._resources()
        )
        self.assertIn('${OML_AIMS:?', script)

    def test_the_aims_stage_is_a_scheduler_stage(self):
        from oml_mcp.stage_execution import STAGE_EXECUTION_MODES

        self.assertEqual(STAGE_EXECUTION_MODES["aims"], "scheduler")

    def test_aims_and_abacus_stage_lists_stay_distinct(self):
        from oml_mcp.stage_templates import (
            CONTROLLED_AIMS_STAGES,
            CONTROLLED_PERIODIC_STAGES,
            CONTROLLED_STAGE_NAMES,
        )

        # ABACUS runs must not be asked for an aims receipt.
        self.assertNotIn("aims", CONTROLLED_PERIODIC_STAGES)
        self.assertEqual(CONTROLLED_AIMS_STAGES, ("aims", "librpa"))
        self.assertIn("aims", CONTROLLED_STAGE_NAMES)
        self.assertIn("scf", CONTROLLED_STAGE_NAMES)
