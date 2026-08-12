import pathlib
import tempfile
import unittest


from oml_mcp.validators import validate_case
from tests.test_artifacts import (
    write_eigenvector_v1,
    write_headwing_metadata,
    write_velocity_v1,
)


STRU_OUT_BASE = """1 0 0
0 1 0
0 0 1
6.283185307 0 0
0 6.283185307 0
0 0 6.283185307
1
0 0 0 1
"""


class WorkflowValidatorTest(unittest.TestCase):
    def make_case(
        self,
        root: pathlib.Path,
        *,
        use_symmetry: bool = True,
        soc: bool = False,
        shrink: bool = True,
        headwing: bool = True,
        task: str = "g0w0",
    ) -> None:
        symmetry = 1 if use_symmetry else -1
        abacus_lines = [
            "INPUT_PARAMETERS",
            "calculation scf",
            "basis_type lcao",
            "rpa 1",
            "out_librpa_reader_version 1",
            f"symmetry {symmetry}",
        ]
        if shrink:
            abacus_lines.extend(("shrink_abfs_pca_thr 1e-4", "shrink_lu_inv_thr 1e-3"))
        (root / "INPUT_scf").write_text("\n".join(abacus_lines) + "\n", encoding="utf-8")
        (root / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")

        librpa_lines = [
            f"task = {task}",
            "input_dir = dataset",
            "prefix_coul_full = v1_coulomb_full_iq_",
            "prefix_coul_cut = v1_coulomb_cut_iq_",
            "prefix_lri_coeff = v1_Cs_data_",
            "fn_stru = stru_out",
            "fn_bz_sampling = bz_sampling_out",
            "fn_basis_wfc = basis_wfc_out",
            "fn_basis_aux = basis_aux_out",
            "version_coul_reader = 1",
            "version_lri_reader = 1",
            f"use_shrink_abfs = {'t' if shrink else 'f'}",
            f"replace_w_head = {'t' if headwing else 'f'}",
            f"use_soc = {1 if soc else 0}",
            f"use_symmetry_exx = {'t' if use_symmetry else 'f'}",
            f"use_symmetry_gw = {'t' if use_symmetry else 'f'}",
        ]
        if shrink:
            librpa_lines.extend(
                (
                    "prefix_lri_coeff_shrink = v1_Cs_shrinked_data_",
                    "prefix_shrink_sinvS = v1_shrink_sinvS_",
                    "fn_basis_aux_shrink = basis_aux_shrink_out",
                )
            )
        (root / "librpa.in").write_text("\n".join(librpa_lines) + "\n", encoding="utf-8")

        dataset = root / "dataset"
        dataset.mkdir()
        symmetry_tail = "1 row\n1 0 0 0 1 0 0 0 1 0.0 0.0 0.0\n" if use_symmetry else ""
        (dataset / "stru_out").write_text(
            STRU_OUT_BASE + symmetry_tail,
            encoding="utf-8",
        )
        for name in ("bz_sampling_out", "basis_wfc_out", "basis_aux_out", "band_out"):
            (dataset / name).write_text(name + "\n", encoding="utf-8")
        for name in (
            "v1_coulomb_full_iq_0.txt",
            "v1_coulomb_cut_iq_0.txt",
            "v1_Cs_data_0.txt",
        ):
            (dataset / name).write_text("v1\n", encoding="utf-8")
        if shrink:
            for name in (
                "basis_aux_shrink_out",
                "v1_Cs_shrinked_data_0.txt",
                "v1_shrink_sinvS_0.txt",
            ):
                (dataset / name).write_text("v1 shrink\n", encoding="utf-8")

        if headwing:
            pyatb = root / "pyatb_librpa_df"
            pyatb.mkdir()
            write_headwing_metadata(pyatb)
            write_eigenvector_v1(pyatb / "KS_eigenvector_0.dat")
            write_velocity_v1(pyatb / "velocity_matrix")

    @staticmethod
    def gate(report, gate_id: str):
        return next(item for item in report.gates if item.gate_id == gate_id)

    def test_complete_periodic_symmetry_case_passes_without_legacy_sidecars(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            report = validate_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                stage="pre_librpa",
            )

        self.assertTrue(report.accepted, report.to_dict())
        self.assertEqual(self.gate(report, "symmetry.sidecars").status, "PASS")
        self.assertEqual(self.gate(report, "pyatb.headwing").status, "PASS")

    def test_obsolete_symmetry_keys_fail_with_exact_replacements(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            path = root / "librpa.in"
            text = path.read_text(encoding="utf-8")
            text = text.replace("use_symmetry_exx", "use_input_exx_symmetry")
            text = text.replace("use_symmetry_gw", "use_input_gw_symmetry")
            path.write_text(text, encoding="utf-8")
            report = validate_case(root, task="gw", system_type="solid", use_symmetry=True)

        gate = self.gate(report, "librpa.unsupported_keys")
        self.assertEqual(gate.status, "FAIL")
        self.assertIn("use_symmetry_exx", gate.repair)
        self.assertIn("use_symmetry_gw", gate.repair)

    def test_deprecated_g0w0_band_is_a_warning_with_g0w0_replacement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root, task="g0w0_band")
            report = validate_case(root, task="gw", system_type="solid", use_symmetry=True)

        gate = self.gate(report, "librpa.task")
        self.assertEqual(gate.status, "WARN")
        self.assertTrue(report.accepted)
        self.assertIn("g0w0", gate.repair)

    def test_explicit_reader_v1_contract_is_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            path = root / "INPUT_scf"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "out_librpa_reader_version 1", "out_librpa_reader_version 0"
                ),
                encoding="utf-8",
            )
            librpa = root / "librpa.in"
            librpa.write_text(
                librpa.read_text(encoding="utf-8").replace(
                    "version_coul_reader = 1", "version_coul_reader = -1"
                ),
                encoding="utf-8",
            )
            report = validate_case(root, task="gw", system_type="solid", use_symmetry=True)

        self.assertEqual(self.gate(report, "abacus.reader_v1").status, "FAIL")
        self.assertEqual(self.gate(report, "librpa.reader_v1").status, "FAIL")

    def test_soc_requires_all_spatial_symmetry_switches_off(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root, use_symmetry=False, soc=True)
            valid = validate_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=False,
                soc=True,
            )
            librpa = root / "librpa.in"
            librpa.write_text(
                librpa.read_text(encoding="utf-8").replace(
                    "use_symmetry_gw = f", "use_symmetry_gw = t"
                ),
                encoding="utf-8",
            )
            invalid = validate_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=False,
                soc=True,
            )

        self.assertTrue(valid.accepted, valid.to_dict())
        self.assertEqual(self.gate(invalid, "symmetry.alignment").status, "FAIL")

    def test_shrink_input_and_artifacts_must_agree(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            (root / "dataset" / "basis_aux_shrink_out").unlink()
            report = validate_case(root, task="gw", system_type="solid", use_symmetry=True)

        gate = self.gate(report, "shrink.artifacts")
        self.assertEqual(gate.status, "FAIL")
        self.assertIn("basis_aux_shrink_out", gate.evidence)

    def test_headwing_directory_is_required_and_fully_validated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            (root / "pyatb_librpa_df" / "velocity_matrix").unlink()
            report = validate_case(root, task="gw", system_type="solid", use_symmetry=True)

        self.assertFalse(report.accepted)
        self.assertEqual(self.gate(report, "pyatb.velocity").status, "FAIL")

    def test_mixed_legacy_and_v1_dataset_families_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            (root / "dataset" / "coulomb_mat_0.txt").write_text("legacy\n", encoding="utf-8")
            report = validate_case(root, task="gw", system_type="solid", use_symmetry=True)

        self.assertEqual(self.gate(report, "dataset.format_families").status, "FAIL")

    def test_input_stage_skips_output_artifact_checks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            for child in tuple((root / "dataset").iterdir()):
                child.unlink()
            for child in tuple((root / "pyatb_librpa_df").iterdir()):
                child.unlink()
            (root / "dataset").rmdir()
            (root / "pyatb_librpa_df").rmdir()
            report = validate_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                stage="input",
            )

        self.assertTrue(report.accepted, report.to_dict())
        self.assertEqual(self.gate(report, "dataset.artifacts").status, "SKIP")
        self.assertEqual(self.gate(report, "pyatb.headwing").status, "SKIP")


if __name__ == "__main__":
    unittest.main()
