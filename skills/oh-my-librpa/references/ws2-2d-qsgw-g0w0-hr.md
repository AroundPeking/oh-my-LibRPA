# WS2 2D: one-task G0W0 + QSGW with H(R) and Sigma(R, iw)

Validated on 2026-10-26 with LibRPA master_ghj plus the QSGW HR/GW ports
(cut semantics aligned with bhjia/master `052e11bd`) and ABACUS ef161
direct-2D head sidecar.

## Pipeline

1. Producer: ABACUS `abacus_ef161_direct2d_headsidecar` with
   `ABACUS_DIRECT_GSUM_COULOMB=1`, `ABACUS_DIRECT_GSUM_REPLACE_EWALD=1`,
   `ABACUS_DIRECT_GSUM_FULL_Q=1`, `ABACUS_DIRECT_GSUM_ECUT_RY=<ecut>`,
   `rpa=1`, `symmetry=1`, `out_mat_hs2=1`, `out_mat_r=1`, `out_mat_xc=1`,
   `out_librpa_reader_version=1`, `exx_ewald_dimension=2`.
   **Production mesh: KPT `12 12 1`** (the campaign standard; k10 was only the
   validation mesh). The archived database record ws2-table-gw used
   `20 20 1`, ecutwfc 120, nbands 88, exx_pca_threshold 1e-6; that k20
   comparison is optional and was cancelled. For the HR export nbands must
   equal n_AO (103 for this WS2 basis). A strained WS2 cell (about 1.7% in
   plane) aborted the special ABACUS binary at the 2D-Ewald/ABFS stage on
   both one and four nodes while the unstrained reference cell finished; the
   strained-cell producer must be validated (try removing
   `exx_ewald_tail_check enlarge` or adjusting `exx_pca_threshold`) before
   launching the 100-structure campaign.
2. Band NSCF on the 121-point Gamma-K-M-Gamma path with `calculation=nscf`,
   `init_chg=file`, same ecut/nbands, `out_wfc_lcao=1`, `out_band=1`,
   `out_mat_xc=1`, `symmetry=-1`; copy the producer
   `ABACUS-CHARGE-DENSITY.restart`. Run
   `preprocess_abacus_for_librpa_band.py` and
   `validate_ws2_band_source.py` (Gamma producer agreement and conduction
   step gates).
3. PyATB on the SCF grid: `get_diel.py` -> `output_librpa.py` (pyatb module)
   writes `pyatb_librpa_df/{KS_eigenvector_0.dat, velocity_matrix, band_out,
   k_path_info}`. Validate with `validate_ws2_pyatb_binary.py` and
   `validate_ws2_pyatb_against_producer.py` (`--k` = nkx*nky).
4. One LibRPA task: `task = qsgw` with `band_kpath_info` present. The driver
   auto-detects the band channel and runs grid and band channels in one
   execution.

## Required LibRPA input for the one-task run

```
task = qsgw
input_dir = ./input_librpa
output_dir = ./librpa.d
nfreq = 16
option_dielect_func = 3
replace_w_head = t
use_2d_dielectric = t
use_pyatb = t
parallel_routing = libri
use_scalars = t
use_cholesky_gw_wc = f
use_kpara_scf_eigvec = f      # critical: avoids the band-eigenvector double redistribution
qsgw_max_iter = 1
qsgw_output_qp = t
qsgw_export_hamiltonian_for_pyatb = t
qsgw_band0_cut_mode = 1       # shifted reference diagonal (scissor)
qsgw_band0_unoccupied_keep = 10
qsgw_band0_cut_shift_ha = 0.07349864435131   # 2 eV
prefix_vxc_band = <band_workdir>/OUT.ABACUS/vxc   # full band Vxc matrices
```

The band `input_dir` must contain both the producer data (band_out, basis,
v1_*, head, H/S/r, vxc, SYMROT) and the band-path data
(`band_kpath_info`, `band_KS_eigenvalue_k_*`, `band_KS_eigenvector_k_*`,
`band_vxc_k_*`). QSGW needs the full band Vxc matrices; the diagonal
`band_vxc_k_*.txt` tables are not enough.

## QSGW update and H(R)

The one-shot QSGW builds
`H_new = H_KS + Sigma_x + Sigma_c(iw -> eps_KS) - V_xc` in the fixed KS state
basis, applies the shifted cut to states outside occupied +
`unoccupied_keep` (reference diagonal + 2 eV, off-diagonals zero), mixes, and
diagonalizes. The band channel diagonalizes the same update at each path k,
so the QSGW band is smooth and is not the G0W0 eqp solution.

