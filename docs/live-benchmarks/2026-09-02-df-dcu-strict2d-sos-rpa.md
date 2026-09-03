# df_dcu strict-2D SOS-RPA admission checkpoint

Route: `strict_2d_sos_rpa`
Profile: `abacus-librpa-2026-09-02-strict2d-sos-rpa-v1`
LibRPA: `c87103df00b772ddbfc21597884c2787cf685037`
Executable SHA-256: `0ca485dde5833dd190709c59d4689c263c2344041f2c71be4bc33c7e0b5da3c9`

## RESULT

MoS2 qavg jobs N=8 `21833983`, N=10 `21836052`, N=12 `21834156`, and N=16
`21836055` all passed the bounded LibRPA-only functional and numerical
validation. The route reuses the validated
reader-v1 ABACUS/PyATB producer, full 2D Ewald Coulomb, and
`librpa_2d_coulomb_head.dat`; there was no ABACUS/PyATB rerun. All four runs used
`task=rpa`, `nfreq=16`, analytic head/wing `qavg`, no `head_only`, four MPI
ranks with `mpirun -ppn 1`, and 30 OpenMP/MKL threads per rank.

The qavg `(Gamma, total)` energies in Ha are N=8
`(-0.06924276799691, -1.268385066102)`, N=10
`(-0.04430281538195, -1.250904354656)`, N=12
`(-0.03075665041071, -1.242737105060)`, and N=16
`(-0.01729559985264, -1.235513727806)`. The Gamma contribution scales close
to the 2D q-cell area. The four-point free-power fit gives `p=2.642`; the
fixed N^-3 fit has RMS `0.399888 mHa`. These are diagnostics, not an accepted
asymptotic exponent.

Matched no-head/wing jobs N=8 `21836051`, N=10 `21836053`, N=12 `21836121`,
and N=16 `21836057` reproduce every non-Gamma contribution within `0.6 nHa`,
so the control isolates the Gamma treatment. Its raw Gamma contribution is
complex, with imaginary parts between `0.416` and `1.177 mHa`; it is therefore
recorded only as a diagnostic failure-mode control and is not an alternative
physical route.

## GATES

- Scheduler/application/process: `normal`, all paths under `/work1`, 4 nodes,
  4 MPI ranks, application and wrapper exit 0, real MPI world-size check pass.
- Input: reader-v1, full 2D Ewald, `task=rpa`, `nfreq=16`, qavg head/wing, no
  `head_only`, immutable producer reuse, and duplicate-job check.
- Numerical: exactly 16 qavg records, weight error below `1e-6`, finite
  energies, per-q and summed imaginary energy below `1e-8 Ha`, q-sum equal to
  total within the registered mixed tolerance, LU info zero, and physical
  anti-Hermitian residual below `1e-12` scale.
- Parallel consistency: N=8 MPI Gamma/total agree with the singleton baseline
  to about `1e-14/1e-12 Ha`.

The source and binary passed local C++/MPI plus GreenX tests and remote C++/MPI
tests, including an explicit four-rank Intel MPI head/wing regression.

## ACCEPTANCE

Reviewed profile `abacus-librpa-2026-09-03-strict2d-sos-rpa-v2` uses
benchmark `strict2d-sos-rpa-mos2-qavg-v1` to mark this exact route `ENABLED`.
The reference-bounded rule accepts the observed four-mesh behavior when the
registered energies, `N^2 |E_Gamma|` scaling, N=12 to N=16 endpoint change,
fit residual, extrapolated-limit span, and finite-q control all stay within
their hard tolerances. This is operational k-mesh convergence for the pinned
MoS2 definition, with no asymptotic exponent claim, and is not strict-2D GW
acceptance.

## REMAINING

The four meshes establish functional and numerical route consistency, but do
not yet establish the asymptotic convergence law. The adjacent effective
exponents drift from `2.732` to `2.518`, and the tested extrapolations span
about `2.09 mHa`. There is therefore no N^-3 claim. A stable asymptotic power
law is not required by the reviewed reference-bounded acceptance criterion;
denser meshes remain useful as diagnostics or for a new material definition,
not as a blocker for this pinned SOS-RPA route.
