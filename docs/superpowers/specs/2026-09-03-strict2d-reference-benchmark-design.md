# Strict-2D Reference Benchmark Design

## Goal

Promote the validated `strict_2d_sos_rpa` route using a reproducible four-mesh
MoS2 reference benchmark. Convergence means agreement with the accepted
N=8/10/12/16 reference behavior within declared tolerances; it does not require
an invariant adjacent-mesh energy or a claimed asymptotic exponent.

## Scope Boundary

This benchmark accepts only strict-2D SOS-RPA total energies calculated with
the pinned reader-v1, full-2D-Ewald, analytic qavg head/wing route. It does not
accept strict-2D GW, a different material, a different producer, or the
diagnostic no-head/wing calculation as a physical result.

The existing profile and manifest remain immutable L3 admission records. A new
profile records the reviewed L4 promotion and points to the benchmark that
justifies it.

## Benchmark Identity

The benchmark records:

- exact ABACUS, LibRPA, and PyATB revisions plus the LibRPA executable hash;
- MoS2 structure, pseudopotential, orbital, auxiliary-basis, and input hashes;
- the mesh-dependent KPT and `bz_sampling_out` hashes;
- N=8/10/12/16 qavg Gamma and total energies;
- the matched no-head/wing controls and their immutable validation receipts.

A material or software identity mismatch is a hard failure, not an energy
comparison.

## Scientific Acceptance

The route passes L4 when every mandatory gate passes:

1. all four reference meshes and all four finite-q controls are present;
2. each reference energy agrees within the registered absolute tolerance;
3. `N^2 |E_Gamma|` has relative span no greater than `1.0e-3`;
4. the N=12 to N=16 total-energy change is no greater than `8.0 mHa`;
5. the fixed N^-3 diagnostic RMS is no greater than `0.5 mHa`;
6. the accepted extrapolated-limit span is no greater than `2.5 mHa`;
7. matched non-Gamma contributions differ by no more than `1.0e-9 Ha`.

The evaluator recomputes the fixed-power and free-power least-squares fits
from the four total energies. The rounded fit summary stored in the admission
manifest must agree with the recomputed values within its receipt tolerance.

The benchmark keeps `forbid_convergence_exponent_claim=true`. Passing means
operational k-mesh convergence for this reference definition, not proof of a
universal asymptotic power law.

## MCP Surface

`inspect_route_benchmark` returns the immutable benchmark policy.
`evaluate_route_benchmark` loads a registered admission manifest, recomputes
all derived metrics, and returns individual gates plus a non-compensating
PASS/FAIL verdict. A failed hard gate cannot be repaired by a score.

## Benchmark Program

The first benchmark matrix separates route validation from material-class
coverage. Rows without accepted evidence stay `REFERENCE_PENDING`; missing
values are never inferred from neighboring materials. The next rows after
strict-2D SOS-RPA are strict-2D GW, molecular Delta-ST RPA, solid Delta-ST RPA,
and representative 3D, perovskite, transition-metal-oxide, and altermagnetic
GW cases.
