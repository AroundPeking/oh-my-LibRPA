# Molecular Delta-ST Parameter Contract

Use this as a template, not as a substitute for version-specific INPUT validation.

## ABACUS Response Keys

```text
symmetry                         -1
exx_singularity_correction        limits
sternheimer_molecular_coulomb     isolated_ri
sternheimer_ao_potential_file     ao_potentials.dat
out_sternheimer_librpa            1
sternheimer_grid_diagnostics      1
sternheimer_fd_order              8
sternheimer_nfreq                 <accepted nfreq>
sternheimer_frequency_grid_file   fixed_frequency_grid.dat
sternheimer_delta                 1
sternheimer_delta_virtual_source  ks_bands
sternheimer_delta_max_states      0
sternheimer_delta_norm_tol        1e-10
sternheimer_frequency_mpi         1
sternheimer_channel_mpi           1
sternheimer_mpi_layout            global_equation

exx_pca_threshold                 <scan or accepted threshold>
exx_ccp_rmesh_times               1
rpa_ccp_rmesh_times               1
rpa_abfs_preorth                  onsite_coulomb
rpa_abfs_preorth_threshold        1e-2
```

Use these two preorthogonalization keys identically in the RPA producer and Sternheimer response. The ABACUS global default remains `none` for backward compatibility, so molecular production scripts must set them explicitly. Require matching `RPA_ABFS_PREORTH` reports, `basis_aux_out`, dimensions, and full-Coulomb provenance before combining producer and response data.

Use the serial complete free-space Center2 V and Cs from the same finalized producer. Export `ao_potentials.dat` with `tools/molecular_sternheimer/export_ao_potentials.py` and verify its manifest against the response PP/NAO/ABFS/geometry. `limits` selects the free-space metric, not periodic Ewald/Massidda. Do not select a direct-reciprocal output or import a response-local V shard. The global `sternheimer_molecular_coulomb` default remains `none`.

Rotated, moment-split, shrunken and mixed external-plus-product ABFS, SIAB, forces and periodic q are outside the validated new route. Check the version-specific guards before submitting. An external-only ABFS uses PCA >= 1; product-only uses no external ABFS entry.

Use:

```bash
export ABACUS_STERNHEIMER_FD_ST_SOLVER_TOL=1e-6
export ABACUS_STERNHEIMER_FD_ST_MAX_ITER=300
export ABACUS_STERNHEIMER_FD_ST_SPECTRAL_PRECONDITIONER=1
export ABACUS_STERNHEIMER_FD_ST_SPECTRAL_PRECONDITIONER_REGULARIZATION=0
```

Increase the iteration limit if needed; do not loosen the residual gate to make a point finish.

For a box scan, set explicit `nx`, `ny`, `nz` so $h=L/N$ and nuclear grid phase remain fixed. For a grid scan, remove those keys and record the actual FFT dimensions selected from `ecutwfc`, unless an explicit distinct-grid ladder is used.

## Cheap And Production Settings

| Stage | FD | Frequencies | PCA | Grid/box treatment |
|---|---:|---:|---:|---|
| PBE pre-gate | n/a | n/a | n/a | cheap converged SCF/PW check |
| Box scan | 8 | 6 | `1e-4` | vary $L$, fixed $h$ and grid phase |
| Frequency scan | 8 | 6/8/12/16 | `1e-4` | accepted boxes and fixed grid |
| PCA scan | 8 | accepted | `1e-4/1e-6/1e-8` | accepted boxes/grid |
| Final grid scan | 8 | accepted | accepted | distinct actual FFT grids |
| NAO endpoint | 8 | accepted | regenerate matched ABFS | all numerical settings fixed |

These are efficient starting ladders, not universal convergence claims.

## Shared Frequency Contract

For each `nfreq`:

1. generate one GreenX minimax frequency/weight file from the declared molecular transition window;
2. use that exact file for molecule and all atoms;
3. record its SHA256 hash;
4. set the same `nfreq` in ABACUS and LibRPA;
5. verify exactly `nfreq` response matrices were written.

Do not truncate a larger frequency file to imitate a smaller GreenX grid.

## LibRPA Contract

Use the reader-v1 Sternheimer route and full Coulomb:

```text
task = rpa
nfreq = <same as ABACUS>
prefix_coul_full = v1_coulomb_full_iq_
prefix_sternheimer_chi0 = v1_sternheimer_chi0_iq_
sternheimer_iq = 1
sternheimer_qweight = 1.0
sqrt_coulomb_threshold = 1e-4
```

Use `sqrt_coulomb_threshold = 1e-4` as the validated production definition with `onsite_coulomb` preorthogonalization. Archive `1e-5`, `1e-6`, and zero as sensitivity diagnostics. Do not switch to cut Coulomb during a production series; cut Coulomb is a separately labeled diagnostic.

## Slurm Resource Shape

Start from:

```text
partition: normal or p1
MPI:       one rank per node
OpenMP:    all physical cores on the node
memory:    full usable node memory
nodes:     measured from a global_equation timing pilot
time:      maximum normal-partition wall time
```

Set:

```bash
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export OMP_PROC_BIND=spread
export OMP_PLACES=cores
```

Use `abacus-delta-st-efficient-production` to project the slowest-rank runtime. For a 24-hour queue, require at most 18 hours before the full series. Use measured equation ownership, memory, and long-tail evidence to increase nodes. Never assume that a fixed number of channels or equations per rank works for every molecule.

## Provenance Record

Archive at minimum:

```text
system, geometry, charge, nspin, occupations
ABACUS commit/path/SHA256
LibRPA commit/path/SHA256
PP path/SHA256
NAO path/SHA256 and generation provenance
ABFS/product-PCA source, threshold, naux, SHA256
RPA ABFS preorth mode/threshold, per-channel retained/rejected counts and identity error
box, ecutwfc, actual nx/ny/nz, h, FD order
nfreq, frequency-file SHA256
Coulomb definition, complete producer V/Cs SHA256, rmesh settings
AO tensor/exporter/manifest SHA256, finalized charge-moment tail audit
mixed AO/grid residual definition and explicit isolated_ri input/status
solver tolerance/max iterations, MPI ranks, OMP threads, memory
Slurm job ID/state/ExitCode/wall time/node-hours
solved/expected equations, maximum residual
EcRPA and energy definition
```

## Machine-Readable Result Gate

Require a summary equivalent to:

```text
status=success
all_converged=yes
complete_isolated_coulomb_postprocess=success
sternheimer_molecular_coulomb=isolated_ri
analytic_ao_contract=rhs_and_left_projection
analytic_ao_qspace=re_solved_grid_rhs
analytic_ao_residual=hybrid_ao_qspace_equations
analytic_ao_gram_reciprocal_condition=<finite value >= 1e-8>
grid_Q_potential=isolated_charge_multipole_tail
fd_order=8
virtual_source=ks_bands
nfreq=<expected>
naux=<producer value>
solved_equations=<expected>/<expected>
max_residual=<value <= 1e-6>
abfs_preorth=onsite_coulomb
abfs_preorth_threshold=1e-2
sqrt_coulomb_threshold=1e-4
sternheimer_preconditioner=fd_spectral
sternheimer_preconditioner_regularization_Ry=0
EcRPA_Ha=<finite value>
```

Reject missing fields, stale copied summaries, mismatched hashes, or energies recovered from a failed formal job unless a separate audited recovery procedure proves the physical output complete.
