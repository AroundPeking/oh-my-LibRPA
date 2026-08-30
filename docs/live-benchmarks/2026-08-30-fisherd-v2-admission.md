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
- The v2 score is `60.5/100`, verdict `INCOMPLETE`. No route was promoted.

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
response, but the single-q trace-log integrand was `-173946.9229542`. A one-axis
`sqrt_coulomb_threshold=0` versus `1e-8` A/B made no change. Matrix inspection
found a positive Coulomb spectrum and a negative-semidefinite response, so the
reader and small-eigenvalue filter are not the immediate fault. Current-revision
same-state LCAO-SOS and complete q/frequency checks remain required.

## Failure Evidence

The first strict-2D replay failed because `input_dir` addressed a missing
`../dataset/band_out`. A fresh attempt with the preserved dataset root passed.
The failed attempt remains in the scorecard as a two-point deduction.

## Next Evolution Axes

1. Run the current Si case with the same-state LCAO-SOS diagnostic enabled and
   compare matrices before changing physics or basis inputs.
2. Run a small current-PyATB periodic 3D L3 case, including `stru_out` symmetry
   and full regular-grid state coverage.
3. Run a material strict-2D L3 case with full Ewald plus analytic head/wing.
   Cut Coulomb and `direct_mixed_fourier` remain diagnostic controls only.
4. Add L4 frequency, q/k-grid, empty-state, NAO, and ABFS convergence evidence.

`propose_evolution_candidate` can select one registered axis within a resource
budget, but it returns `PROPOSAL_ONLY`. Submission and route promotion remain
separate reviewed operations.
