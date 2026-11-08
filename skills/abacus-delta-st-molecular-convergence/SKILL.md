---
name: abacus-delta-st-molecular-convergence
description: Use when preparing, running, auditing, or documenting ABACUS Delta-Sternheimer plus LibRPA calculations for isolated molecules and their spin-polarized atomic fragments, including box-size, GreenX frequency, auxiliary-basis PCA, FD-grid, occupied-orbital, pseudopotential, SOS, binding-energy, and resource-convergence questions.
---

# ABACUS Molecular Delta-ST Convergence

Use one controlled protocol for every molecule and all atomic fragments. Treat solver completion, numerical convergence, and agreement with a reference as three separate conclusions.

Before submitting work, also apply:

- `research-hpc-orchestrator` for duplicate prevention, queue choice, provenance, and result collection;
- `abacus-delta-st-efficient-production` for measured equation-throughput sizing and the 24-hour gate;
- `abacus-librpa-version-guard` for the accepted ABACUS/LibRPA build contract;
- `ghj-aitp-tex-research-note` when recording the campaign in the project TeX document.

Read [references/parameter-contract.md](references/parameter-contract.md) before writing INPUT, Slurm, or LibRPA files.

## Define The Quantity First

For a molecule containing $n_A,n_B,\ldots$ atoms, define the correlation contribution to dissociation as

\[
D_c=\sum_X n_X E_c(X)-E_c(\mathrm{molecule}).
\]

Use $627.5094740631$ kcal/mol per Ha. State whether the reported value is:

- correlation-only $D_c$;
- zero-order/exchange contribution;
- total RPA@PBE dissociation energy;
- an SOS or Delta-ST result;
- an all-electron, frozen-core, or pseudopotential result.

Never compare unlike definitions or call cancellation in $D_c$ convergence of the absolute energies.

## Non-Negotiable Physical Contract

- Use `sternheimer_fd_order 8` explicitly for every molecular and atomic response calculation. FD2/FD4/FD6 are diagnostics only.
- Use `sternheimer_delta_virtual_source ks_bands`; do not require a manual environment override.
- Use the full LCAO band space. Set `nbands` to the actual NAO dimension unless a separately validated reason requires otherwise.
- For new isolated molecular/atomic Delta-ST, use the explicit `sternheimer_molecular_coulomb isolated_ri` route described below. The global ABACUS default remains `none`; a Gamma-only solid is not an isolated molecule.
- For isolated molecules and atoms, start with `exx_ccp_rmesh_times 1` and `rpa_ccp_rmesh_times 1`; do not change either during an ordinary convergence scan.
- For new molecular and atomic Delta-ST work, explicitly use `rpa_abfs_preorth onsite_coulomb` with `rpa_abfs_preorth_threshold 1e-2` in both producer and response INPUT files. Use `none` only to reproduce historical results or for a clearly labeled A/B diagnostic.
- Use LibRPA `sqrt_coulomb_threshold = 1e-4` as the production definition with on-site preorthogonalization. Archive `1e-5`, `1e-6`, and zero only as threshold-sensitivity diagnostics; zero is not a production definition.
- Keep the verified FD spectral Sternheimer preconditioner enabled with zero regularization. Record `sternheimer_preconditioner fd_spectral` and `sternheimer_preconditioner_regularization_Ry 0` from the response status.
- Use `symmetry -1` and `exx_singularity_correction limits` in the serial producer and response. This selects the complete free-space Center2 metric; do not mix it with a periodic Ewald/Massidda or direct-reciprocal metric.
- Generate a Coulomb matrix for each box. Do not reuse a file from a different box, auxiliary ordering, or pseudopotential/orbital chain.
- Use one pseudopotential with its matched NAO and product-PCA ABFS chain for a production series. A PP change that also changes NAO/ABFS is a joint representation change, not a pure PP difference.
- Give each atom its physical spin multiplicity and converge it independently. Do not force the molecular box, spin, or grid onto an atom.

## Isolated RI Coupling

The producer supplies complete serial V and localized-RI Cs. Export the Hartree AO tensor with the repository's `tools/molecular_sternheimer/export_ao_potentials.py`; require complete pair coverage, correct AO/ABFS order, Gamma identity, finite Hermitian matrices and archived hashes. Set `sternheimer_ao_potential_file` to that immutable tensor. Never analyze a multi-rank response's local V shard.

