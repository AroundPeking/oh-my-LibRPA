# df_dcu strict-2D SOS-RPA admission checkpoint

Route: `strict_2d_sos_rpa`
Profile: `abacus-librpa-2026-09-02-strict2d-sos-rpa-v1`
LibRPA: `c87103df00b772ddbfc21597884c2787cf685037`
Executable SHA-256: `0ca485dde5833dd190709c59d4689c263c2344041f2c71be4bc33c7e0b5da3c9`

## RESULT

MoS2 N=8 job `21833983` and N=12 job `21834156` both passed the bounded
LibRPA-only functional and numerical smoke. The route reuses the validated
reader-v1 ABACUS/PyATB producer, full 2D Ewald Coulomb, and
`librpa_2d_coulomb_head.dat`; there was no ABACUS/PyATB rerun. Both runs used
`task=rpa`, `nfreq=16`, analytic head/wing `qavg`, no `head_only`, four MPI
ranks with `mpirun -ppn 1`, and 30 OpenMP/MKL threads per rank.

N=8 gave Gamma `-0.06924276799691 Ha` and total `-1.268385066102 Ha`. N=12
gave Gamma `-0.03075665041071 Ha` and total `-1.242737105060 Ha`. The N=12/N=8
Gamma ratio was `0.4441857439`, close to the 2D q-cell area ratio `4/9`; this
is a consistency observation, not a fitted law.

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

## REMAINING

This is a functional smoke only. N=8 and N=12 are two meshes, so there is no convergence exponent claim and no N^-3 claim. The route remains `TESTABLE`.
At least three controlled in-plane meshes, with the physical definition held
fixed, are required before assessing the asymptotic k-point convergence law or
promotion beyond admission testing.
