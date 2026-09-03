# Fisherd molecular Delta-ST current-stack checkpoint

- Route: `molecular_delta_st_rpa`
- ABACUS: `1648a8a344427ae1b6394912bf677c4a20e053f2`
- LibRPA: `7e40c5bbf735a78aa15fa589ca2468fec2e2427b`
- PyATB: `9fb9028c59b1dbaf9cf66965280961fc2225d9eb`

The complete machine-readable receipt is
[`benchmarks/live/fisherd-molecular-delta-current-2026-09-03.json`](../../benchmarks/live/fisherd-molecular-delta-current-2026-09-03.json).

## RESULT

The clean current ABACUS checkout built successfully on Fisherd. Seven focused
input, Delta-ST, finite-difference, response-grid, smoke, periodic-solver, and
k/q tests passed 7/7. The executable SHA-256 is
`7aba04e711e68bc654dc737ed5c1a330ddfe62a7ea2305c4d78b6edad5347b5a`.

The historical-input H2 replay also passed the producer gate. It used an
explicit 50x50x50 grid, FD8, the `fd_spectral` preconditioner with zero
regularization, `ks_bands`, one imaginary frequency, and reader-v1. All 30
equations converged, with maximum solver relative residual
`3.322591176989514e-7`. ABACUS exited 0 in 6.70 seconds with peak RSS
8,203,396 KiB.

The producer did not write the required
`v1_sternheimer_coulomb_iq_1_rank0.dat`. It wrote the ordinary
`v1_coulomb_full_iq_1_rank0.dat`, but that file is not an allowed fallback.
Therefore the current-stack verdict is
`BLOCKED_MISSING_RESPONSE_COULOMB`, while producer status remains `PASS`.

## DIAGNOSTIC CONTROL

The current ordinary matrix is byte-identical to the ordinary matrix from the
previous v3 run. It differs from the validated dedicated Sternheimer metric by
`0.0037011365` in relative Frobenius norm, with maximum entry difference
`0.28468244`. The files are therefore different physical representations, not
renamed equivalents.

A preserved diagnostic LibRPA run using the prohibited ordinary prefix
finished and gave `EcRPA = -0.01109259015020 Ha`. The validated v3 dedicated
metric gave `-0.01100066029904 Ha`; the difference is `0.00009192985116 Ha`,
or `0.05768685 kcal/mol`. The diagnostic is finite but remains
`DIAGNOSTIC_ONLY`. A small difference in this one H2 point cannot override the
representation contract or establish molecular convergence.

Source history confirms that the validated metric-writing revision
`81ff5f33995e7a545c2b9cb4f1a74490a74ecb4a` is not an ancestor of the tested
current ABACUS revision. It remains on
`origin/codex/sternheimer-grid-metric-handoff-20260830`.

## ACCEPTANCE

- Producer and focused source tests: `PASS`.
- Reader-v1 response file: `PASS`.
- Dedicated response Coulomb handoff: `BLOCKED_MISSING_RESPONSE_COULOMB`.
- Production LibRPA: `NOT_RUN_HANDOFF_BLOCKED`.
- Scientific acceptance: `NOT_EVALUATED`.
- Automatic promotion: `BLOCKED`.

The next valid step is to restore the dedicated metric on the selected ABACUS
production revision and repeat this exact L3 handoff. Only after that passes
should the benchmark proceed to molecule and atom absolute correlation
energies, binding contribution, box, real-space Ecut, frequency, PCA/ABFS, and
SOS controls.
