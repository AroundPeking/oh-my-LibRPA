# DF BN reader-v1 symmetry/shrink live benchmark

Date: 2026-08-13

This benchmark validates the current OML controlled-execution path on the
`df_iopcas_ghj` Slurm cluster. It is a workflow and format-compatibility
benchmark. It is not yet a scientific GW accuracy reference.

## Pinned stack

| Component | Revision or fingerprint |
| --- | --- |
| ABACUS `master_ghj` | `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e` |
| LibRPA 0.7.0 | `dd169fa11fa920d580d4f39dc11e218a7f17f7b5` |
| PyATB `enable_head_wing` | `9fb9028c59b1dbaf9cf66965280961fc2225d9eb` |
| ABACUS executable SHA-256 | `56f445affd67756cea21381b05a45b4de5d9cbe8b0a061cdc80d91e37228fa6e` |
| LibRPA executable SHA-256 | `7af5e426933283a2aa08b8771692bc770506ce3b6f00ccf8545108cb8e58d3bc` |

The ABACUS executable uses the exact pinned source with compiler vectorization
disabled because Intel oneAPI 2024.2 crashed while compiling
`ctrl_scf_lcao.cpp` at the original optimization settings. No ABACUS source
file was changed for this build.

## Controlled case

- System: 3D cubic BN, nonmagnetic, non-SOC, `2 x 2 x 2` regular k grid.
- Route: `SCF -> PyATB -> NSCF -> preprocess -> LibRPA`.
- Format: explicit reader-v1 for Coulomb and LRI coefficient files.
- Symmetry: ABACUS `symmetry = 1` producer; LibRPA rebuilds rotations from
  `stru_out`; legacy copied symmetry sidecars are not required.
- Shrink producer: `exx_pca_threshold = 1e-3`,
  `shrink_abfs_pca_thr = 1e-1`, `shrink_lu_inv_thr = 1e-3`.
- Shrink consumer: `use_shrink_abfs = t`, `use_shrink_chi = t`, with explicit
  `v1_Cs_shrinked_data_`, `v1_shrink_sinvS_`, and
  `basis_aux_shrink_out` names.
- EXX Coulomb definition: `use_fullcoul_exx = f`, matching the LibRPA 0.7.0
  default and official ABACUS GW regressions.
- Auxiliary dimensions: full `119`, shrink `34`.

The input-stage report contained 14 PASS, 0 WARN, and 0 FAIL gates before the
dedicated EXX-definition gate was added. The final controlled baseline's
immutable plan digest was
`f67cf43e0fa5ffbc2747f65ec52267126486a520f8ef19659126aa81821d1533`.

## Stage evidence

Run: `run-20260813T033132Z-9f810b6522`

| Stage | Slurm job | Elapsed | OML inspection |
| --- | ---: | ---: | --- |
| SCF | `3003134` | 58 s | 3 PASS |
| PyATB | `3003136` | 17 s | 38 PASS |
| NSCF | `3003139` | 3 s | 3 PASS |
| preprocess | `3003140` | 1 s | 3 PASS |
| LibRPA | `3003141` | 11 s | 4 PASS |

All five immutable attempts passed. The final OML score is 55/100 with verdict
`INCOMPLETE`: provenance, pinned versions, stage lineage, duplicate protection,
stage completion, and finite output passed; diagnosis and numerical/scientific
validity remain explicitly not evaluated.

Final artifact SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| `KS_band_spin_1.dat` | `7d061a0bf7b9d8a7a38a5a9e1e83557aab3a85b7675595009a658a41b6b2b930` |
| `EXX_band_spin_1.dat` | `0abae042770d3a13813917ad2261f45b7ea12e0aca687c7932464f6058834bf9` |
| `GW_band_spin_1.dat` | `5e899992b12078b120cf870324e956daa77a81ad5b8d093fa42f4b267f02ef0f` |
| `stru_out` | `e9b77fb9f6b28a45585f26ff607ce33111edb8d8102477f6367a3513eeb130eb` |

## Consumer isolation check

The pinned LibRPA executable was also run against the official frozen dataset
for `g0w0_band_abacus_BN_headwing_sym_kpara_shrink_v1_libri`. Slurm job
`3003038` completed successfully. Both `EXX_band_spin_1.dat` and
`GW_band_spin_1.dat` matched the LibRPA 0.7.0 references element by element;
the maximum absolute difference was `0.0 eV`.

This confirms the fixed LibRPA reader-v1/shrink consumer path. It does not prove
that a freshly produced ABACUS dataset must match an older frozen dataset,
because producer revisions and calculation definitions can differ.

An earlier complete workflow run (`run-20260813T025321Z-9c7c0755b3`) explicitly
set `use_fullcoul_exx = t`, while LibRPA 0.7.0 defaults to `false` and all seven
official ABACUS GW regression inputs leave it disabled. With the current
producer data and only `use_fullcoul_exx` changed to `f`, 66 of 78 EXX entries
and 65 of 78 GW entries agreed with the frozen reference within `1e-4 eV`; the
remaining 12 or 13 entries reflect producer-data differences. OML templates now use
`use_fullcoul_exx = f`. Full-Coulomb EXX is an explicit physical-definition
override, not a general default.

The final controlled baseline differs from the frozen reference by at most
`0.443 eV` over the first four GW states at each of the three band-path k
points. This is recorded as an unresolved producer/reference difference, not a
scientific acceptance result.

## Harness efficiency evidence

The first full SCF snapshot took `73.8 s`. Reusing the previous immutable
snapshot with checksum-verified hard links reduced subsequent PyATB, NSCF,
preprocess, and LibRPA inspection times to `2.3 s`, `3.0 s`, `2.2 s`, and
`2.9 s`. Only about `214 kB` of unique data was added by the final LibRPA
snapshot. Read-only version and executable fingerprint checks also retry up to
three transient observation timeouts; Slurm submission commands are never
automatically retried.

## Negative evidence retained

The no-shrink `exx_pca_threshold = 1e-3` run reached LibRPA but stopped because
the option-3 head/wing path found one singular auxiliary-basis direction:
`n_singular = 1`, `n_nonsingular = 118`, `n_abf = 119`. Disabling the ELPA
square-root backend did not change that result. Directly changing
`exx_pca_threshold` to `1e-1` made the route finish, but it is not treated as a
replacement for the explicit full-plus-shrink protocol.

## Remaining scientific gates

OML 0.3 now defines the low-energy window as `VBM-3` through `CBM+3`, a
definition-matched regression threshold of `0.001 eV`, and independent
`nfreq`, empty-state, and screening-k-grid convergence thresholds of `0.05 eV`
for both GW states and the fundamental gap. The packaged BN policy deliberately
contains no accepted reference yet, so this historical run remains
`NOT_EVALUATED` rather than being promoted automatically.

Before this case can become a PASS scientific benchmark, the three convergence
axes must pass and a candidate reference must be reviewed and promoted in a
repository commit. NAO/ABFS completeness, analytic-continuation alternatives,
and shrink thresholds remain later independent campaigns. Large
corrections in high unoccupied states are present in the upstream program
regression itself, so a universal absolute-energy cutoff would create false
failures. Numerical gates must be state-window and benchmark specific.