The AO right source and conjugated left contraction use the same RI vertices, while Q-space is solved again with the sampled isolated perturbation. Outside the radial table, continue the potential from the actual finalized auxiliary charge's multipole moment, not its final tabulated potential value. Compact charge does not imply zero multipole moment. Do not force all tails to zero because some rotated channels have zero moments.

Require `analytic_ao_contract rhs_and_left_projection`, `analytic_ao_qspace re_solved_grid_rhs`, `analytic_ao_residual hybrid_ao_qspace_equations`, sampled AO Gram eigenvalue ratio >= 1e-8, and the charge-moment tail audit. This residual validates the mixed AO/grid equations, not pure-grid or continuum equivalence. Do not replace an SOS contribution after solving the old equation.

Until separately validated, reject rotated/moment-split/shrunken or external-plus-product mixed ABFS, SIAB, forces and periodic q output in this route. Use a product-only PCA basis, or external-only ABFS with `exx_pca_threshold >= 1`. Reject the old experimental analytic-AO/tail environment switches. Ordinary SOS and periodic response retain their existing paths; changing them requires their own controlled tests.

Implementation merged to `master_ghj` as `1dc96f149927915ce15ac30e9633d89c4c0ed73f`. Final remote build 3267969, binary SHA256 `e06c37bfd706bb4a835c826679eda6b5674455c6add75a646641943332ce15b7`, passed seven focused native tests and H2 guard pilot 3268100. Earlier same-equation build 3267624, binary SHA256 `b32e9459ddc65dae9274bf6368292bb039a7553a80893b2aba7b1e4df83058f0`, completed H2/H full32 and Li2/GTH-N2 single-frequency comparisons within 1e-7 Ha of the endpoint-tail control; active jobs retained that immutable binary. The final guard pilot changed H2 single-frequency energies by less than 5e-17 Ha. This is not a basis/box convergence certificate for a new molecule. Record the current source commit and binary hash before each campaign, rather than blindly reusing this historical artifact.

## Cheap Pre-Gate

Run this before expensive response scans, especially for a new element or pseudopotential.

1. Converge ordinary PBE SCF occupations for the molecule and every atom.
2. Verify integer occupations and the intended atomic multiplicity. If degeneracy causes fractional occupations, use a documented symmetry-breaking field/restart protocol instead of accepting the wrong state.
3. Compare the matched LCAO PBE result with a same-pseudopotential PW calculation or with the next NAO hierarchy for the molecule and each atom separately.
4. Inspect absolute total energies, occupied eigenvalues, and the dissociation combination. Large molecule/atom imbalance is an occupied-orbital or PP/NAO transferability problem, not a Delta-ST, PCA, or LibRPA error.
5. Stop the expensive campaign until this gate is understood.

## Efficient Convergence Order

Change one variable at a time and freeze it after it passes. Use the same ordered sequence for every new molecule.

### 1. Box Size At Fixed Grid Spacing

This is the first Delta-ST scan because an oversized box multiplies all later costs.

- Use FD8, `nfreq=6`, PCA $10^{-4}$, solver tolerance $10^{-6}$, and the same physical geometry.
- Scan molecule and atomic fragments independently. Typical starting ladders are 10, 12, 14.4, 16 Angstrom; extend only the unconverged species.
- Keep the real-space spacing $h=L/N$ fixed, initially near 0.16 Angstrom when suitable. Set explicit `nx`, `ny`, `nz` for this scan.
- Keep the nuclei at the same grid phase. Center each isolated species consistently and, where possible, place the center and symmetry-related nuclei on equivalent grid indices.
- Rebuild the complete isolated producer V and matching AO tensor for every changed box/input identity.
- Accept the smallest box whose next larger box changes each required absolute $E_c$ and $D_c$ by less than 0.1 kcal/mol. A tighter 0.025 kcal/mol atom gate is useful when several atoms amplify the atomic error.
- Once an atom is converged, keep its accepted box fixed while continuing the molecular scan. The molecule and atoms need not use equal boxes.

Do not vary box length and grid spacing together. An oscillatory curve produced from mixed $L$, $h$, executable, or response provenance is not a box-convergence curve.

