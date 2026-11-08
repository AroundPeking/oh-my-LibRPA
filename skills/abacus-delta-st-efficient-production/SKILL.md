---
name: abacus-delta-st-efficient-production
description: Use when planning, submitting, or recovering molecular, atomic, or periodic-solid ABACUS Delta-Sternheimer jobs that must finish within a scheduler wall-time limit, especially after slow tails, load imbalance, or 24-hour timeouts.
---

# Efficient Delta-ST Production

Choose a physically equivalent parallel layout from measured equation throughput. Never submit a full molecule series or canonical-q array from node availability alone.

Also use `research-hpc-orchestrator` for provenance and duplicate prevention. Use `abacus-delta-st-molecular-convergence` or `abacus-delta-st-solid-convergence` for the physical convergence protocol.

## Non-Negotiable Rules

- Run production physics only on the remote compute host, on its production partition and storage root.
- Use the accepted executable hash and the exact final physical inputs in the timing pilot.
- Use FD8 for molecular, atomic, and formal periodic-solid response calculations. Keep old FD2 curves diagnostic and separate.
- Preserve existing outputs. Never resubmit an existing physical definition merely because its log is incomplete.
- Do not estimate completion from response-file counts. Read `STERNHEIMER_CHI0_PROGRESS_rank*.dat` equation counts and elapsed seconds.

## Mandatory 24-Hour Gate

1. Run one expensive representative channel before the full campaign: the largest planned molecular/atomic case, or one slow canonical q of the finest solid grid. A 10--30 minute pilot is enough after every rank finishes at least one k pair.
2. Run `scripts/estimate_sternheimer_runtime.py` on the live directory. Use a 1.25 safety factor and add SCF/startup time.
3. Submit the full array only when the conservative maximum is at most 18 hours for a 24-hour queue. Treat 18--24 hours as unsafe and change the parallel layout first. Reject estimates above 24 hours.
4. After 30--60 minutes of production, repeat the estimate for the slowest running rank. Recover early; do not wait for the time limit.
5. Compare both total wall time and node-hours. A layout that uses more MPI ranks can shorten the equation phase while wasting nodes or creating a slow communication/I/O tail; do not call it more efficient from equation throughput alone.

## Choose The Lane

- **Molecule or isolated atom:** read [references/molecular.md](references/molecular.md). Use FD8 with frequency MPI, channel MPI, and `global_equation`.
- **Periodic solid:** read [references/solid.md](references/solid.md). Keep analytic head/wing on. Prefer nested frequency plus k-point MPI, with `NPROC = nfreq * kpoint_groups`, for fine grids.
- Start resource tuning from one MPI rank per node with the node's usable OpenMP cores. Pack two or more ranks per node only after an A/B timing test shows that lower per-rank OpenMP width improves the required metric.

## Efficient Campaign Order

- **Molecule plus atoms:** pass PBE occupations first; converge box at fixed spacing; then frequency count; product-PCA threshold; distinct FD8 real-space grids; occupied-orbital representation; finally one matched SOS comparator. Treat every atom independently, keep integer spin occupations, and use `exx_ccp_rmesh_times=1`, `rpa_ccp_rmesh_times=1` for isolated species.
- **Insulating solid:** pass the PBE gap first; obtain actual grid fingerprints and skip repeated grids; converge distinct FD8 grids; then frequency count; PCA; full-Coulomb metric; and finally the common k/q mesh with analytic head/wing already enabled. Run one matched SOS comparator only after the Delta-ST endpoint is accepted.
- Do not launch all expensive points merely because nodes are free. Pilot the largest molecule/atom or the finest-grid slow q first, pass the 18-hour gate, and only then release independent arrays.

## FD Spectral Preconditioner

For FD8 Delta-ST production built from an accepted `master_ghj`, do not export either spectral-preconditioner environment variable. The discrete-kinetic right preconditioner is the no-configuration default with zero regularization. Require the ABACUS report to contain `sternheimer_preconditioner fd_spectral` and `sternheimer_preconditioner_regularization_Ry 0`; the report, executable hash, and source commit are the provenance gate.

Use `ABACUS_STERNHEIMER_FD_ST_SPECTRAL_PRECONDITIONER=false` only for a controlled rollback or A/B diagnostic. Never leave that rollback setting in a production script. The regularization override is likewise diagnostic-only unless a separately accepted campaign requires it.

For each newly merged executable, compare enabled and disabled paths once on representative molecule and solid inputs with the same physical definition, MPI/OMP layout, solver tolerance, and fixed frequency. Accept only complete responses with matching dimensions and matrix/residual agreement within the campaign tolerance. Do not repeat the disabled control for every material unless the report, residual, iteration count, or final energy is anomalous. Measured one-frequency ABACUS speedups do not directly apply to Slurm queue time, LibRPA, or a full multi-q/multi-frequency campaign.

## Independent Channel Batching

Accepted `master_ghj` builds batch two independent auxiliary-response channels
by default. Do not export `ABACUS_STERNHEIMER_CHANNEL_BATCH_WIDTH` in normal
production. Require the ABACUS report to show
`sternheimer_channel_batch_width 2` and the planned outer worker count; batch
columns do not reduce the available outer OpenMP workers when memory permits.

Use `ABACUS_STERNHEIMER_CHANNEL_BATCH_WIDTH=1` only for regression or rollback.
Width four is not a production recommendation: the accepted Si q=7 A/B/C gave
only a 0.99% total-wall improvement over width one while increasing per-rank
MaxRSS by about 74%. Width two gave a 4.13% total-wall/node-hour reduction,
5.7% response-interval speedup, and response-matrix relative Frobenius
difference `7.59e-13`, with about 24.8% more per-rank memory than width one.
Revalidate on a representative case before changing the default width or using
a larger batch.

## Parallel A/B Gate

Before changing a formal campaign to a new MPI layout, compare one small completed channel against the old layout. Require identical physical inputs, `all_converged=yes`, complete manifests, matching matrix dimensions, and numerical agreement within the existing solver/output precision. Runtime improvement without physical equivalence is not accepted.
