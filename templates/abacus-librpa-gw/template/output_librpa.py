import numpy as np
import sys
import os
import struct

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


def _iter_ks_eigenvector_blocks(eigenvectors, k_num, nspin, basis_num, use_soc, ik_offset=0):
    if use_soc:
        if basis_num % 2 != 0:
            raise ValueError("SOC eigenvector basis size must be even")
        nspinor = 2
        n_basis_ao = basis_num // nspinor
        for ik in range(k_num):
            block = np.empty((1, nspinor, basis_num, n_basis_ao), dtype=np.complex128)
            for isoc in range(nspinor):
                block[0, isoc, :, :] = np.asarray(
                    eigenvectors[0][ik, isoc::nspinor, :], dtype=np.complex128
                ).T
            yield ik_offset + ik + 1, block
    else:
        for ik in range(k_num):
            block = np.empty((nspin, 1, basis_num, basis_num), dtype=np.complex128)
            for ispin in range(nspin):
                block[ispin, 0, :, :] = np.asarray(
                    eigenvectors[ispin][ik, :, :], dtype=np.complex128
                ).T
            yield ik_offset + ik + 1, block


def _write_ks_eigenvectors_v1(path, eigenvectors, k_num, nspin, basis_num, use_soc=False,
                              ik_offset=0):
    header_values = (
        KS_EIGENVECTOR_V1_MARKER,
        KS_EIGENVECTOR_V1_KIND,
        k_num,
        nspin,
        basis_num,
        basis_num,
    )
    _write_indexed_complex_v1(
        path,
        "=6i",
        header_values,
        k_num,
        _iter_ks_eigenvector_blocks(eigenvectors, k_num, nspin, basis_num, use_soc, ik_offset),
    )


def _iter_velocity_blocks(velocity_matrix, k_num, nspin, ik_offset=0):
    for ik in range(k_num):
        block = np.empty(
            (nspin, 3, velocity_matrix[0].shape[2], velocity_matrix[0].shape[3]),
            dtype=np.complex128,
        )
        for ispin in range(nspin):
            block[ispin, :, :, :] = np.asarray(velocity_matrix[ispin][ik, :, :, :],
                                               dtype=np.complex128)
        yield ik_offset + ik + 1, block


def _write_velocity_matrix_v1(path, velocity_matrix, k_num, nspin, n_bands, n_aos, ik_offset=0):
    header_values = (
        VELOCITY_MATRIX_V1_MARKER,
        VELOCITY_MATRIX_V1_KIND,
        k_num,
        nspin,
        n_bands,
        n_aos,
        3,
    )
    _write_indexed_complex_v1(
        path,
        "=7i",
        header_values,
        k_num,
        _iter_velocity_blocks(velocity_matrix, k_num, nspin, ik_offset),
    )


