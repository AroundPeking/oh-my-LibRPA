# Fisherd v2 admission checkpoint (2026-08-30)

This checkpoint tests profile `abacus-librpa-2026-08-30-v2` on Fisherd. The
machine-readable record is
[`benchmarks/live/fisherd-v2-admission-2026-08-30.json`](../../benchmarks/live/fisherd-v2-admission-2026-08-30.json).

## Result

- Exact clean source revisions were used for ABACUS, LibRPA, and PyATB.
- LibRPA built all targets; its selected route tests passed `5/5`.
- ABACUS built the production `abacus_3p` target; its selected tests passed
  `11/11`. The aggregate build still has one stale test-source compile warning.
- Reader-v1 is the only active handoff format. Symmetry metadata comes from
  `stru_out`; no legacy symmetry sidecars were copied.
- The v2 score is `56.5/100`, verdict `INCOMPLETE`. No route was promoted.

| Route | Highest evidence | Process | Numerical | Scientific | Promotion |
| --- | --- | --- | --- | --- | --- |
| periodic 3D GW | L2 exact replay | PASS | PASS | NOT_EVALUATED | BLOCKED |
| strict-2D GW | L2 synthetic current-source replay | PASS | PASS | NOT_EVALUATED | BLOCKED |
| molecular Delta-ST RPA | L3 H2 smoke | PASS | PASS | NOT_EVALUATED | BLOCKED |
| solid Delta-ST RPA | L3 Si2 partial checkpoint | PASS | WARN | NOT_EVALUATED | BLOCKED |

## Gates

The periodic 3D replay read eight 26-state tables and reproduced all 1,456
finite reference values exactly. The strict-2D replay used full Ewald Coulomb
plus analytic head/wing and reproduced `-0.03189000799689 Ha` exactly; it is not
a material L3 acceptance run.

The H2 producer solved 30 equations and LibRPA returned a finite
`EcRPA=-0.0110925901502 Ha`. This proves the current molecular reader-v1 path,
not box, frequency, auxiliary-basis, or scientific convergence.

The Si2 producer solved all 62,464 equations on a 24x24x24 real-space grid. Its
maximum solver relative residual was `9.99997e-9`; it wrote 64 full and 64 cut
Coulomb matrices, one finite-q response, and no legacy data. LibRPA read the
response, but the single-q trace-log integrand was `-173946.9229542`.

The anomaly is now localized to the Coulomb representation at the ABACUS to
LibRPA interface:

- The same-state Delta and LCAO-SOS responses differ by only `0.594%`; the
  in-grid SOS term agrees with LCAO-SOS to `3.16e-5` relative error. The Pulay
  and out-of-grid components reconstruct the Delta response to `9.30e-16`.
- Raising both `exx_ccp_rmesh_times` and `rpa_ccp_rmesh_times` from 1 to 2
  changes the Coulomb matrix by `1.24e-9`, the Delta response by `8.36e-13`,
  and the LCAO-SOS response by `2.38e-15`. This axis is rejected as a fix.
- Both the grid-Poisson and reader-v1 RI/Ewald Coulomb matrices are positive,
  but their Frobenius relative difference is `0.8133`. The eigenvalues of
  `V_reader^-1/2 V_grid V_reader^-1/2` span `1.09e-5` to `9.21e4`; they are not
  interchangeable representations.
- Whitening the same LCAO-SOS response with reader-v1 gives a trace-log of
  `-173330.3291`. Using the grid Coulomb gives `-2.6059259` instead.
- An independent LibRPA minimax-6 SOS calculation completed in 44.16 seconds
  with `EcRPA=-2.846971381648 Ha`. At the nearest q=21 frequency, `0.304680 Ha`,
  its trace-log is `-2.5831371`; the grid-whitened same-state LCAO-SOS value at
  `0.298137 Ha` is `-2.6059259`, a `0.87%` difference despite the `2.19%`
  frequency offset.

Therefore the large number is not a Delta solver, Pulay, out-of-grid,
`rmesh_times`, Coulomb-threshold, or negative-spectrum failure. ABACUS generates
the Sternheimer perturbation and response with the grid-Poisson Coulomb
representation, while the current LibRPA handoff applies the incompatible
reader-v1 RI/Ewald inverse square root. Solid L3 remains `INCOMPLETE` until the
producer and consumer use one definition-consistent representation.

## Failure Evidence

The first strict-2D replay failed because `input_dir` addressed a missing
`../dataset/band_out`. A fresh attempt with the preserved dataset root passed.

The first independent SOS attempt used minimax with `nfreq=1`, which GreenX
does not support. The second used `evenspaced`; LibRPA accepted the input, then
stopped because its conventional frequency-domain chi0 builder is not
implemented. The third used the source-supported minimax time-frequency route
with `nfreq=6` and passed. OML now rejects both earlier inputs before execution.
All three failed attempts remain in the scorecard for a six-point deduction.

## Next Evolution Axes

1. Make the solid Delta-ST handoff definition-consistent: either output and use
   the grid Coulomb representation, or transform the perturbation/response into
   the reader-v1 RI/Ewald representation. Repeat the pre-response metric gate
   before solving any response equations.
2. Run a small current-PyATB periodic 3D L3 case, including `stru_out` symmetry
   and full regular-grid state coverage.
3. Run a material strict-2D L3 case with full Ewald plus analytic head/wing.
   Cut Coulomb and `direct_mixed_fourier` remain diagnostic controls only.
4. After the solid interface is corrected, add full q/frequency and L4 k-grid,
   empty-state, real-space-grid, NAO, and ABFS convergence evidence.

`propose_evolution_candidate` can select one registered axis within a resource
budget, but it returns `PROPOSAL_ONLY`. Submission and route promotion remain
separate reviewed operations.
