# Fisherd Current-Stack Periodic 3D GW Benchmark

Date: 2026-09-03

Route: `periodic_3d_gw`

Verdict: `PASS_WITH_DEGENERATE_GAUGE_CAVEAT` for the L3 interface replay;
scientific acceptance is `NOT_EVALUATED`, and reference promotion remains
`BLOCKED`.

## Scope

This replay runs the small bulk-BN symmetry/shrink regression from a current
ABACUS producer through current LibRPA. It checks reader-v1 serialization,
embedded symmetry, SCF, NSCF, band preprocessing, QP-grid evaluation, band
continuation, and MPI/OpenMP reproducibility. It is not a converged BN GW
calculation: the screening grid is `2x2x2`, `nfreq = 8`, and no NAO or ABFS
basis ladder is present.

The fixed producer uses `ecutwfc = 100 Ry`, 26 states in the complete
26-function NAO space, `exx_pca_threshold = 1e-3`,
`shrink_abfs_pca_thr = 1e-1`, and Massidda singularity correction. The STRU,
both ONCV pseudopotentials, and both NAO files are pinned by SHA-256 in the
machine-readable receipt.

The case has `replace_w_head = false`, so PyATB is pinned as part of the stack
but is not executed in this no-head-replacement regression.

## Pinned Stack

| Component | Revision or SHA-256 |
| --- | --- |
| ABACUS `master_ghj` | `1648a8a344427ae1b6394912bf677c4a20e053f2` |
| LibRPA `master_ghj` | `7e40c5bbf735a78aa15fa589ca2468fec2e2427b` |
| PyATB `enable_head_wing` | `9fb9028c59b1dbaf9cf66965280961fc2225d9eb` |
| ABACUS executable | `7aba04e711e68bc654dc737ed5c1a330ddfe62a7ea2305c4d78b6edad5347b5a` |
| LibRPA executable | `cefc8f33c2a99085db3dd07a0f7110c17fc5176270cc8a2157ac17e4c1aa8f60` |
| band preprocessor | `c8b9ed860c9e47752632425d87ffe6eb7df6473a69edaaccb08a4d516fd3cec5` |

Retained live evidence is under
`/home/ghj/oml-benchmarks/20260903-periodic-3d-gw/runs/bn-sym-shrink-current`.
Its machine-generated receipt has SHA-256
`407345ef7b859f30118ce019a74a57896abc02437021cbe86fd557173b6fc08b`.

## Producer And Handoff

The current ABACUS SCF completed with exit code 0 in `56.14 s`, reached
`-347.8644069358 eV`, and used at most `2653440 KiB`. `stru_out` contains 24
symmetry operations. The LibRPA dataset contains no `symrot_*` or
`irreducible_sector.txt` sidecar; LibRPA reconstructs symmetry from
`stru_out`.

The handoff uses only reader-v1 data. The KS header reports marker `-12345679`,
kind `28`, three irreducible k points, 26 states, and a 26-function basis. The
three Coulomb files report marker `-20129433` and a 34-function shrunk
auxiliary basis.

The current NSCF completed with `symmetry = -1` and three Gamma-X path points.
The current preprocessor then generated `band_kpath_info`, three band
eigenvalue/eigenvector pairs, and three band-vxc files. Both stages returned
exit code 0.

## Consumer Checks

Current LibRPA completed the full QP-grid and band path with both `1 MPI x 48
OpenMP` and `4 MPI x 1 OpenMP`. All three `KS/EXX/GW_band_spin_1.dat` tables
are numerically identical between the two layouts. The regular-grid QP tables
are also identical. The two runs took `1.25 s` and `1.55 s`, respectively.

Against the official frozen LibRPA regression output, the current producer's
eight regular-grid QP tables contain 208 states and differ by at most
`0.00001 eV`, below the `0.0001 eV` interface threshold. The grid QP gap is
`7.08896 eV` (`VBM = 9.71387 eV`, `CBM = 16.80283 eV`). This value is a
regression observable, not a converged material result.

As an independent consumer control, current LibRPA run on the complete
official frozen dataset reproduces its KS, EXX, and GW band files exactly:
the maximum difference is `0.0 eV` for every table.

## Degenerate-Gauge Finding

The newly produced KS band eigenvalues reproduce the official frozen KS band
exactly. The underlying eigenvectors differ by unitary rotations inside exact
degenerate manifolds; at the Gamma-X midpoint the largest fitted relative
subspace residual is only `2.69e-9`.

Despite the identical KS spectrum, a direct current-end-to-end comparison with
the historical band files reaches `89.24885 eV` for EXX and `126.67942 eV`
for GW. The worst entry is midpoint band 24. The mismatch is confined to
degenerate state groups. Current output preserves the 20 detected degeneracies
to `0.00001 eV` for EXX and exactly for GW, while the historical files split
some of the same groups strongly.

Two mixing controls show that replacing only the band eigenvectors is not a
valid repair: official grid data plus current band data still differs from the
official EXX/GW files by `5.14608/4.76818 eV`; current grid data plus official
band data retains the current five-decimal output. The SCF and band gauges must
therefore be treated as one definition-matched handoff.

This is classified as `BLOCKED_DEGENERATE_GAUGE_MISMATCH`. It is not a
reader-v1 failure because the QP grid passes, the frozen consumer control is
exact, and current parallel layouts agree. It is also not accepted as a
scientific pass: OML must not silently average, reorder, or compare individual
members of a historical degenerate manifold as if state identity were fixed.

## Acceptance Boundary

| Gate | Result |
| --- | --- |
| current source and executable identity | PASS |
| current ABACUS SCF/NSCF/preprocess | PASS |
| reader-v1 and embedded-symmetry handoff | PASS |
| current LibRPA on official frozen dataset | PASS |
| current `1x48` versus `4x1` reproducibility | PASS |
| historical end-to-end band reference | `BLOCKED_DEGENERATE_GAUGE_MISMATCH` |
| scientific convergence | `NOT_EVALUATED` |
| reference promotion | BLOCKED |

The earlier BN campaign still reports `0.33829 eV` maximum GW-state change for
`nfreq 16 -> 24` and `0.70466 eV` for screening grid `4x4x4 -> 8x8x8`. This
small replay cannot supersede those failed convergence gates, so the benchmark
matrix remains `PARTIAL_REFERENCE`.

## Next Gates

1. Add a fixture that applies controlled unitary rotations to protected
   degenerate SCF and band manifolds.
2. Require a gauge-invariant band observable, or diagonalize the self-energy
   within each protected degenerate subspace before assigning state energies.
3. Repeat frequency and screening-grid convergence on one current-stack
   candidate.
4. Complete NAO and ABFS basis ladders before reference review.

The machine-readable record is
`benchmarks/live/fisherd-periodic-3d-gw-current-2026-09-03.json`.