def output_librpa(lattice_vector: np.array, fermi_energy: float, occ_band: int, nkx : int = 20, nky : int = 20, nkz : int = 20, nspin: int = 1, matrix_route: str = 'OUT.ABACUS', use_soc: bool = False):
    import pyatb
    from pyatb import RANK, COMM, SIZE
    from pyatb.kpt.kpoint_generator import mp_generator, kpoints_in_different_process
    from pyatb.parallel import op_sum
    from pyatb.tools.smearing import gauss

    """----------------输入数据----------------"""
    # 1. 晶格参数
    lattice_constant = 1.0
    # unit: \AA
    #lattice_vector = np.array(
    #    [
    #        [0.000000000000,  1.8,  1.8],
    #        [1.8,  0.000000000000,  1.8],
    #        [1.8,  1.8,  0.000000000000]
    #    ], dtype=float
    #)
    if(nspin==2):
        HR_route = [os.path.join(matrix_route, 'hrs1_nao.csr'), os.path.join(matrix_route, 'hrs2_nao.csr')]
    if(nspin==1 or nspin==4):
        HR_route = os.path.join(matrix_route, 'hrs1_nao.csr')
    SR_route = os.path.join(matrix_route, 'srs1_nao.csr')
    rR_route = os.path.join(matrix_route, 'rr.csr')
    pR_route = os.path.join(matrix_route, 'rr.csr')

    # 2. 设置参数
    #fermi_energy = 13.063197611 # eV
    #occ_band = 4
    #omega_range = [0, 100] # eV
    #domega = 1 # eV
    kpt_grid = np.array([nkx, nky, nkz], dtype=int)

    """--------创建tight binding model-------"""
    m_tb = pyatb.init_tb(
        package = 'ABACUS',
        nspin = nspin,
        lattice_constant = lattice_constant,
        lattice_vector = lattice_vector,
        max_kpoint_num = 8000,
        isSparse = False,
        HR_route = HR_route,
        HR_unit = 'Ry',
        SR_route = SR_route,
        need_rR = True,
        rR_route = rR_route,
        rR_unit = 'Bohr',
        pR_route = pR_route,
        pR_unit= "Ry",
        need_pR= True
    )

    """----------------设置k点----------------"""
    k_start = np.array([0.0, 0.0, 0.0], dtype=float)
    k_vect1 = np.array([1.0, 0.0, 0.0], dtype=float)
    k_vect2 = np.array([0.0, 1.0, 0.0], dtype=float)
    k_vect3 = np.array([0.0, 0.0, 1.0], dtype=float)
    grid = kpt_grid
    kpt_grid_num = grid[0] * grid[1] * grid[2]
    kpt_generator = mp_generator(m_tb.max_kpoint_num, k_start, k_vect1, k_vect2,  k_vect3, grid)
    COMM.Barrier()
    basis_num = m_tb.basis_num
    for kpt in kpt_generator:
        ik_process = kpoints_in_different_process(SIZE, RANK, kpt)
        k_direct_coor_local = ik_process.k_direct_coor_local
        k_num = k_direct_coor_local.shape[0]
        eigenvalues = []
        eigenvectors = []
        velocity_matrix = []

        if k_num:
            if(nspin==1 or nspin==4):
                eigenvalues, eigenvectors, velocity_matrix = m_tb.tb_solver.get_velocity_matrix(k_direct_coor_local)
                eigenvalues = [eigenvalues]
                eigenvectors = [eigenvectors]
                velocity_matrix = [velocity_matrix]
            if(nspin==2):
                eigenvalues_up, eigenvectors_up, velocity_matrix_up = m_tb.tb_solver_up.get_velocity_matrix(k_direct_coor_local)
                eigenvalues_dn, eigenvectors_dn, velocity_matrix_dn = m_tb.tb_solver_dn.get_velocity_matrix(k_direct_coor_local)
                eigenvalues = [eigenvalues_up, eigenvalues_dn]
                eigenvectors = [eigenvectors_up, eigenvectors_dn]
                velocity_matrix = [velocity_matrix_up, velocity_matrix_dn]
            #eigenvalues, pk_matrix = m_tb.tb_solver.get_pk_matrix(k_direct_coor_local)
            
    # 输出文件 only precision=16 for python float
    HA2EV = 27.211386245988
    if(use_soc):
        nspin = 1
    local_k_num = k_num
    k_counts = COMM.allgather(local_k_num)
    ik_offset = sum(k_counts[:RANK])
    if RANK == 0:
        if (not os.path.exists("pyatb_librpa_df")):
            os.makedirs("pyatb_librpa_df")
    COMM.Barrier()
    if local_k_num or RANK == 0:
        ks_name = "KS_eigenvector_0.dat" if SIZE == 1 else "KS_eigenvector_" + str(RANK) + ".dat"
        velocity_name = "velocity_matrix" if RANK == 0 else "velocity_matrix_" + str(RANK) + ".dat"
        _write_ks_eigenvectors_v1(
            os.path.join("pyatb_librpa_df", ks_name),
            eigenvectors,
            local_k_num,
            nspin,
            basis_num,
            use_soc=use_soc,
            ik_offset=ik_offset,
        )
        _write_velocity_matrix_v1(
            os.path.join("pyatb_librpa_df", velocity_name),
            velocity_matrix,
            local_k_num,
            nspin,
            basis_num,
            basis_num,
            ik_offset=ik_offset,
        )

    meta_payloads = COMM.gather((k_direct_coor_local, eigenvalues), root=0)
    if RANK == 0:
        meta_payloads = [payload for payload in meta_payloads if payload[0].shape[0] > 0]
        k_direct_coor_local = np.concatenate([payload[0] for payload in meta_payloads], axis=0)
        eigenvalues = [
            np.concatenate([payload[1][ispin] for payload in meta_payloads], axis=0)
            for ispin in range(nspin)
        ]
        k_num = k_direct_coor_local.shape[0]
        with open('pyatb_librpa_df/'+"k_path_info", 'w') as f:
            f.write("%8d%8d%8d%8d"%(basis_num,basis_num,nspin,k_num))
            f.write('\n')
            for ik in range(k_num):
                f.write("%30.16f%30.16f%30.16f"%(k_direct_coor_local[ik][0],k_direct_coor_local[ik][1],k_direct_coor_local[ik][2]))
                f.write('\n')
        
        with open('pyatb_librpa_df/'+"band_out", 'w') as f:
            f.write(str(k_num))
            f.write('\n')
            f.write(str(nspin))
            f.write('\n')
            f.write(str(basis_num))
            f.write('\n')
            f.write(str(basis_num))
            f.write('\n')
            f.write("%.6f"%(fermi_energy/HA2EV))
            f.write('\n')
            for ik in range(k_num):
                for ispin in range(nspin):
                    f.write("%3d%3d"%(ik+1,ispin+1))
                    f.write('\n')
                    for iband in range(basis_num):
                        if (iband < occ_band):
                            if(use_soc):
                                f.write("%3d%13.8f%30.16E%18.8f"%(iband+1,1.0,(eigenvalues[ispin][ik, iband]/HA2EV),eigenvalues[ispin][ik, iband]))
                            else:
                                if(nspin==2):
                                    f.write("%3d%13.8f%30.16E%18.8f"%(iband+1,1.0,(eigenvalues[ispin][ik, iband]/HA2EV),eigenvalues[ispin][ik, iband]))
                                else:
                                    f.write("%3d%13.8f%30.16E%18.8f"%(iband+1,2.0,(eigenvalues[ispin][ik, iband]/HA2EV),eigenvalues[ispin][ik, iband]))
                            f.write('\n')
                        else:
                            f.write("%3d%13.8f%30.16E%18.8f"%(iband+1,0.0,(eigenvalues[ispin][ik, iband]/HA2EV),eigenvalues[ispin][ik, iband]))
                            f.write('\n')
        #with open('pyatb_librpa_df/'+"momentum_matrix", 'w') as f:
        #    f.write(str(k_num))
        #    f.write('\n')
        #    f.write(str(basis_num))
        #    f.write('\n')
        #    f.write(str(basis_num))
        #    f.write('\n')
        #    for ik in range(k_num):
        #        for ialpha in range(3):
        #            f.write("%5d%5d"%(ialpha+1,ik+1))
        #            f.write('\n')
        #            for iband in range(basis_num):
        #                for ibasis in range(basis_num):
        #                    f.write("%30.16E%30.16E"%(pk_matrix[ik, ialpha, iband, ibasis].real, pk_matrix[ik, ialpha, iband, ibasis].imag))
        #                    f.write('\n')
            
