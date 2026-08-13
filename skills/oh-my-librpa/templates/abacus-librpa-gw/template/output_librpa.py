import os
import struct

import numpy as np


KS_EIGENVECTOR_V1_MARKER = -12345679
KS_EIGENVECTOR_V1_KIND = 28
VELOCITY_MATRIX_V1_MARKER = -12345680
VELOCITY_MATRIX_V1_KIND = 29


def _write_indexed_complex_v1(path, header_fmt, header_values, k_num, block_iter):
    tmp_path = path + ".tmp"
    record_size = struct.calcsize("=iq")
    records = []
    try:
        with open(tmp_path, "wb") as f:
            f.write(struct.pack(header_fmt, *header_values))
            table_pos = f.tell()
            f.write(b"\0" * record_size * k_num)
            for ik, block in block_iter:
                records.append((ik, f.tell()))
                np.ascontiguousarray(block, dtype=np.complex128).tofile(f)
            if len(records) != k_num:
                raise ValueError("number of v1 k-point blocks does not match header")
            f.seek(table_pos)
            for ik, offset in records:
                f.write(struct.pack("=iq", int(ik), int(offset)))
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _iter_ks_eigenvector_blocks(
    eigenvectors, k_num, nspin, basis_num, nstates, use_soc, ik_offset=0
):
    if use_soc:
        if basis_num % 2 != 0:
            raise ValueError("SOC eigenvector basis size must be even")
        nspinor = 2
        n_basis_ao = basis_num // nspinor
        for ik in range(k_num):
            block = np.empty((1, nspinor, nstates, n_basis_ao), dtype=np.complex128)
            for isoc in range(nspinor):
                block[0, isoc, :, :] = np.asarray(
                    eigenvectors[0][ik, isoc::nspinor, :nstates], dtype=np.complex128
                ).T
            yield ik_offset + ik + 1, block
    else:
        for ik in range(k_num):
            block = np.empty((nspin, 1, nstates, basis_num), dtype=np.complex128)
            for ispin in range(nspin):
                block[ispin, 0, :, :] = np.asarray(
                    eigenvectors[ispin][ik, :, :nstates], dtype=np.complex128
                ).T
            yield ik_offset + ik + 1, block


def _write_ks_eigenvectors_v1(path, eigenvectors, k_num, nspin, basis_num, use_soc=False,
                              ik_offset=0, nstates=None):
    nstates = basis_num if nstates is None else nstates
    header_values = (
        KS_EIGENVECTOR_V1_MARKER,
        KS_EIGENVECTOR_V1_KIND,
        k_num,
        nspin,
        nstates,
        basis_num,
    )
    _write_indexed_complex_v1(
        path,
        "=6i",
        header_values,
        k_num,
        _iter_ks_eigenvector_blocks(
            eigenvectors, k_num, nspin, basis_num, nstates, use_soc, ik_offset
        ),
    )


def _iter_velocity_matrix_blocks(
    velocity_matrix, k_num, nspin, nstates, ik_offset=0
):
    for ik in range(k_num):
        block = np.empty((nspin, 3, nstates, nstates), dtype=np.complex128)
        for ispin in range(nspin):
            block[ispin, :, :, :] = np.asarray(
                velocity_matrix[ispin][ik, :, :nstates, :nstates], dtype=np.complex128
            )
        yield ik_offset + ik + 1, block


def _write_velocity_matrix_v1(
    path, velocity_matrix, k_num, nspin, basis_num, ik_offset=0, nstates=None
):
    nstates = basis_num if nstates is None else nstates
    header_values = (
        VELOCITY_MATRIX_V1_MARKER,
        VELOCITY_MATRIX_V1_KIND,
        k_num,
        nspin,
        nstates,
        basis_num,
        3,
    )
    _write_indexed_complex_v1(
        path,
        "=7i",
        header_values,
        k_num,
        _iter_velocity_matrix_blocks(velocity_matrix, k_num, nspin, nstates, ik_offset),
    )


def _write_velocity_matrix_legacy_text(path, velocity_matrix, k_num, nspin, basis_num):
    """Write the historical PyATB velocity text format for old LibRPA builds."""
    with open(path, "w") as f:
        f.write(str(k_num))
        f.write("\n")
        f.write(str(nspin))
        f.write("\n")
        f.write(str(basis_num))
        f.write("\n")
        f.write(str(basis_num))
        f.write("\n")
        for ispin in range(nspin):
            for ik in range(k_num):
                for ialpha in range(3):
                    f.write("%5d%5d%5d" % (ialpha + 1, ik + 1, ispin + 1))
                    f.write("\n")
                    matrix = np.asarray(velocity_matrix[ispin][ik, ialpha], dtype=np.complex128)
                    for iband in range(basis_num):
                        for ibasis in range(basis_num):
                            value = matrix[iband, ibasis]
                            f.write("%30.16E%30.16E" % (value.real, value.imag))
                            f.write("\n")


