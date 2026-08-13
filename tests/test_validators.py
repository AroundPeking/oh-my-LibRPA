import pathlib
import struct
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


def write_split_basis(path: pathlib.Path, size: int) -> None:
    shells = "\n".join("0" for _ in range(size))
    path.write_text(f"1 {size} abacus\n1 {size}\n1 {size}\n{shells}\n", encoding="utf-8")


def write_coulomb_v1(
    path: pathlib.Path,
    *,
    iq: int = 1,
    naux: int = 2,
    marker: int = -20129433,
) -> None:
    offset = 24 + 4 + 12
    data = struct.pack("=6i", marker, iq, naux, 1, 1, 1)
    data += struct.pack("=i", naux)
    data += struct.pack("=iq", 0, offset)
    data += bytes(naux * naux * 16)
    path.write_bytes(data)


def write_cs_v1(
    path: pathlib.Path,
    *,
    aux_size: int = 2,
    marker: int = -10267453,
) -> None:
    offset = 28 + 36
    data = struct.pack("=3i2q", marker, 1, 0, 1, 1)
    data += struct.pack("=5idq", 1, 1, 0, 0, 0, 1.0, offset)
    data += bytes(2 * 2 * aux_size * 8)
    path.write_bytes(data)


def write_shrink_sinvs_v1(
    path: pathlib.Path,
    *,
    iq: int = 1,
    marker: int = -30241621,
) -> None:
    offset = 8 + 44
    data = struct.pack("=2i", marker, 1)
    data += struct.pack("=7idq", iq, 1, 2, 1, 1, 1, 2, 1.0, offset)
    data += bytes(1 * 2 * 16)
    path.write_bytes(data)


