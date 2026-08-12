import pathlib
import tempfile
import unittest


from oml_mcp.stage_inspection import inspect_stage_outputs
from tests.test_artifacts import write_eigenvector_v1, write_headwing_metadata, write_velocity_v1


def command_completed(root: pathlib.Path, stage: str) -> None:
    path = root / ".oml" / "stage-results" / f"{stage}.status"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("COMMAND_COMPLETED\n", encoding="utf-8")


class StageInspectionTest(unittest.TestCase):
    def test_scf_requires_abacus_completion_and_reader_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            command_completed(root, "scf")
            output = root / "OUT.ABACUS"
            output.mkdir()
            (output / "running_scf.log").write_text(
                "Finish Time\nTotal Time\n", encoding="utf-8"
            )
            (output / "ABACUS-CHARGE-DENSITY.restart").write_text("charge\n")
            (root / "vxc_out").write_text("vxc\n")
            (root / "stru_out").write_text("structure\n")

            accepted = inspect_stage_outputs(root, "scf")
            (root / "stru_out").unlink()
            rejected = inspect_stage_outputs(root, "scf")

        self.assertTrue(accepted["accepted"])
        self.assertFalse(rejected["accepted"])
        self.assertTrue(any(gate["gate_id"] == "stage.scf.artifacts" for gate in rejected["gates"]))

    def test_pyatb_uses_reader_v1_dimension_and_coverage_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            command_completed(root, "pyatb")
            headwing = root / "pyatb_librpa_df"
            headwing.mkdir()
            write_headwing_metadata(headwing)
            write_eigenvector_v1(headwing / "KS_eigenvector_0.dat")
            write_velocity_v1(headwing / "velocity_matrix")
            for name in ("band_out", "basis_wfc_out", "basis_aux_out"):
                (root / name).write_text("data\n")
            for name in (
                "KS_eigenvector_0.dat",
                "v1_Cs_data_0.dat",
                "v1_coulomb_full_iq_1_rank0.dat",
                "v1_coulomb_cut_iq_1_rank0.dat",
            ):
                (root / name).write_bytes(b"data")

            accepted = inspect_stage_outputs(root, "pyatb")
            write_velocity_v1(headwing / "velocity_matrix", nbands=4)
            rejected = inspect_stage_outputs(root, "pyatb")

        self.assertTrue(accepted["accepted"])
        self.assertFalse(rejected["accepted"])
        self.assertTrue(any(gate["gate_id"] == "pyatb.dimensions.velocity" for gate in rejected["gates"]))

    def test_preprocess_requires_finite_nonempty_band_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            command_completed(root, "preprocess")
            (root / "band_kpath_info").write_text("2 3 1 1\n0 0 0\n")
            (root / "band_KS_eigenvalue_k_00001.txt").write_text("0.1 0.2\n")
            (root / "band_KS_eigenvector_k_00001.txt").write_text("1.0 0.0\n")
            (root / "band_vxc_k_00001.txt").write_text("0.0 0.0\n")

            accepted = inspect_stage_outputs(root, "preprocess")
            (root / "band_vxc_k_00001.txt").write_text("nan\n")
            rejected = inspect_stage_outputs(root, "preprocess")

        self.assertTrue(accepted["accepted"])
        self.assertFalse(rejected["accepted"])
        self.assertTrue(any(gate["gate_id"] == "stage.preprocess.finite" for gate in rejected["gates"]))

    def test_librpa_completion_marker_does_not_accept_nonfinite_gw_band(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            command_completed(root, "librpa")
            (root / "LibRPA.123.out").write_text("libRPA finished successfully\n")
            (root / "band_kpath_info").write_text("2 2 1 1\n0 0 0\n")
            gw = root / "GW_band_spin_1.dat"
            gw.write_text("1 0 0 0 0.0 5.0 0.0 6.0\n")

            accepted = inspect_stage_outputs(root, "librpa")
            gw.write_text("1 0 0 0 0.0 nan 0.0 6.0\n")
            rejected = inspect_stage_outputs(root, "librpa")

        self.assertTrue(accepted["accepted"])
        self.assertFalse(rejected["accepted"])
        self.assertTrue(any(gate["gate_id"] == "stage.librpa.gw_data" for gate in rejected["gates"]))

    def test_librpa_gw_band_rows_must_match_band_kpath(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            command_completed(root, "librpa")
            (root / "LibRPA.123.out").write_text("Timer stop:  total.\n")
            (root / "band_kpath_info").write_text("2 2 1 2\n0 0 0\n0.5 0 0\n")
            (root / "GW_band_spin_1.dat").write_text("1 0 0 0 0.0 5.0 0.0 6.0\n")

            report = inspect_stage_outputs(root, "librpa")

        self.assertFalse(report["accepted"])
        self.assertTrue(any(gate["gate_id"] == "stage.librpa.gw_shape" for gate in report["gates"]))


if __name__ == "__main__":
    unittest.main()