### 2. GreenX Imaginary Frequencies

- Freeze all accepted boxes and the FD8 grid spacing.
- Keep PCA at $10^{-4}$ for this scan.
- Start at 6 frequencies, then test 8, 12, and 16 only as needed.
- Generate each GreenX minimax grid from one declared molecular transition window. Reuse the exact frequency/weight file byte-for-byte for the molecule and all atoms at that `nfreq`.
- Accept when every absolute molecular/atomic $E_c$ and $D_c$ changes by less than 0.1 kcal/mol between adjacent frequency grids.

Do not compare calculations that silently generated different minimax grids from different atomic eigenvalue windows.

### 3. Product-PCA Auxiliary Basis

- Freeze boxes, FD8 grid spacing, and the accepted frequency file.
- Scan `exx_pca_threshold` efficiently as $10^{-4},10^{-6},10^{-8}$.
- Insert $10^{-5}$ or $10^{-7}$ only to diagnose a non-smooth step or to bracket the endpoint.
- Record the actual `naux` for the molecule and every atom. Never describe convergence using the threshold alone.
- Apply the same on-site Coulomb preorthogonalization to every PCA point before building producer or response data. Confirm matching preorthogonalized dimensions and reports for producer and response.
- Require absolute molecular/atomic $E_c$ and $D_c$ to change by less than 0.1 kcal/mol.
- If $10^{-6}\rightarrow10^{-8}$ fails, add $10^{-9}$; do not call $10^{-8}$ converged automatically.

### 4. FD8 Real-Space Grid

- Freeze accepted boxes, frequencies, PCA, PP/NAO/ABFS, and solver settings.
- Remove explicit `nx`, `ny`, `nz` and scan `ecutwfc`, or set an explicit sequence of distinct grids when deterministic grid control is required.
- A useful first ladder is 25, 30, 35, and 40 Ry. Extend to 45/50 Ry only when an absolute energy fails the gate.
- Parse the actual FFT dimensions from ABACUS. Plot and judge convergence versus actual one-dimensional grid count $N$ or spacing $h=L/N$, never versus nominal `ecutwfc` alone.
- If two Ecut values produce the same real-space grid, retain the second point only as a PW-cutoff diagnostic; it is not a grid refinement.
- Require the finest adjacent distinct-grid change in every absolute molecular/atomic $E_c$ and in $D_c$ to be below 0.1 kcal/mol.

Do not accept a small change in $D_c$ when molecule and atom errors of order $10^{-3}$ Ha merely cancel.

### 5. Occupied-Orbital Representation

Delta-ST removes the need to converge a large virtual LCAO space, but it does not remove occupied-orbital error.

- After numerical parameters pass, compare the production NAO with the next sensible occupied-space hierarchy or radius.
- Keep PP, geometry, boxes, frequencies, PCA convention, FD8 grid, and Coulomb definition fixed.
- Require each absolute $E_c$ and $D_c$ to pass 0.1 kcal/mol.
- If a larger radius or hierarchy worsens the result, inspect same-PP PBE molecule/atom imbalance, orbital-generation provenance, product-PCA dimension, and occupied eigenvalues before adding an even larger basis.

Do not use a reference value as the convergence target. Convergence is internal stability; reference disagreement is a separate error analysis.

## Run-Time Layout

- Use production/normal partitions only; never submit these calculations to debug partitions.
- Use one MPI rank per node and fill the node with OpenMP threads and available memory.
- Enable frequency MPI, channel MPI, and `global_equation` scheduling.
- Size ranks from the total equation count and a live `global_equation` pilot; ranks do not need to equal `nfreq`.
- If memory forces one concurrent Sternheimer equation per rank, report that fact and request more nodes rather than allowing a nominally parallel job to serialize.
- Derive expected equations and `naux` from producer output. Do not hard-code dimensions from another molecule.
- Keep the zero-order producer shared within one controlled series; parallelize response equations instead of rerunning the producer once per frequency.
- Record wall time and node-hours for molecule and atoms separately.
- Before submission, check for an existing formal job with the same input fingerprint. Never duplicate a pending or running job.
- For a 24-hour queue, release a full molecule/atom series only when the conservative progress estimate is at most 18 hours. Treat 18--24 hours as unsafe and add ranks before production.

