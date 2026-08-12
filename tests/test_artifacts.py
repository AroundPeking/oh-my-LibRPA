import pathlib
import struct
import tempfile
import unittest


from oml_mcp.artifacts import (
    inspect_eigenvector_v1,
    inspect_headwing_directory,
    inspect_stru_out,
    inspect_velocity_v1,
)


def write_eigenvector_v1(
    path: pathlib.Path,
    *,
    nkpoints: int = 2,
    nspin: int = 1,
    nstates: int = 3,
    nbasis: int = 2,
    indices: tuple[int, ...] | None = None,
    truncate: int = 0,
) -> None:
    indices = indices or tuple(range(1, nkpoints + 1))
    header_size = 24 + 12 * nkpoints
    block_size = nspin * nstates * nbasis * 16
    table = b"".join(
        struct.pack("=iq", index, header_size + block * block_size)
        for block, index in enumerate(indices)
    )
    data = struct.pack("=6i", -12345679, 28, nkpoints, nspin, nstates, nbasis)
    data += table + bytes(block_size * nkpoints)
    path.write_bytes(data[:-truncate] if truncate else data)


def write_velocity_v1(
    path: pathlib.Path,
    *,
    nkpoints: int = 2,
    nspin: int = 1,
    nbands: int = 3,
    naos: int = 2,
    nalpha: int = 3,
    marker: int = -12345680,
    indices: tuple[int, ...] | None = None,
    truncate: int = 0,
) -> None:
    indices = indices or tuple(range(1, nkpoints + 1))
    header_size = 28 + 12 * nkpoints
    block_size = nspin * nalpha * nbands * nbands * 16
    table = b"".join(
        struct.pack("=iq", index, header_size + block * block_size)
        for block, index in enumerate(indices)
    )
    data = struct.pack("=7i", marker, 29, nkpoints, nspin, nbands, naos, nalpha)
    data += table + bytes(block_size * nkpoints)
    path.write_bytes(data[:-truncate] if truncate else data)


def write_headwing_metadata(root: pathlib.Path, *, nkpoints: int = 2) -> None:
    rows = "\n".join(f"{index / 2:.1f} 0.0 0.0" for index in range(nkpoints))
    (root / "k_path_info").write_text(f"2 3 1 {nkpoints}\n{rows}\n", encoding="utf-8")
    blocks = []
    for ik in range(1, nkpoints + 1):
        blocks.append(f"{ik} 1")
        blocks.extend(f"{band} 0.0 0.0 0.0" for band in range(1, 4))
    (root / "band_out").write_text(
        f"{nkpoints}\n1\n3\n2\n0.0\n" + "\n".join(blocks) + "\n",
        encoding="utf-8",
    )