def _empty_spin_payload(nspin, basis_num):
    return (
        [np.empty((0, basis_num), dtype=float) for _ in range(nspin)],
        [np.empty((0, basis_num, basis_num), dtype=np.complex128) for _ in range(nspin)],
        [np.empty((0, 3, basis_num, basis_num), dtype=np.complex128) for _ in range(nspin)],
    )


def _merge_rank_payloads(payloads, nspin):
    payloads = sorted(
        [payload for payload in payloads if payload is not None and payload["k_num"] > 0],
        key=lambda payload: payload["ik_offset"],
    )
    if not payloads:
        raise ValueError("PyATB produced no k-point payloads")
    k_direct_coor = np.concatenate([payload["k_direct_coor"] for payload in payloads], axis=0)
    eigenvalues = [
        np.concatenate([payload["eigenvalues"][ispin] for payload in payloads], axis=0)
        for ispin in range(nspin)
    ]
    velocity_matrix = [
        np.concatenate([payload["velocity_matrix"][ispin] for payload in payloads], axis=0)
        for ispin in range(nspin)
    ]
    return k_direct_coor, eigenvalues, velocity_matrix


def output_librpa(lattice_vector: np.array, fermi_energy: float, occ_band: int,
                  nkx: int = 20, nky: int = 20, nkz: int = 20, nspin: int = 1,
                  matrix_route: str = "OUT.ABACUS", use_soc: bool = False,
                  nstates: int = None):
    import pyatb
    from pyatb import COMM, RANK, SIZE
    from pyatb.kpt.kpoint_generator import mp_generator, kpoints_in_different_process

    lattice_constant = 1.0
    if nspin == 2:
        HR_route = [
            os.path.join(matrix_route, "hrs1_nao.csr"),
            os.path.join(matrix_route, "hrs2_nao.csr"),
        ]
    elif nspin == 1 or nspin == 4:
        HR_route = os.path.join(matrix_route, "hrs1_nao.csr")
    else:
        raise ValueError("unsupported nspin for PyATB LibRPA output: {}".format(nspin))

    SR_route = os.path.join(matrix_route, "srs1_nao.csr")
    rR_route = os.path.join(matrix_route, "rr.csr")
    pR_route = os.path.join(matrix_route, "rr.csr")
    kpt_grid = np.array([nkx, nky, nkz], dtype=int)

    m_tb = pyatb.init_tb(
        package="ABACUS",
        nspin=nspin,
        lattice_constant=lattice_constant,
        lattice_vector=lattice_vector,
        max_kpoint_num=8000,
        isSparse=False,
        HR_route=HR_route,
        HR_unit="Ry",
        SR_route=SR_route,
        need_rR=True,
        rR_route=rR_route,
        rR_unit="Bohr",
        pR_route=pR_route,
        pR_unit="Ry",
        need_pR=True,
    )

    k_start = np.array([0.0, 0.0, 0.0], dtype=float)
    k_vect1 = np.array([1.0, 0.0, 0.0], dtype=float)
    k_vect2 = np.array([0.0, 1.0, 0.0], dtype=float)
    k_vect3 = np.array([0.0, 0.0, 1.0], dtype=float)
    kpt_generator = mp_generator(
        m_tb.max_kpoint_num, k_start, k_vect1, k_vect2, k_vect3, kpt_grid
    )

    COMM.Barrier()
    basis_num = m_tb.basis_num
    nstates = basis_num if nstates is None else int(nstates)
    if nstates <= 0 or nstates > basis_num:
        raise ValueError(
            "ABACUS band count must be positive and cannot exceed the PyATB AO basis size"
        )
    output_nspin = 1 if use_soc else nspin
    local_kpoints = []
    local_eigenvalues, local_eigenvectors, local_velocity = _empty_spin_payload(
        output_nspin, basis_num
    )

    eigenvalue_chunks = [[] for _ in range(output_nspin)]
    eigenvector_chunks = [[] for _ in range(output_nspin)]
    velocity_chunks = [[] for _ in range(output_nspin)]

    for kpt in kpt_generator:
        ik_process = kpoints_in_different_process(SIZE, RANK, kpt)
        k_direct_coor_local = ik_process.k_direct_coor_local
        k_num = k_direct_coor_local.shape[0]
        if not k_num:
            continue

        if nspin == 1 or nspin == 4:
            eigenvalues, eigenvectors, velocity_matrix = m_tb.tb_solver.get_velocity_matrix(
                k_direct_coor_local
            )
            eigenvalues = [eigenvalues]
            eigenvectors = [eigenvectors]
            velocity_matrix = [velocity_matrix]
        else:
            eigenvalues_up, eigenvectors_up, velocity_matrix_up = (
                m_tb.tb_solver_up.get_velocity_matrix(k_direct_coor_local)
            )
            eigenvalues_dn, eigenvectors_dn, velocity_matrix_dn = (
                m_tb.tb_solver_dn.get_velocity_matrix(k_direct_coor_local)
            )
            eigenvalues = [eigenvalues_up, eigenvalues_dn]
            eigenvectors = [eigenvectors_up, eigenvectors_dn]
            velocity_matrix = [velocity_matrix_up, velocity_matrix_dn]

        local_kpoints.append(k_direct_coor_local)
        for ispin in range(output_nspin):
            eigenvalue_chunks[ispin].append(np.asarray(eigenvalues[ispin]))
            eigenvector_chunks[ispin].append(np.asarray(eigenvectors[ispin]))
            velocity_chunks[ispin].append(np.asarray(velocity_matrix[ispin]))

    if local_kpoints:
        k_direct_coor_local = np.concatenate(local_kpoints, axis=0)
        local_k_num = k_direct_coor_local.shape[0]
        local_eigenvalues = [
            np.concatenate(eigenvalue_chunks[ispin], axis=0) for ispin in range(output_nspin)
        ]
        local_eigenvectors = [
            np.concatenate(eigenvector_chunks[ispin], axis=0) for ispin in range(output_nspin)
        ]
        local_velocity = [
            np.concatenate(velocity_chunks[ispin], axis=0) for ispin in range(output_nspin)
        ]
    else:
        k_direct_coor_local = np.empty((0, 3), dtype=float)
        local_k_num = 0

    k_counts = COMM.allgather(local_k_num)
    ik_offset = sum(k_counts[:RANK])

    if RANK == 0 and not os.path.exists("pyatb_librpa_df"):
        os.makedirs("pyatb_librpa_df")
    COMM.Barrier()

    if local_k_num:
        ks_name = "KS_eigenvector_0.dat" if SIZE == 1 else "KS_eigenvector_" + str(RANK) + ".dat"
        _write_ks_eigenvectors_v1(
            os.path.join("pyatb_librpa_df", ks_name),
            local_eigenvectors,
            local_k_num,
            output_nspin,
            basis_num,
            use_soc=use_soc,
            ik_offset=ik_offset,
            nstates=nstates,
        )

    payload = {
        "ik_offset": ik_offset,
        "k_num": local_k_num,
        "k_direct_coor": k_direct_coor_local,
        "eigenvalues": local_eigenvalues,
        "velocity_matrix": local_velocity,
    }
    payloads = COMM.gather(payload, root=0)

    HA2EV = 27.211386245988
    if RANK != 0:
        return

    k_direct_coor, eigenvalues, velocity_matrix = _merge_rank_payloads(payloads, output_nspin)
    k_num = k_direct_coor.shape[0]

    with open("pyatb_librpa_df/k_path_info", "w") as f:
        f.write("%8d%8d%8d%8d" % (basis_num, nstates, output_nspin, k_num))
        f.write("\n")
        for ik in range(k_num):
            f.write(
                "%30.16f%30.16f%30.16f"
                % (k_direct_coor[ik][0], k_direct_coor[ik][1], k_direct_coor[ik][2])
            )
            f.write("\n")

    with open("pyatb_librpa_df/band_out", "w") as f:
        f.write(str(k_num))
        f.write("\n")
        f.write(str(output_nspin))
        f.write("\n")
        f.write(str(nstates))
        f.write("\n")
        f.write(str(basis_num))
        f.write("\n")
        f.write("%.6f" % (fermi_energy / HA2EV))
        f.write("\n")
        for ik in range(k_num):
            for ispin in range(output_nspin):
                f.write("%3d%3d" % (ik + 1, ispin + 1))
                f.write("\n")
                for iband in range(nstates):
                    if iband < occ_band:
                        occ = 1.0 if (use_soc or output_nspin == 2) else 2.0
                    else:
                        occ = 0.0
                    eig_ev = eigenvalues[ispin][ik, iband]
                    f.write("%3d%13.8f%30.16E%18.8f" % (iband + 1, occ, eig_ev / HA2EV, eig_ev))
                    f.write("\n")

    _write_velocity_matrix_v1(
        "pyatb_librpa_df/velocity_matrix",
        velocity_matrix,
        k_num,
        output_nspin,
        basis_num,
        nstates=nstates,
    )