## Acceptance Gate For Every Point

Require all of the following before using an energy:

1. Slurm `COMPLETED` with `ExitCode=0:0`.
2. ABACUS SCF converged with intended electron count, spin, and occupations.
3. `STERNHEIMER_CHI0.dat` reports `status success` and `all_converged yes`.
4. FD order is 8, virtual source is `ks_bands`, and the expected MPI layout was used.
5. Solved equation count equals the expected count; no residual exceeds $10^{-6}$.
6. Exactly `nfreq` reader-v1 response files exist and match the archived frequency hash.
7. The auxiliary dimension/order, AO tensor and complete isolated Coulomb provenance match the producer; the explicit `isolated_ri` status and charge-moment tail audit are present.
8. The producer and response both report `RPA_ABFS_PREORTH mode=onsite_coulomb`, threshold `1e-2`, matching output dimensions, and acceptable on-site identity errors.
9. The trace-log uses producer complete V with new B, applying the same on-site congruence scaling to both, at primary `sqrt_coulomb_threshold=1e-4`, and gives finite `EcRPA`.
10. Logs contain no NaN, OOM, fatal signal, or unconverged-equation marker.

`RUNNING`, an empty stderr, a generated matrix, or a parser success is not a physical result.

## Stop Rule And Reporting

For every adjacent pair $j-1,j$, calculate

\[
\Delta E_c(X)=627.5094740631\left|E_c^{(j)}(X)-E_c^{(j-1)}(X)\right|
\]

for the molecule and every distinct atom, plus

\[
\Delta D_c=\left|D_c^{(j)}-D_c^{(j-1)}\right|.
\]

Accept a parameter only when every required quantity is below 0.1 kcal/mol. Preserve the previous point as the uncertainty estimate.

For each parameter, plot absolute $E_c$ for the molecule and each atom and plot $D_c$. For the grid plot, use actual $N$ or $h$ on the x-axis. Put failed/obsolete FD2 or mixed-provenance curves in an appendix, not the main conclusion.

The audit record must include (keep these in the README/data, not extra columns in a compact paper table):

- geometry and spin states;
- PP, NAO, ABFS/product-PCA provenance and `naux`;
- molecule/atom boxes and actual grids;
- FD8, frequency file/hash, PCA threshold, Coulomb convention, and solver tolerance;
- absolute $E_c$ values in Ha;
- $D_c$ in kcal/mol and eV;
- uncertainty from each endpoint scan;
- ABACUS/LibRPA binary hashes, jobs, wall time, and node-hours;
- reference value and its exact energy definition.

For this molecular paper, keep the visible comparison table to six columns: system, R, ABACUS Dtotal, FHI-aims Dtotal, ABACUS Dc, FHI-aims Dc. Do not compare pseudopotential and all-electron absolute total energies. Preserve missing values and historical definitions rather than substituting unmatched fragments. Keep old Ewald/grid-only and endpoint-tail results as controls, not overwritten data.

## SOS Comparator

After the Delta-ST result is converged, run one matched SOS comparator when requested:

- use all LCAO bands, not a truncated empty-band set;
- use the same PP/NAO/ABFS, PCA endpoint, frequency file, declared complete Coulomb kernel, geometry, and accepted boxes; leave the ordinary SOS algorithm unchanged;
- report its own absolute atomic/molecular $E_c$ and $D_c$;
- label it by NAO hierarchy and PCA threshold.

The SOS difference can include finite virtual-LCAO, RI and grid-partition errors; it alone proves neither correctness nor a bug. Do not substitute SOS convergence for Delta-ST convergence.

## Reuse Across Molecules

Reuse the protocol and accepted element-level assets, not numerical assumptions. For a new molecule:

1. run the PBE occupied-space pre-gate;
2. reuse an atomic box only when the same PP/NAO/spin/grid-phase contract was already converged;
3. repeat at least the cheap molecular box scan;
4. reuse frequency/PCA/grid endpoints only after one adjacent confirmation point passes for the new system;
5. archive one machine-readable row per successful endpoint and update the project TeX table only after all gates pass.

The on-site transformation is not mathematically molecule-only. Automatic use in this skill is limited to isolated molecules and atoms because that is the validated production domain; periodic solids require a separate acceptance regression before enabling it by default.