class ReaderV1ArtifactTest(unittest.TestCase):
    def test_valid_eigenvector_header_and_payload_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "KS_eigenvector_0.dat"
            write_eigenvector_v1(path)
            info = inspect_eigenvector_v1(path)

        self.assertTrue(info.accepted)
        self.assertEqual(info.format_version, "v1")
        self.assertEqual(info.metadata["k_indices"], (1, 2))
        self.assertEqual(info.metadata["nstates"], 3)

    def test_empty_reader_v1_splits_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            eigenvector = root / "KS_eigenvector_empty.dat"
            velocity = root / "velocity_matrix_empty.dat"
            write_eigenvector_v1(eigenvector, nkpoints=0)
            write_velocity_v1(velocity, nkpoints=0)

            eigenvector_info = inspect_eigenvector_v1(eigenvector)
            velocity_info = inspect_velocity_v1(velocity)

        self.assertTrue(eigenvector_info.accepted)
        self.assertTrue(velocity_info.accepted)
        self.assertEqual(eigenvector_info.metadata["k_indices"], ())
        self.assertEqual(velocity_info.metadata["k_indices"], ())

    def test_truncated_eigenvector_payload_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "KS_eigenvector_0.dat"
            write_eigenvector_v1(path, truncate=16)
            info = inspect_eigenvector_v1(path)

        self.assertFalse(info.accepted)
        self.assertIn("payload", info.gates[0].message)

    def test_duplicate_eigenvector_k_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "KS_eigenvector_0.dat"
            write_eigenvector_v1(path, indices=(1, 1))
            info = inspect_eigenvector_v1(path)

        self.assertFalse(info.accepted)
        self.assertIn("unique", info.gates[0].message)

    def test_overlapping_eigenvector_payloads_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "KS_eigenvector_0.dat"
            write_eigenvector_v1(path)
            data = bytearray(path.read_bytes())
            first_offset = struct.unpack_from("=q", data, 24 + 4)[0]
            struct.pack_into("=q", data, 24 + 12 + 4, first_offset)
            path.write_bytes(data)

            info = inspect_eigenvector_v1(path)

        self.assertFalse(info.accepted)
        self.assertIn("overlap", info.gates[0].message)

    def test_valid_velocity_header_and_payload_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "velocity_matrix"
            write_velocity_v1(path)
            info = inspect_velocity_v1(path)

        self.assertTrue(info.accepted)
        self.assertEqual(info.metadata["nalpha"], 3)
        self.assertEqual(info.metadata["k_indices"], (1, 2))

    def test_wrong_velocity_marker_and_nalpha_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            marker_path = root / "velocity_matrix"
            alpha_path = root / "velocity_matrix_1.dat"
            write_velocity_v1(marker_path, marker=-7)
            write_velocity_v1(alpha_path, nalpha=2)

            marker_info = inspect_velocity_v1(marker_path)
            alpha_info = inspect_velocity_v1(alpha_path)

        self.assertFalse(marker_info.accepted)
        self.assertFalse(alpha_info.accepted)

    def test_headwing_directory_cross_checks_all_dimensions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_headwing_metadata(root)
            write_eigenvector_v1(root / "KS_eigenvector_0.dat")
            write_velocity_v1(root / "velocity_matrix")

            report = inspect_headwing_directory(root)

        self.assertTrue(report.accepted)
        self.assertEqual(report.artifact_type, "pyatb_headwing_directory")
        self.assertEqual(report.metadata["nkpoints"], 2)

    def test_headwing_dimension_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_headwing_metadata(root)
            write_eigenvector_v1(root / "KS_eigenvector_0.dat", nstates=4)
            write_velocity_v1(root / "velocity_matrix")

            report = inspect_headwing_directory(root)

        self.assertFalse(report.accepted)
        self.assertTrue(any("dimensions" in gate.message for gate in report.gates))

    def test_truncated_headwing_band_out_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_headwing_metadata(root)
            band = root / "band_out"
            band.write_text("\n".join(band.read_text(encoding="utf-8").splitlines()[:-1]))
            write_eigenvector_v1(root / "KS_eigenvector_0.dat")
            write_velocity_v1(root / "velocity_matrix")

            report = inspect_headwing_directory(root)

        self.assertFalse(report.accepted)
        self.assertEqual(report.gates[0].gate_id, "pyatb.metadata")

    def test_headwing_duplicate_kpoint_across_split_files_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_headwing_metadata(root)
            write_eigenvector_v1(root / "KS_eigenvector_0.dat", nkpoints=1, indices=(1,))
            write_eigenvector_v1(root / "KS_eigenvector_1.dat", nkpoints=2, indices=(1, 2))
            write_velocity_v1(root / "velocity_matrix")

            report = inspect_headwing_directory(root)

        self.assertFalse(report.accepted)
        duplicate_gate = next(
            gate for gate in report.gates if gate.gate_id == "pyatb.duplicates.eigenvector"
        )
        self.assertEqual(duplicate_gate.status, "FAIL")

    def test_headwing_requires_exact_velocity_root_and_ignores_dot_backup(self):
        with tempfile.TemporaryDirectory() as missing_tmp, tempfile.TemporaryDirectory() as backup_tmp:
            missing_root = pathlib.Path(missing_tmp)
            backup_root = pathlib.Path(backup_tmp)
            for root in (missing_root, backup_root):
                write_headwing_metadata(root)
                write_eigenvector_v1(root / "KS_eigenvector_0.dat")
            write_velocity_v1(missing_root / "velocity_matrix_0")
            write_velocity_v1(backup_root / "velocity_matrix")
            (backup_root / "velocity_matrix.backup").write_text("not a v1 split\n", encoding="utf-8")

            missing_report = inspect_headwing_directory(missing_root)
            backup_report = inspect_headwing_directory(backup_root)

        self.assertFalse(missing_report.accepted)
        self.assertTrue(backup_report.accepted, backup_report.to_dict())


class StruOutArtifactTest(unittest.TestCase):
    BASE = """1 0 0
0 1 0
0 0 1
6.283185307 0 0
0 6.283185307 0
0 0 6.283185307
1
0 0 0 1
"""

    def inspect_text(self, text: str):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "stru_out"
            path.write_text(text, encoding="utf-8")
            return inspect_stru_out(path)

    def test_structure_without_symmetry_tail_is_valid(self):
        info = self.inspect_text(self.BASE)
        self.assertTrue(info.accepted)
        self.assertFalse(info.metadata["has_symmetry"])

    def test_valid_row_symmetry_tail_is_parsed(self):
        info = self.inspect_text(self.BASE + "1 row\n1 0 0 0 1 0 0 0 1 0.0 0.0 0.0\n")
        self.assertTrue(info.accepted)
        self.assertTrue(info.metadata["has_symmetry"])
        self.assertEqual(info.metadata["n_symops"], 1)
        self.assertEqual(info.metadata["convention"], "row")

    def test_zero_symmetry_operations_do_not_count_as_symmetry(self):
        info = self.inspect_text(self.BASE + "0 row\n")
        self.assertTrue(info.accepted)
        self.assertFalse(info.metadata["has_symmetry"])

    def test_non_unimodular_symmetry_rotation_is_rejected(self):
        info = self.inspect_text(self.BASE + "1 row\n2 0 0 0 1 0 0 0 1 0.0 0.0 0.0\n")
        self.assertFalse(info.accepted)
        self.assertIn("determinant", info.gates[0].message)

    def test_truncated_symmetry_operation_is_rejected(self):
        info = self.inspect_text(self.BASE + "1 row\n1 0 0\n")
        self.assertFalse(info.accepted)

    def test_non_integer_rotation_and_trailing_tokens_are_rejected(self):
        non_integer = self.inspect_text(
            self.BASE + "1 row\n1.5 0 0 0 1 0 0 0 1 0.0 0.0 0.0\n"
        )
        trailing = self.inspect_text(
            self.BASE + "1 row\n1 0 0 0 1 0 0 0 1 0.0 0.0 0.0 extra\n"
        )
        self.assertFalse(non_integer.accepted)
        self.assertFalse(trailing.accepted)

    def test_nonfinite_structure_values_are_rejected(self):
        lattice = self.inspect_text(self.BASE.replace("1 0 0", "nan 0 0", 1))
        translation = self.inspect_text(
            self.BASE + "1 row\n1 0 0 0 1 0 0 0 1 inf 0.0 0.0\n"
        )

        self.assertFalse(lattice.accepted)
        self.assertFalse(translation.accepted)


if __name__ == "__main__":
    unittest.main()
