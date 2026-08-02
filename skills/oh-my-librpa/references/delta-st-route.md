# Delta-Sternheimer Route

Use this route for ABACUS molecular or periodic-solid Delta-Sternheimer response calculations, including LibRPA RPA handoff, convergence scans, live progress checks, and Slurm resource sizing.

## Version and run isolation

Apply the ABACUS+LibRPA version guard before staging. Record the ABACUS feature commit, executable SHA256, LibRPA executable SHA256, fixed frequency grid, basis files, pseudopotentials, and Coulomb convention. Use a fresh directory for every resource layout or numerical point. Never overwrite or cancel an older production run unless the user explicitly requests it.

## Common physical contract

Use the auxiliary-basis Hartree potential as the perturbation and solve the occupied-state response. For an imaginary frequency,

\[
 Q(H-\epsilon_i+i\omega)Q\,\delta\psi_i
 =-Q\,\delta V_\mu\psi_i.
\]

Delta-ST reconstructs the response represented by the selected LCAO subspace and solves the complementary grid-space response. Use `sternheimer_delta 1` and the validated `ks_bands` virtual source unless a named experiment changes that source. Do not infer occupied/virtual states from band indices when occupations are available.

Build the induced density from occupations and spin channels,

\[
 \delta n=2\operatorname{Re}\sum_{i\sigma} f_{i\sigma}
 \psi^*_{i\sigma}\delta\psi_{i\sigma},
\]

with the implementation's spin convention. Never add a blind factor of two to an `nspin=2` result.

For the Coulomb-potential perturbation convention, hand the Sternheimer response to LibRPA using the selected full-Coulomb metric and evaluate

\[
 \Pi=V_{\rm full}^{-1/2}M_{\rm ST}V_{\rm full}^{-1/2}.
\]

Use the same GreenX frequency file across compared runs. A valid endpoint requires ABACUS `status success`, `all_converged yes`, the expected response matrices, the stated residual tolerance, and `libRPA finished successfully`.

With global-equation MPI, ABACUS may write a full-Coulomb matrix as several rank shards. Do not byte-compare one shard with a monolithic reference file. Verify the basis/metadata and either assemble the documented shards or give LibRPA the explicitly selected monolithic full-Coulomb reference.

## Molecules and atoms

Represent an isolated atom or molecule with a Gamma-only periodic supercell. Converge the molecule and every atomic fragment independently with respect to box size before forming a binding or dissociation energy. During an Ecut scan, remove explicit `nx/ny/nz` so `ecutwfc` selects the native uniform FFT grid. Keep geometry, orbital basis, auxiliary basis, frequency file, Coulomb matrix, solver tolerance, and spin state fixed.

For a molecule, the response-equation count is

\[
 N_{\rm eq}=N_{\rm freq}N_{\rm aux}\sum_\sigma N_{\rm occ,\sigma}.
\]

Report molecular and atomic zero-order contributions, correlation energies, the combined energy, wall time, node-hours, and peak memory separately.

## Periodic solids

For a perturbation at \(\mathbf q\), solve each occupied \((n,\mathbf k)\) response in the \(\mathbf k+\mathbf q\) sector,

\[
 Q_{\mathbf k+\mathbf q}
 (H_{\mathbf k+\mathbf q}-\epsilon_{n\mathbf k}+i\omega)
 Q_{\mathbf k+\mathbf q}\delta\psi_{n\mathbf k}
 =-Q_{\mathbf k+\mathbf q}\delta V_{\mu\mathbf q}\psi_{n\mathbf k}.
\]

Use the overlap metric consistently for LCAO projections and residuals. Keep the full k/q coverage, q weights, symmetry reconstruction, and `q=0` head/wing treatment explicit. A single q star or a solver/output smoke test is not a full-BZ RPA energy gate. Keep molecular and solid convergence thresholds separate.

## MPI and memory resource policy

Use `sternheimer_frequency_mpi 1`, `sternheimer_channel_mpi 1`, and `sternheimer_mpi_layout global_equation` for production when that exact implementation has passed a same-matrix endpoint test. In global-equation mode, MPI ranks must not be pinned to `nfreq`; the ranks distribute occupied-state/frequency/auxiliary-channel equations globally.

On df_dcu, use the `normal` partition and probe the live node limits. The currently validated full-node shape is one MPI rank per node, 30 OpenMP threads per rank, 110610 MB per node, and a 24-hour limit. Do not place multiple large-grid ranks on one node unless a memory preflight proves that the duplicated fixed state and all solver workspaces fit.

Read every rank's `channel_workers_ready` record:

`memory_current_bytes`, `memory_per_worker_bytes`, `automatic_workers`, and `effective_workers`.

If `automatic_workers>1` but `effective_workers=1`, treat it as a memory-limited outer-channel fallback. Immediately tell the user that each rank is solving one equation at a time with grid OpenMP and recommend more nodes/MPI ranks. This is a performance warning, not a correctness failure.

Size a production rerun from the slowest rank, not aggregate equation progress. Estimate its completion time and choose

\[
 N_{\rm new}\geq
 \left\lceil N_{\rm old}\frac{T_{\rm projected}}{T_{\rm target}}\right\rceil,
 \qquad T_{\rm target}\leq0.8T_{\rm limit}.
\]

Round upward for queue and load-balance margin. More nodes reduce equations per rank but do not remove the per-rank memory fallback; reducing worker memory and dynamic/cost-aware equation assignment are separate code optimizations.

## Live reporting

For running jobs report: scheduler state, elapsed/limit, equations per rank, slowest-rank fraction, newest progress age, convergence residuals, memory-plan line, projected wall time, and recommended nodes. Never call a job healthy from `RUNNING` alone. If a replacement layout is submitted while the old job continues, use an isolated output root and report both job IDs.