def write_band_out(path: pathlib.Path, *, nkpoints: int = 1) -> None:
    blocks = []
    for ik in range(1, nkpoints + 1):
        blocks.extend(
            (
                f"{ik} 1",
                "1 2.0 -0.5 -13.6",
                "2 0.0 0.2 5.4",
                "3 0.0 0.4 10.9",
            )
        )
    path.write_text(
        f"{nkpoints}\n1\n3\n2\n0.0\n" + "\n".join(blocks) + "\n",
        encoding="utf-8",
    )


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
            "prefix_eigvecs_scf = KS_eigenvector",
            "prefix_lri_coeff = v1_Cs_data_",
            "fn_stru = stru_out",
            "fn_bz_sampling = bz_sampling_out",
            "fn_basis_wfc = basis_wfc_out",
            "fn_basis_aux = basis_aux_out",
            "fn_eigocc_scf = band_out",
            "fn_vxc_scf = vxc_out",
            "version_coul_reader = 1",
            "version_lri_reader = 1",
            f"use_shrink_abfs = {'t' if shrink else 'f'}",
            f"replace_w_head = {'t' if headwing else 'f'}",
            f"use_soc = {1 if soc else 0}",
        ]
        if task == "rpa":
            librpa_lines.append(f"use_symmetry_rpa = {'t' if use_symmetry else 'f'}")
        else:
            librpa_lines.extend(
                (
                    f"use_symmetry_exx = {'t' if use_symmetry else 'f'}",
                    f"use_symmetry_gw = {'t' if use_symmetry else 'f'}",
                )
            )
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
        (dataset / "bz_sampling_out").write_text(
            "1 1 1\n1 1\n1 1.0 0 0 0 0 0 0 1 1\n",
            encoding="utf-8",
        )
        write_band_out(dataset / "band_out")
        write_eigenvector_v1(dataset / "KS_eigenvector_0.dat", nkpoints=1)
        (dataset / "vxc_out").write_text(
            "1\n1\n3\n-0.4 -10.9\n-0.2 -5.4\n-0.1 -2.7\n", encoding="utf-8"
        )
        write_split_basis(dataset / "basis_wfc_out", 2)
        write_split_basis(dataset / "basis_aux_out", 2)
        coulomb_naux = 1 if shrink else 2
        write_coulomb_v1(dataset / "v1_coulomb_full_iq_1_rank0.dat", naux=coulomb_naux)
        write_coulomb_v1(dataset / "v1_coulomb_cut_iq_1_rank0.dat", naux=coulomb_naux)
        write_cs_v1(dataset / "v1_Cs_data_0.txt")
        if shrink:
            write_split_basis(dataset / "basis_aux_shrink_out", 1)
            write_cs_v1(dataset / "v1_Cs_shrinked_data_0.txt", aux_size=1)
            write_shrink_sinvs_v1(dataset / "v1_shrink_sinvS_0.txt")

        if headwing:
            pyatb = dataset / "pyatb_librpa_df"
            pyatb.mkdir()
            write_headwing_metadata(pyatb, nkpoints=1)
            write_eigenvector_v1(pyatb / "KS_eigenvector_0.dat", nkpoints=1)
            write_velocity_v1(pyatb / "velocity_matrix", nkpoints=1)

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
        self.assertEqual(self.gate(report, "basis.v1").status, "PASS")
        self.assertEqual(self.gate(report, "bz_sampling.format").status, "PASS")
        self.assertEqual(self.gate(report, "dataset.v1_payloads").status, "PASS")
        self.assertEqual(self.gate(report, "dataset.eigenvectors").status, "PASS")
        self.assertEqual(self.gate(report, "gw.vxc").status, "PASS")
        self.assertEqual(self.gate(report, "pyatb.headwing").status, "PASS")
        self.assertEqual(self.gate(report, "pyatb.alignment").status, "PASS")

    def test_reader_v1_dataset_marker_and_payload_bounds_are_required(self):
        with tempfile.TemporaryDirectory() as marker_tmp, tempfile.TemporaryDirectory() as truncated_tmp:
            marker_root = pathlib.Path(marker_tmp)
            truncated_root = pathlib.Path(truncated_tmp)
            self.make_case(marker_root)
            self.make_case(truncated_root)
            write_cs_v1(marker_root / "dataset" / "v1_Cs_data_0.txt", marker=-7)
            coulomb = truncated_root / "dataset" / "v1_coulomb_full_iq_1_rank0.dat"
            coulomb.write_bytes(coulomb.read_bytes()[:-16])

            marker_report = validate_case(
                marker_root, task="gw", system_type="solid", use_symmetry=True
            )
            truncated_report = validate_case(
                truncated_root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(marker_report, "dataset.v1_payloads").status, "FAIL")
        self.assertEqual(self.gate(truncated_report, "dataset.v1_payloads").status, "FAIL")

    def test_main_eigenvectors_require_v1_dimensions_and_full_coverage(self):
        with tempfile.TemporaryDirectory() as marker_tmp, tempfile.TemporaryDirectory() as coverage_tmp:
            marker_root = pathlib.Path(marker_tmp)
            coverage_root = pathlib.Path(coverage_tmp)
            self.make_case(marker_root)
            self.make_case(coverage_root)
            eigen = marker_root / "dataset" / "KS_eigenvector_0.dat"
            data = bytearray(eigen.read_bytes())
            struct.pack_into("=i", data, 0, -7)
            eigen.write_bytes(data)
            write_eigenvector_v1(
                coverage_root / "dataset" / "KS_eigenvector_0.dat",
                nkpoints=1,
                indices=(2,),
            )

            marker_report = validate_case(
                marker_root, task="gw", system_type="solid", use_symmetry=True
            )
            coverage_report = validate_case(
                coverage_root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(marker_report, "dataset.eigenvectors").status, "FAIL")
        self.assertEqual(self.gate(coverage_report, "dataset.eigenvectors").status, "FAIL")

    def test_gw_requires_complete_dimensionally_consistent_vxc(self):
        with tempfile.TemporaryDirectory() as missing_tmp, tempfile.TemporaryDirectory() as dims_tmp:
            missing_root = pathlib.Path(missing_tmp)
            dims_root = pathlib.Path(dims_tmp)
            self.make_case(missing_root)
            self.make_case(dims_root)
            (missing_root / "dataset" / "vxc_out").unlink()
            (dims_root / "dataset" / "vxc_out").write_text(
                "1\n1\n2\n-0.4 -10.9\n-0.2 -5.4\n", encoding="utf-8"
            )

            missing_report = validate_case(
                missing_root, task="gw", system_type="solid", use_symmetry=True
            )
            dims_report = validate_case(
                dims_root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(missing_report, "gw.vxc").status, "FAIL")
        self.assertEqual(self.gate(dims_report, "gw.vxc").status, "FAIL")

    def test_split_basis_and_coulomb_q_sets_are_cross_checked(self):
        with tempfile.TemporaryDirectory() as basis_tmp, tempfile.TemporaryDirectory() as q_tmp:
            basis_root = pathlib.Path(basis_tmp)
            q_root = pathlib.Path(q_tmp)
            self.make_case(basis_root)
            self.make_case(q_root)
            (basis_root / "dataset" / "basis_aux_out").write_text(
                "1 2 abacus\n1 2\n1 1\n0\n", encoding="utf-8"
            )
            (q_root / "dataset" / "v1_coulomb_cut_iq_1_rank0.dat").unlink()
            write_coulomb_v1(
                q_root / "dataset" / "v1_coulomb_cut_iq_2_rank0.dat",
                iq=2,
                naux=1,
            )

            basis_report = validate_case(
                basis_root, task="gw", system_type="solid", use_symmetry=True
            )
            q_report = validate_case(
                q_root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(basis_report, "basis.v1").status, "FAIL")
        self.assertEqual(self.gate(q_report, "dataset.coulomb_q").status, "FAIL")

    def test_shrink_sinvs_q_set_must_match_bz_sampling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            write_shrink_sinvs_v1(
                root / "dataset" / "v1_shrink_sinvS_0.txt",
                iq=2,
            )

            report = validate_case(
                root, task="gw", system_type="solid", use_symmetry=True
            )

        gate = self.gate(report, "dataset.v1_payloads")
        self.assertEqual(gate.status, "FAIL")
        self.assertTrue(any("q-point coverage" in item for item in gate.evidence))

    def test_coulomb_q_coverage_must_match_bz_sampling(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            (root / "dataset" / "bz_sampling_out").write_text(
                "1 1 2\n2 2\n1 0.5 0 0 0 0 0 0 1 1\n2 0.5 0 0 0.5 0 0 0.5 2 2\n",
                encoding="utf-8",
            )
            write_band_out(root / "dataset" / "band_out", nkpoints=2)

            report = validate_case(
                root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(report, "dataset.coulomb_q").status, "FAIL")

    def test_bz_sampling_and_band_out_kpoint_counts_must_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            write_band_out(root / "dataset" / "band_out", nkpoints=2)

            report = validate_case(
                root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(report, "dataset.kpoints").status, "FAIL")

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

    def test_full_coulomb_exx_requires_an_explicit_definition_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            path = root / "librpa.in"
            path.write_text(
                path.read_text(encoding="utf-8") + "use_fullcoul_exx = t\n",
                encoding="utf-8",
            )

            report = validate_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                stage="input",
            )

        gate = self.gate(report, "librpa.fullcoul_exx")
        self.assertEqual(gate.status, "WARN")
        self.assertTrue(report.accepted)
        self.assertIn("definition-matched", gate.repair)

    def test_invalid_full_coulomb_exx_switch_fails_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            path = root / "librpa.in"
            path.write_text(
                path.read_text(encoding="utf-8") + "use_fullcoul_exx = maybe\n",
                encoding="utf-8",
            )

            report = validate_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                stage="input",
            )

        gate = self.gate(report, "librpa.fullcoul_exx")
        self.assertEqual(gate.status, "FAIL")
        self.assertFalse(report.accepted)

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

    def test_headwing_policy_depends_on_task_and_system_type(self):
        with tempfile.TemporaryDirectory() as periodic_tmp, tempfile.TemporaryDirectory() as molecular_tmp:
            periodic = pathlib.Path(periodic_tmp)
            molecular = pathlib.Path(molecular_tmp)
            self.make_case(periodic, use_symmetry=False, headwing=False)
            self.make_case(molecular, use_symmetry=False, headwing=True)

            periodic_report = validate_case(
                periodic,
                task="gw",
                system_type="solid",
                use_symmetry=False,
            )
            molecular_report = validate_case(
                molecular,
                task="gw",
                system_type="molecule",
                use_symmetry=False,
            )

        self.assertEqual(self.gate(periodic_report, "pyatb.policy").status, "FAIL")
        self.assertEqual(self.gate(molecular_report, "pyatb.policy").status, "FAIL")

    def test_periodic_headwing_off_is_valid_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root, use_symmetry=True, headwing=False)

            report = validate_case(
                root,
                task="gw",
                system_type="solid",
                use_symmetry=True,
                headwing=False,
                stage="input",
            )

        self.assertTrue(report.accepted, report.to_dict())
        self.assertEqual(self.gate(report, "pyatb.policy").status, "PASS")

    def test_molecular_route_rejects_spatial_symmetry_even_if_inputs_match_request(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root, use_symmetry=True, headwing=False)

            report = validate_case(
                root,
                task="gw",
                system_type="molecule",
                use_symmetry=True,
            )

        self.assertEqual(self.gate(report, "route.policy").status, "FAIL")

    def test_strict_2d_validation_reports_the_pinned_version_block(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root, use_symmetry=True, headwing=True)

            report = validate_case(
                root,
                task="gw",
                system_type="2d",
                use_symmetry=True,
                stage="input",
            )

        gate = self.gate(report, "route.strict_2d_capability")
        self.assertEqual(gate.status, "FAIL")
        self.assertIn("LIBRPA_070_STRICT_2D_INVALID", gate.evidence)
        self.assertIn("dd169fa11fa920d580d4f39dc11e218a7f17f7b5", gate.evidence)

    def test_symmetry_route_requires_positive_row_convention_operations(self):
        with tempfile.TemporaryDirectory() as zero_tmp, tempfile.TemporaryDirectory() as col_tmp:
            zero = pathlib.Path(zero_tmp)
            col = pathlib.Path(col_tmp)
            self.make_case(zero)
            self.make_case(col)
            (zero / "dataset" / "stru_out").write_text(
                STRU_OUT_BASE + "0 row\n", encoding="utf-8"
            )
            (col / "dataset" / "stru_out").write_text(
                STRU_OUT_BASE + "1 col\n1 0 0 0 1 0 0 0 1 0 0 0\n",
                encoding="utf-8",
            )

            zero_report = validate_case(
                zero, task="gw", system_type="solid", use_symmetry=True
            )
            col_report = validate_case(
                col, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(zero_report, "symmetry.stru_out").status, "FAIL")
        self.assertEqual(self.gate(col_report, "symmetry.stru_out").status, "FAIL")

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
            (root / "dataset" / "pyatb_librpa_df" / "velocity_matrix").unlink()
            report = validate_case(root, task="gw", system_type="solid", use_symmetry=True)

        self.assertFalse(report.accepted)
        self.assertEqual(self.gate(report, "pyatb.velocity").status, "FAIL")

    def test_pyatb_full_grid_and_mean_field_dimensions_must_match(self):
        with tempfile.TemporaryDirectory() as grid_tmp, tempfile.TemporaryDirectory() as dims_tmp:
            grid_root = pathlib.Path(grid_tmp)
            dims_root = pathlib.Path(dims_tmp)
            self.make_case(grid_root)
            self.make_case(dims_root)
            write_headwing_metadata(grid_root / "dataset" / "pyatb_librpa_df", nkpoints=2)
            write_eigenvector_v1(
                grid_root / "dataset" / "pyatb_librpa_df" / "KS_eigenvector_0.dat",
                nkpoints=2,
            )
            write_velocity_v1(
                grid_root / "dataset" / "pyatb_librpa_df" / "velocity_matrix",
                nkpoints=2,
            )
            write_band_out(dims_root / "dataset" / "band_out")
            band = dims_root / "dataset" / "band_out"
            band.write_text(
                band.read_text(encoding="utf-8").replace("\n3\n2\n", "\n3\n4\n", 1),
                encoding="utf-8",
            )

            grid_report = validate_case(
                grid_root, task="gw", system_type="solid", use_symmetry=True
            )
            dims_report = validate_case(
                dims_root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(grid_report, "pyatb.alignment").status, "FAIL")
        self.assertEqual(self.gate(dims_report, "pyatb.alignment").status, "FAIL")

    def test_pyatb_states_must_equal_abacus_band_out(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            pyatb = root / "dataset" / "pyatb_librpa_df"
            write_headwing_metadata(pyatb, nkpoints=1)
            (pyatb / "k_path_info").write_text(
                "2 4 1 1\n0.0 0.0 0.0\n", encoding="utf-8"
            )
            write_eigenvector_v1(
                pyatb / "KS_eigenvector_0.dat", nkpoints=1, nstates=4, nbasis=2
            )
            write_velocity_v1(
                pyatb / "velocity_matrix", nkpoints=1, nbands=4, naos=2
            )
            blocks = ["1 1", *(f"{band} 0.0 0.0 0.0" for band in range(1, 5))]
            (pyatb / "band_out").write_text(
                "1\n1\n4\n2\n0.0\n" + "\n".join(blocks) + "\n",
                encoding="utf-8",
            )

            report = validate_case(
                root, task="gw", system_type="solid", use_symmetry=True
            )

        gate = self.gate(report, "pyatb.alignment")
        self.assertEqual(gate.status, "FAIL")
        self.assertIn("PyATB nstates=4 != band_out 3", gate.evidence)

    def test_pyatb_coordinates_use_librpa_periodic_unique_mapping(self):
        with tempfile.TemporaryDirectory() as valid_tmp, tempfile.TemporaryDirectory() as invalid_tmp:
            valid_root = pathlib.Path(valid_tmp)
            invalid_root = pathlib.Path(invalid_tmp)
            self.make_case(valid_root)
            self.make_case(invalid_root)
            (valid_root / "dataset" / "pyatb_librpa_df" / "k_path_info").write_text(
                "2 3 1 1\n1.0 0.0 0.0\n", encoding="utf-8"
            )
            (invalid_root / "dataset" / "pyatb_librpa_df" / "k_path_info").write_text(
                "2 3 1 1\n0.25 0.0 0.0\n", encoding="utf-8"
            )

            valid_report = validate_case(
                valid_root, task="gw", system_type="solid", use_symmetry=True
            )
            invalid_report = validate_case(
                invalid_root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(valid_report, "pyatb.alignment").status, "PASS")
        self.assertEqual(self.gate(invalid_report, "pyatb.alignment").status, "FAIL")

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
            for child in tuple((root / "dataset" / "pyatb_librpa_df").iterdir()):
                child.unlink()
            (root / "dataset" / "pyatb_librpa_df").rmdir()
            for child in tuple((root / "dataset").iterdir()):
                child.unlink()
            (root / "dataset").rmdir()
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

    def test_rpa_case_uses_rpa_symmetry_key_without_pyatb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root, task="rpa", headwing=False)
            (root / "dataset" / "v1_coulomb_cut_iq_1_rank0.dat").unlink()
            (root / "dataset" / "vxc_out").unlink()
            librpa = root / "librpa.in"
            librpa.write_text(
                "\n".join(
                    line
                    for line in librpa.read_text(encoding="utf-8").splitlines()
                    if not line.startswith(("prefix_coul_cut", "fn_vxc_scf"))
                )
                + "\n",
                encoding="utf-8",
            )
            report = validate_case(
                root,
                task="rpa",
                system_type="solid",
                use_symmetry=True,
            )

        self.assertTrue(report.accepted, report.to_dict())
        self.assertEqual(self.gate(report, "pyatb.headwing").status, "SKIP")
        self.assertEqual(self.gate(report, "gw.vxc").status, "SKIP")

    def test_gw_requires_cut_coulomb_family(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            (root / "dataset" / "v1_coulomb_cut_iq_1_rank0.dat").unlink()

            report = validate_case(
                root, task="gw", system_type="solid", use_symmetry=True
            )

        self.assertEqual(self.gate(report, "dataset.v1_prefixes").status, "FAIL")
        self.assertEqual(self.gate(report, "dataset.coulomb_q").status, "FAIL")


if __name__ == "__main__":
    unittest.main()
