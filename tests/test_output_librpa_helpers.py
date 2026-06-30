import importlib.util
import pathlib
import struct
import tempfile
import unittest

import numpy as np


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "templates/abacus-librpa-gw/template/output_librpa.py"


def load_output_librpa_module():
    spec = importlib.util.spec_from_file_location("output_librpa", SCRIPT_PATH)
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


if __name__ == "__main__":
    unittest.main()
