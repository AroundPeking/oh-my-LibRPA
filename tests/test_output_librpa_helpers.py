import importlib.util
import pathlib
import struct
import tempfile
import unittest

import numpy as np


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "templates/abacus-librpa-gw/template/output_librpa.py"
GET_DIEL_PATH = REPO_ROOT / "templates/abacus-librpa-gw/template/get_diel.py"


def load_output_librpa_module():
    spec = importlib.util.spec_from_file_location("output_librpa", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_get_diel_module():
    spec = importlib.util.spec_from_file_location("get_diel", GET_DIEL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OutputLibrpaHelperTest(unittest.TestCase):
    def test_ks_eigenvectors_are_written_as_reader_v1_binary(self):
        module = load_output_librpa_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "KS_eigenvector_0.dat"
            eigenvectors = [np.eye(2, dtype=np.complex128).reshape(1, 2, 2)]

            module._write_ks_eigenvectors_v1(
                str(path),
                eigenvectors=eigenvectors,
                k_num=1,
                nspin=1,
                basis_num=2,
                use_soc=False,
            )

            data = path.read_bytes()
            self.assertEqual(struct.unpack("=6i", data[:24]), (-12345679, 28, 1, 1, 2, 2))
            self.assertEqual(struct.unpack("=iq", data[24:36]), (1, 36))
            payload = np.frombuffer(data[36:], dtype=np.complex128)
            self.assertEqual(payload.size, 4)
            self.assertTrue(np.allclose(payload.reshape(1, 1, 2, 2)[0, 0], np.eye(2)))

    def test_velocity_matrix_is_written_as_reader_v1_binary(self):
        module = load_output_librpa_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "velocity_matrix"
            velocity = [np.arange(12, dtype=float).reshape(1, 3, 2, 2).astype(np.complex128)]

            module._write_velocity_matrix_v1(
                str(path),
                velocity_matrix=velocity,
                k_num=1,
                nspin=1,
                basis_num=2,
            )

            data = path.read_bytes()
            self.assertEqual(struct.unpack("=7i", data[:28]), (-12345680, 29, 1, 1, 2, 2, 3))
            self.assertEqual(struct.unpack("=iq", data[28:40]), (1, 40))
            payload = np.frombuffer(data[40:], dtype=np.complex128)
            self.assertEqual(payload.size, 12)
            self.assertTrue(np.allclose(payload.reshape(1, 3, 2, 2), velocity[0][0]))

    def test_reader_v1_writers_truncate_states_but_keep_ao_basis_dimension(self):
        module = load_output_librpa_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            eigen_path = root / "KS_eigenvector_0.dat"
            velocity_path = root / "velocity_matrix"
            eigenvectors = [
                np.arange(9, dtype=float).reshape(1, 3, 3).astype(np.complex128)
            ]
            velocity = [
                np.arange(27, dtype=float).reshape(1, 3, 3, 3).astype(np.complex128)
            ]

            module._write_ks_eigenvectors_v1(
                str(eigen_path),
                eigenvectors=eigenvectors,
                k_num=1,
                nspin=1,
                basis_num=3,
                nstates=2,
                use_soc=False,
            )
            module._write_velocity_matrix_v1(
                str(velocity_path),
                velocity_matrix=velocity,
                k_num=1,
                nspin=1,
                basis_num=3,
                nstates=2,
            )

            eigen_data = eigen_path.read_bytes()
            velocity_data = velocity_path.read_bytes()

        self.assertEqual(
            struct.unpack("=6i", eigen_data[:24]), (-12345679, 28, 1, 1, 2, 3)
        )
        eigen_payload = np.frombuffer(eigen_data[36:], dtype=np.complex128)
        self.assertEqual(eigen_payload.size, 6)
        self.assertTrue(
            np.allclose(eigen_payload.reshape(1, 1, 2, 3)[0, 0], eigenvectors[0][0, :, :2].T)
        )
        self.assertEqual(
            struct.unpack("=7i", velocity_data[:28]), (-12345680, 29, 1, 1, 2, 3, 3)
        )
        velocity_payload = np.frombuffer(velocity_data[40:], dtype=np.complex128)
        self.assertEqual(velocity_payload.size, 12)
        self.assertTrue(
            np.allclose(velocity_payload.reshape(1, 3, 2, 2), velocity[0][0, :, :2, :2])
        )

    def test_get_param_returns_abacus_band_count(self):
        module = load_get_diel_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "OUT.ABACUS").mkdir()
            (root / "STRU").write_text(
                "LATTICE_VECTORS\n1 0 0\n0 1 0\n0 0 1\n", encoding="utf-8"
            )
            (root / "OUT.ABACUS" / "running_scf.log").write_text(
                "E_FERMI 1.25\n", encoding="utf-8"
            )
            (root / "band_out").write_text(
                "1\n1\n2\n3\n0.0\n1 1\n"
                "1 2.0 -0.5 -13.6\n2 0.0 0.2 5.4\n",
                encoding="utf-8",
            )

            lattice, fermi, occupied, nstates = module.get_param(str(root))

        self.assertEqual(lattice, [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        self.assertEqual(fermi, 1.25)
        self.assertEqual(occupied, 1)
        self.assertEqual(nstates, 2)


if __name__ == "__main__":
    unittest.main()
