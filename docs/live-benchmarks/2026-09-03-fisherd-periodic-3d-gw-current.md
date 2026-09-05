# Fisherd Current-Stack Periodic 3D GW Benchmark

Date: 2026-09-03

Last verified: 2026-09-06

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

The L3 replay evidence is under
`/home/ghj/oml-benchmarks/20260903-periodic-3d-gw/runs/bn-sym-shrink-current`.
Its machine-generated receipt has SHA-256
`407345ef7b859f30118ce019a74a57896abc02437021cbe86fd557173b6fc08b`.
The current-stack convergence follow-up is retained separately under
`/home/ghj/oml-benchmarks/20260903-periodic-3d-gw/runs/bn-k444-current-20260903`.

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

## Current-Stack Convergence Follow-Up

A fresh `4x4x4` producer was generated with the same structure, PP, NAO,
26-state complete basis, reader-v1, shrink, symmetry, Massidda correction, and
current executables. Its SCF completed in `54.91 s` with `2743792 KiB` maximum
RSS and produced eight irreducible q points, eight full and eight cut reader-v1
Coulomb files, and no legacy symmetry sidecars. NSCF and preprocessing also
completed.

The frequency ladder fixes `tfgrids_type = minimax`,
`n_params_anacon = 6`, `option_qpe_solver = 0`, and
`use_qpe_adaptive_damp = false`. Only `nfreq` changes:

| Pair | Gap change | Maximum GW change in VBM-3 through CBM+3 | Result |
| --- | ---: | ---: | --- |
| `16 -> 24` | `0.02747 eV` | `0.51179 eV` | FAIL |
| `24 -> 32` | `0.00021 eV` | `0.04440 eV` | PASS |

All three runs are finite and have no explicit QP-solver failure. The accepted
`24 -> 32` pair has gaps `6.27089 -> 6.27110 eV`; its worst low-energy state
is Gamma band 1. This accepts only the current BN frequency axis under the
explicit six-parameter continuation contract. It does not establish a generic
Padé setting for molecules, strict-2D GW, SOC, or other material classes.

The high-unoccupied region is reported separately: bands 9-26 change by up to
`1.44653 eV`, at X band 26. This does not enter the declared low-energy gate,
but it remains visible in the evidence rather than being called converged.

Three negative controls explain why the continuation settings are part of the
scientific definition. Using all frequency points as Padé parameters gives a
`0.35045 eV` low-energy change and a `90.05310 eV` high-state root switch.
Twelve parameters gives a `0.56241 eV` low-energy change and a non-finite
high-energy state at 32 frequencies. Switching the all-point calculation to
the perturbative QP solver still gives `0.38074 eV` in the low-energy window
and a `1996.89089 eV` high-state excursion. A stable gap alone would have
missed every one of these failures.

The matched `2x2x2 -> 4x4x4` screening-grid pair fixes `nfreq = 24` and
`n_params_anacon = 6`. It fails strongly: the low-energy maximum is
`139.78139 eV`, and the fixed-frontier gap changes from `-132.38050` to
`6.27089 eV`. The worst state is the off-grid Gamma-X midpoint band 5, whose
EXX value already changes from `-106.05359` to `22.28204 eV`. Therefore the
coarse-grid anomaly is an interpolation/screening-grid failure, not a
frequency or QP-solver failure.

The same current-stack definition was then extended through `4x4x4`,
`6x6x6`, `8x8x8`, `10x10x10`, `12x12x12`, and `14x14x14`. Every producer, reader-v1
handoff, LibRPA run, and QP diagnostic completed without a non-finite value or
an explicit QP-solver failure. The application cost rose from `21.23 s` and
`475020 KiB` at `4x4x4` to `9657 s` and `8785672 KiB` at `14x14x14`.

| Screening pair | Gap change | Maximum GW change in VBM-3 through CBM+3 | Result |
| --- | ---: | ---: | --- |
| `4x4x4 -> 6x6x6` | `0.45210 eV` | `0.53403 eV` | FAIL |
| `6x6x6 -> 8x8x8` | `0.06140 eV` | `0.05378 eV` | FAIL |
| `8x8x8 -> 10x10x10` | `0.03805 eV` | `0.05357 eV` | FAIL |
| `10x10x10 -> 12x12x12` | `0.04850 eV` | `0.06091 eV` | FAIL |
| `12x12x12 -> 14x14x14` | `0.02590 eV` | `0.03279 eV` | PASS |

The `10x10x10 -> 12x12x12` pair passes the gap component but fails the
statewise component at `0.06091 eV`. The next `12x12x12 -> 14x14x14` pair is
the first adjacent fine-grid pass: its gap changes from `5.89064` to
`5.86474 eV`, and the largest low-energy GW change is `0.03279 eV` at the
Gamma-X midpoint band 1. Across that pair KS and EXX change by at most
`0.00001` and `0.00007 eV`. This accepts the BN screening-grid axis under the
declared continuation and state-window definition; it does not establish
transferability to another material or complete the missing basis and
physical-reference gates.

The `14x14x14` LibRPA application completed with exit code 0 and an explicit
success marker in `2:40:57`, using at most `8785672 KiB`. All 33 applicable
validation gates pass, three are explicitly skipped, stderr is empty, and the
three band tables contain no non-finite value or QP failure. The comparison
report SHA-256 is
`523b0efeee0630aa78957cc3369fb7f6d3357f8c7f2d57d70795b110fa3bdeba`.
Its `.oml` plan and execution receipts were reconstructed after completion and
are explicitly marked `posthoc_current-stack_benchmark_reconstruction`; they
are audit evidence, not proof that this run was launched by the MCP execution
service.

