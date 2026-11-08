# Periodic Solid Delta-ST Protocol

## 1. Freeze the Scientific Definition

Record before submission:

- structure, primitive-cell atom count, lattice constant, and energy normalization;
- PP, NAO, ABFS/product-PCA chain and actual auxiliary dimension;
- atomic spin multiplicities, occupations, boxes, and grid phase;
- ABACUS and LibRPA commit, executable SHA256, and head/wing implementation provenance;
- full-Coulomb convention, q=0 treatment, GreenX grid/hash, and solver tolerance.

Run a cheap same-PP PBE gate for solid and atoms. Verify electron counts, intended atomic integer occupations, and a positive solid gap. A nominal semiconductor such as Ge is not eligible when the actual PBE setup is gapless.

## 2. Efficient Full-Convergence Order

### A. Actual-grid Ecut

Use FD8 for formal solid and atomic responses. Keep FD2 only as a separately labeled diagnostic. Use a 20 Angstrom cubic Gamma-only atom box by default; do not add a 24 Angstrom box test unless 20 Angstrom shows direct evidence of residual image interaction. Before a full canonical-q array, obtain

`(Nx, Ny, Nz, Ngrid, dV)`.

If two Ecut values have the same fingerprint, mark the second `SKIPPED_SAME_GRID`; do not run response or LibRPA. Plot against actual `Ngrid` or spacing, with Ecut only as a label. A useful first solid ladder is 10, 15, 20, 30 Ry; use 15, 20, 25, 30 Ry for atoms and extend only if distinct-grid changes fail.

Do not declare convergence from a small grid increment even when the adjacent energy change is below threshold. The project acceptance rule is an independent confirmation point with `Ngrid_new / Ngrid_candidate >= 1.5` and an absolute total-energy change below 0.1 kcal/mol under otherwise identical settings. For cubic grids near 25--35 points per direction, increasing each direction by about five points normally satisfies this test. Label any smaller-step plateau `FALSE_PLATEAU_RISK` and continue. The Si `24^3 -> 25^3` plateau is the canonical rejected example; `30^3 -> 35^3` is the required follow-up scale.

Require absolute solid total energy per atom, every atomic total energy, and cohesive energy to change by less than 0.1 kcal/mol after the robust grid-size gate above. Do not accept cancellation alone.

For the Si atomic reference, do not assume the default box without an independent gate. First scan box length at fixed real-space spacing and fixed grid phase using FD8, one archived `nfreq=6` frequency file, PCA `1e-4`, integer triplet occupations, and `exx_ccp_rmesh_times=rpa_ccp_rmesh_times=1`. A practical ladder is 14.375, 16.250, 18.125, and 20.000 Angstrom with grids 92, 104, 116, and 128, respectively, so that `h=0.15625` Angstrom and the atom remains on the central grid point. Use the 0.1 kcal/mol absolute-energy gate; record the tighter 0.025 kcal/mol adjacent atom change when affordable. Freeze 20 Angstrom only after the box curve passes, then continue frequency, PCA, and distinct-grid convergence in that order.

### B. GreenX frequencies

Freeze Ecut and scan 6, 8, 12, 16. Use one archived frequency/weight definition and verify the response metadata. Stop at the first adjacent endpoint passing the absolute-energy and cohesive-energy gates.

### C. Auxiliary PCA

Freeze Ecut/frequency and scan `1e-4`, `1e-5`, `1e-6`. Add `1e-7` only if `1e-5 -> 1e-6` fails. Record actual auxiliary dimensions and ordering.

### D. Coulomb metric

For periodic solids, production defaults are `exx_ccp_rmesh_times=2` and `sqrt_coulomb_threshold=1e-5`. For a new element/basis family, a cheap one-q metric check of rmesh 2 versus 3 is sufficient; do not launch a full energy scan unless the matrix or trace-log gate fails.

For isolated atoms, set `exx_ccp_rmesh_times=1` and `rpa_ccp_rmesh_times=1`. Verify the final spin-resolved `eig_occ.txt` contains only integer occupations and matches the intended atomic multiplicity. Do not use the solid rmesh setting for the atomic reference.

On server 66, cap every submission at 10 nodes. A 16-node response layout requires verification that the selected available host's scheduler and allocation support it; do not infer this from historical runs elsewhere.

Before releasing a full canonical-q array, apply `abacus-delta-st-efficient-production`. Pilot a slow q on the finest grid and require a conservative projected runtime of at most 18 hours for a 24-hour queue. For `nfreq=F`, use nested frequency/k-point MPI with `NPROC=F*kpoint_groups` on fine grids after a one-q physical A/B gate. Do not rely on one rank per frequency when it leaves all k points serial on that rank.

### E. Solid k/q mesh with head/wing on

Run common k/q meshes `2^3 -> 3^3 -> 4^3`; add `5^3` only when `3^3 -> 4^3` fails. Formal points always use:

```text
replace_w_head true
option_dielect_func 3
rpa_headwing_mode qavg
rpa_headwing_body_start 1
```

Require the adjacent cohesive-energy change below 0.1 kcal/mol per atom. An off-head/wing curve is optional diagnosis, never a required production scan.

## 3. Conservative New-Material Screening

Use this only after the PBE/gap and provenance gates pass. It gives one reliable-looking comparison point, not a convergence claim.

- solid: FD8, a distinct grid at 30 Ry or the finest verified reusable grid, 16 frequencies, PCA `1e-6`, common k/q `4^3`, rmesh 2, full Coulomb, q=0 included, analytic q-average head/wing on;
- atoms: Gamma-only FD8, a 20 Angstrom cubic box, 30 Ry or the finest verified element grid, 16 frequencies, PCA `1e-6`, physical integer occupations, and `exx_ccp_rmesh_times=rpa_ccp_rmesh_times=1`;
- use the same PP/NAO/ABFS family across solid and atoms;
- label the outcome `SCREENING_NOT_CONVERGED` until at least one adjacent confirmation point passes.

If a verified endpoint exists for the same element contract, reuse it instead of recomputing. Do not transfer an atom across different PP, NAO, ABFS, occupation, box, or Coulomb definitions.

## 4. Matched SOS Comparator

After the Delta-ST producer is accepted, run one SOS comparator with all LCAO bands and the same structure, PP/NAO/ABFS, PCA, frequency grid, full Coulomb, k/q mesh, head/wing settings, and atomic reference. Reuse the producer when the data contract allows it. Report Delta-ST and SOS absolute components before their cohesive-energy difference.

## 5. Scheduler And Duplicate Rules

- Use production/normal partitions only.
- Query existing registries, Slurm jobs, case roots, and result summaries before submission.
- Keep one formal lane per material and parameter fingerprint; do not migrate or duplicate a running job.
- Split independent canonical q representatives into arrays and preserve completed elements during recovery.
- A failed wrapper after complete physics is recovered by auditing the existing case; never rerun successful ABACUS output solely for a post-check error.

## 6. Required Result Record

For every accepted or screening point, record:

- scheduler state/ExitCode, node/partition, wall time and node-hours;
- actual grid fingerprint, FD order, nfreq/frequency hash, PCA threshold and naux;
- head/wing settings and response-frequency metadata source;
- `E0`, `EcRPA`, total energy, atom energies, and positive cohesive energy;
- PP/NAO/ABFS, binary hashes, job IDs, remote paths, and acceptance status;
- exact literature lattice constant and energy definition.

Update machine-readable CSV first, regenerate convergence/comparison plots, compile the TeX document with XeLaTeX, and visually inspect every new page. Preserve failed or obsolete data but keep it out of final curves.