The HR exporter writes the actual post-cut operator:
`H(R) = H_native(R) + FFT^-1[D H_new D^dag - H_native]` with
`D = S C (C^dag S C)^-1` in the dual frame. On the symmetry-reduced SCF mesh
the correction is mapped onto the PyATB full-BZ reference by band index.
The full `expand_symmetry_meanfield` port is still open (S-metric residual
3450 on this basis).

## Acceptance gates

- PBE path gap vs the database (WS2: 1.799 vs 1.80171 eV).
- G0W0 eqp K gap from `qsgw_qp.csv` channel=band (WS2 k10 validation: 2.628 eV
  against the database 2.674 eV; the k20 comparison was cancelled and
  production uses k12).
- QSGW band: adjacent-k jump <= 0.5 eV (WS2 k10: max 0.416 eV).
- `QSGW_band_spin_1_1.dat`, `qsgw_qp.csv` (grid + band rows), 64
  `SigcRF_*`, `hrs1_nao_qsgw_iter_0001.csr`; HR native metric ~1e-12 and
  Fourier roundtrip < 1e-6 Ha.
- The H/Σ pair comes from the same run; do not mix H from one run with Σ from
  another.

## Pitfalls

- `use_kpara_scf_eigvec=t` corrupts the band EXX (Gamma band 1 -1876 eV
  against -39.86 eV on the grid). Use `f` for the band path. The driver now
  refuses the combination: with `use_symmetry_exx = t` it prints
  `Warning: use_symmetry_exx requires SCF eigenvectors replicated over all IBZ
  k-points; ignoring use_kpara_scf_eigvec = true` and runs as `f` (verified
  bit-identical on Si k444, max |t-f| = 0.0).
- Root cause of the `t` deviation, measured on Fisherd Si k444: it is not a
  parallelism problem. The same 9.36 eV band-EXX difference appears with
  `-np 1` and with 8 ranks (auto shape 8 k-groups x 1 BLACS), so the k-group
  split of the density matrix is not the cause. With the k-star restore
  disabled, both density-matrix builders (`build_dmat_libri_kblacs_para` for
  `t`, `build_dmat_libri_kserial` for `f`) produce bit-identical blocks
  (|D|^2 1.221287785769e+01, 256 keys). With the restore enabled they differ
  on all 64 R blocks (|D|^2 1.6629 for `t` against 1.7854 for `f`, ratio 0.93),
  i.e. the two implementations of the symmetry-restored density matrix
  (`get_symmetry_restored_dmat_cplx_Rs_kblacs_para` against
  `get_symmetry_restored_dmat_cplx_R`) disagree. Forcing the serial density
  builder while keeping `use_kpara_scf_eigvec = t` (even with the k-local
  rotation still active) reproduces the `f` band EXX exactly
  (max |dEXX| = 0.0), while forcing the dense rotation with the k-parallel
  density builder does not. The archived TiS3 record does run `t` together
  with symmetry, so the k-star restore there was accepted as-is; treat the
  Si k444 numbers as evidence that the two restore implementations are not
  interchangeable rather than as proof that `t` is unusable.
- `qsgw_band0_cut_mode` mapping: mode 1 is the shifted cut, mode 2 is rejected
  by the developer master; the shift is in Ha (`2 eV = 0.07349864435131`).
- `prefix_vxc_band` must point at the band OUT.ABACUS `vxc` prefix; otherwise
  the run fails on `band_vxck1_nao.txt`.
- The H(R) file support grows with the full-BZ mesh (121 R blocks at k10,
  400 at k20); the file is larger but the writer is the same.
- One-node k20 producer at 300 GB OOM-kills; use four nodes or lower
  `exx_pca_threshold`.
- Do not stage the producer in `/ssd/work/.../full_producer/<case>`: with the
  same INPUT/STRU/assets the run aborts at the 2D-Ewald/ABFS stage (empty
  mpiexec abort) on several nodes, while the identical case under
  `/data/home/.../batch_k12/<case>` completes (SCF converged, full_q=19
  cut_q=57 at k12). Stage production under `/data/home`.
- The producer script's `grep 'finish time'` check can false-negative on the
  direct-2D run even though `OUT.ABACUS/running_scf.log` says
  `#SCF IS CONVERGED#`; verify the required output files and write
  `PRODUCER_OK` from those counts.
