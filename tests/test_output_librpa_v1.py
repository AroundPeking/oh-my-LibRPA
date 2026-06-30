#!/usr/bin/env python3

import importlib.util
import struct
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIBRPA = ROOT / "templates/abacus-librpa-gw/template/output_librpa.py"


def load_output_librpa():
    spec = importlib.util.spec_from_file_location("output_librpa", OUTPUT_LIBRPA)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_indexed_complex(path, header_fmt, payload_shape):
    with path.open("rb") as f:
        header_size = struct.calcsize(header_fmt)
        header = struct.unpack(header_fmt, f.read(header_size))
        records = [struct.unpack("=iq", f.read(struct.calcsize("=iq")))
                   for _ in range(header[2])]
        payloads = []
        for _, offset in records:
            f.seek(offset)
            count = int(np.prod(payload_shape))
            payloads.append(np.fromfile(f, dtype=np.complex128, count=count).reshape(payload_shape))
    return header, records, payloads


def test_ks_eigenvector_v1_nspin2(module):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "KS_eigenvector_0.dat"
        k_num = 2
        nspin = 2
        basis_num = 3
        eigenvectors = []
        for ispin in range(nspin):
            arr = np.empty((k_num, basis_num, basis_num), dtype=np.complex128)
            for ik in range(k_num):
                for ibasis in range(basis_num):
                    for iband in range(basis_num):
                        value = 1000 * ispin + 100 * ik + 10 * ibasis + iband
                        arr[ik, ibasis, iband] = value + 1j * (value + 0.5)
            eigenvectors.append(arr)

        module._write_ks_eigenvectors_v1(str(out), eigenvectors, k_num, nspin, basis_num)
        header, records, payloads = read_indexed_complex(out, "=6i",
                                                         (nspin, 1, basis_num, basis_num))

        assert header == (
            module.KS_EIGENVECTOR_V1_MARKER,
            module.KS_EIGENVECTOR_V1_KIND,
            k_num,
            nspin,
            basis_num,
            basis_num,
        )
        assert [record[0] for record in records] == [1, 2]
        for ispin in range(nspin):
            for ibasis in range(basis_num):
                for iband in range(basis_num):
                    assert payloads[0][ispin, 0, iband, ibasis] == eigenvectors[ispin][
                        0, ibasis, iband
                    ]


def test_ks_eigenvector_v1_soc_spinor_split(module):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "KS_eigenvector_0.dat"
        k_num = 1
        basis_num = 4
        eigenvectors = [np.empty((k_num, basis_num, basis_num), dtype=np.complex128)]
        for ibasis in range(basis_num):
            for iband in range(basis_num):
                value = 10 * ibasis + iband
                eigenvectors[0][0, ibasis, iband] = value + 1j * (value + 0.25)

        module._write_ks_eigenvectors_v1(
            str(out), eigenvectors, k_num, 1, basis_num, use_soc=True
        )
        header, _, payloads = read_indexed_complex(out, "=6i", (1, 2, basis_num, 2))

        assert header[0:4] == (
            module.KS_EIGENVECTOR_V1_MARKER,
            module.KS_EIGENVECTOR_V1_KIND,
            k_num,
            1,
        )
        for isoc in range(2):
            for iao in range(2):
                for iband in range(basis_num):
                    assert payloads[0][0, isoc, iband, iao] == eigenvectors[0][
                        0, iao * 2 + isoc, iband
                    ]


def test_velocity_matrix_v1(module):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "velocity_matrix"
        k_num = 2
        nspin = 2
        n_bands = 3
        velocity = []
        for ispin in range(nspin):
            arr = np.empty((k_num, 3, n_bands, n_bands), dtype=np.complex128)
            for ik in range(k_num):
                for ialpha in range(3):
                    for i in range(n_bands):
                        for j in range(n_bands):
                            value = 1000 * ispin + 100 * ik + 10 * ialpha + 3 * i + j
                            arr[ik, ialpha, i, j] = value - 1j * (value + 0.75)
            velocity.append(arr)

        module._write_velocity_matrix_v1(str(out), velocity, k_num, nspin, n_bands, n_bands,
                                         ik_offset=4)
        header, records, payloads = read_indexed_complex(out, "=7i",
                                                         (nspin, 3, n_bands, n_bands))

        assert header == (
            module.VELOCITY_MATRIX_V1_MARKER,
            module.VELOCITY_MATRIX_V1_KIND,
            k_num,
            nspin,
            n_bands,
            n_bands,
            3,
        )
        assert [record[0] for record in records] == [5, 6]
        for ispin in range(nspin):
            np.testing.assert_array_equal(payloads[1][ispin], velocity[ispin][1])


if __name__ == "__main__":
    module = load_output_librpa()
    test_ks_eigenvector_v1_nspin2(module)
    test_ks_eigenvector_v1_soc_spinor_split(module)
    test_velocity_matrix_v1(module)