Three setup incidents remain recorded rather than discarded. The first SCF
SSH observation returned 255 while the existing remote process continued and
finished, so it was not rerun. The first dataset assembly expected `vxc_out`
at the wrong path; its failed directories were preserved before the producer's
`OUT.ABACUS/vxc_out.dat` was staged explicitly as `vxc_out`. The first LibRPA
duplicate guard matched its own broad process query; no application was
launched by that attempt, and the corrected exact-name guard launched one
process.

During this ladder, the `10x10x10` consumer audit copy of `KPT_scf` was found
to contain the old `8x8x8` template even though `bz_sampling_out` and all
numerical data came from the correct `10x10x10` producer. Commit `814169d`
adds gate `dataset.screening_grid`, which rejects that mismatch. The old audit
file and receipts remain preserved; replacing only the audit copy and
regenerating receipts changed no numerical output.

## Current Symmetry/Full-Q Control

Two fresh Fisherd runs were prepared and executed through the bounded MCP
sequence, one stage at a time. They share the same bulk-BN structure, PP, NAO,
26-state complete basis, `4x4x4` screening grid, reader-v1 format, shrink
settings, `nfreq = 24`, six-parameter continuation, and no head/wing
replacement. The scientific-definition comparison permits only the route and
symmetry fields to differ: ABACUS SCF `symmetry`, LibRPA
`use_symmetry_exx`/`use_symmetry_gw`, and the two corresponding route labels.

The resulting comparison is `8-q symmetry -> 64-q full-q`. The symmetry run
contains 24 operations in `stru_out` and eight full plus eight cut Coulomb
files; the full-q run contains 64 of each. Neither run contains legacy
symmetry sidecars. All SCF, NSCF, preprocessing, and LibRPA stages passed their
application and artifact gates. Fisherd jobs were `1537/1539/1541/1543` for
the symmetry route and `1538/1540/1542/1544` for full-q.

MCP scientific evaluator v9 applies a dedicated `0.0001 eV` symmetry
tolerance to KS, EXX, GW, and the fundamental gap. Across all 24 states in the
declared VBM-3 through CBM+3 window, every maximum difference and the gap
change are `0.0 eV`; both gaps are `6.27089 eV`. An additional complete-basis
audit compares all 78 path states: occupations and KS agree exactly, while
the largest EXX and GW differences are both `1e-5 eV`, with no non-finite
value or explicit QP failure.

This control is `PASS_REFERENCE_BOUNDED` only for BN `4x4x4`, no head/wing,
and the pinned current stack. The aggregate MCP report remains
`NOT_EVALUATED`: regression has no physical reference and the same report
lineage still lacks `nfreq`, empty-state, and screening-grid axes. Profile
`abacus-librpa-2026-09-06-v6` records the bounded control while keeping
periodic 3D GW at L3 `EXPERIMENTAL`; it does not claim transfer, basis
convergence, or L4 acceptance.

Two setup failures are preserved as operational evidence. SSH banners first
corrupted binary transfer protocols; a marked noninteractive-session guard
fixed transfer without changing interactive Fisherd shells. The first
controlled preparation then found no administrator-created remote root. It
created no scheduler job, and OML now records this class of retained run as
`PREPARE_FAILED` rather than `RUN_PREPARED`.

## Acceptance Boundary

| Gate | Result |
| --- | --- |
| current source and executable identity | PASS |
| current ABACUS SCF/NSCF/preprocess | PASS |
| reader-v1 and embedded-symmetry handoff | PASS |
| current LibRPA on official frozen dataset | PASS |
| current `1x48` versus `4x1` reproducibility | PASS |
| current `nfreq 24 -> 32`, fixed six-parameter Padé | PASS |
| current BN `8-q symmetry -> 64-q full-q`, no head/wing | `PASS_REFERENCE_BOUNDED` (`1e-5 eV` complete-basis maximum) |
| current screening grid `2x2x2 -> 4x4x4` | FAIL |
| current screening grid `10x10x10 -> 12x12x12` | FAIL (`0.06091 eV`) |
| current screening grid `12x12x12 -> 14x14x14` | PASS (`0.03279 eV`, gap `0.02590 eV`) |
| historical end-to-end band reference | `BLOCKED_DEGENERATE_GAUGE_MISMATCH` |
| scientific convergence | `NOT_EVALUATED` |
| reference promotion | BLOCKED |

The current frequency and screening-grid axes each have one passing adjacent
pair. Profile `abacus-librpa-2026-09-06-v5` preserves those two accepted BN
contracts. Profile `abacus-librpa-2026-09-06-v6` additionally records the
bounded symmetry/full-q control while keeping periodic 3D GW `EXPERIMENTAL`
at L3. Because no accepted empty-state, NAO or ABFS ladder, transfer case, or
definition-matched physical reference is present in one complete lineage, the
benchmark matrix remains `PARTIAL_REFERENCE` and scientific acceptance remains
`NOT_EVALUATED`.

## Next Gates

1. Require a gauge-invariant band observable, or diagonalize the self-energy
   within each protected degenerate subspace before assigning state energies.
2. Test the accepted `12x12x12 -> 14x14x14` screening rule on Si and MgO
   without inheriting BN-specific convergence as a universal default.
3. Complete empty-state, NAO, and ABFS ladders before reference review.

The machine-readable records are
`benchmarks/live/fisherd-periodic-3d-gw-current-2026-09-03.json` and
`benchmarks/live/fisherd-periodic-3d-gw-symmetry-fullq-2026-09-06.json`.
