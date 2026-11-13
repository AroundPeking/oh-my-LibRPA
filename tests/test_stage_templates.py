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

    def test_a_profile_may_still_override_a_value(self):
        from oml_mcp.stage_templates import render_fortran_environment

        rendered = render_fortran_environment({"FORT_BUFFERED": "FALSE"})
        self.assertIn("export FORT_BUFFERED=FALSE", rendered)
        self.assertIn("export GFORTRAN_UNBUFFERED_ALL=0", rendered)


if __name__ == "__main__":
    unittest.main()
