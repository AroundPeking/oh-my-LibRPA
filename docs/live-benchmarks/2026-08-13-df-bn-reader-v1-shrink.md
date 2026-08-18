# DF BN reader-v1 symmetry/shrink live benchmark

Initial date: 2026-08-13

Updated: 2026-08-18

This benchmark validates the current OML controlled three-dimensional GW path
on `df_iopcas_ghj`. It now covers complete execution, reader-v1 interoperability,
PyATB state dimensions, scientific diagnostics, and three initial convergence
axes. It is not an accepted GW reference: frequency and screening-k-grid
convergence remain `FAIL`, and the packaged BN policy intentionally has no
promoted reference.

Strict 2D was not run. Its planning interface remains visible but execution is
blocked as `LIBRPA_070_STRICT_2D_INVALID` for the pinned LibRPA revision.

## Pinned stack and definition

| Component | Revision or fingerprint |
| --- | --- |
| ABACUS `master_ghj` | `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e` |
| LibRPA 0.7.0 | `dd169fa11fa920d580d4f39dc11e218a7f17f7b5` |
| PyATB `enable_head_wing` | `9fb9028c59b1dbaf9cf66965280961fc2225d9eb` |
| ABACUS executable SHA-256 | `56f445affd67756cea21381b05a45b4de5d9cbe8b0a061cdc80d91e37228fa6e` |
| LibRPA executable SHA-256 | `7af5e426933283a2aa08b8771692bc770506ce3b6f00ccf8545108cb8e58d3bc` |
| `get_diel.py` SHA-256 | `fea2d2e62a23aa86bd17b8a447dd58f078679fcf7b6db31b493fe2b13137e714` |
| `output_librpa.py` SHA-256 | `10986012071d6bb1d235874c5136e79b5b2f137e6b71bbd78a7cecdc9060305a` |

The ABACUS executable uses the exact pinned source with compiler vectorization
disabled because Intel oneAPI 2024.2 crashed while compiling
`ctrl_scf_lcao.cpp` at the original optimization settings. No ABACUS source
file was changed for this build.

The fixed route is `SCF -> PyATB -> NSCF -> preprocess -> LibRPA`, using:

- cubic three-dimensional BN, nonmagnetic and non-SOC;
- explicit reader-v1 Coulomb and LRI data;
- ABACUS `symmetry = 1`, with rotations reconstructed by LibRPA from
  `stru_out`; no legacy symmetry sidecars are copied;
- `exx_pca_threshold = 1e-3`, `shrink_abfs_pca_thr = 1e-1`, and
  `shrink_lu_inv_thr = 1e-3`;
- full auxiliary dimension `119`, shrunk dimension `34`;
- `use_shrink_abfs = t`, `use_shrink_chi = t`, head/wing enabled, and
  `use_fullcoul_exx = f`.

## PyATB state-count contract

PyATB diagonalizes the complete AO Hamiltonian, but the adapter must use the
ABACUS `band_out` state count consistently in PyATB `band_out`, `k_path_info`,
reader-v1 eigenvectors, and reader-v1 velocity matrices.

An earlier `nbands = 22` attempt,
`run-20260813T073552Z-3d810bc5d7`, let PyATB write 26 states. SCF, PyATB,
NSCF, and preprocessing passed, but LibRPA job `3004696` ended `FAILED`,
`ExitCode 1:0`, after 9 seconds with:

```text
k-BLACS eigenvector reader got inconsistent dimensions
```

OML retained the failed terminal snapshot and forced the scheduler gate to
FAIL. No stage was repeated in that run directory. The corrected adapter reads
22 from the ABACUS output, truncates every PyATB handoff payload consistently,
and completed the equivalent LibRPA route as job `3004837`.

## Adapter-v2 execution evidence

All 20 jobs below ended `COMPLETED` with `ExitCode 0:0`. Every run has five
immutable accepted stage receipts; the final LibRPA inspection has 4 PASS,
0 WARN, and 0 FAIL gates.

| Run and isolated setting | SCF | PyATB | NSCF | preprocess | LibRPA |
| --- | ---: | ---: | ---: | ---: | ---: |
| candidate: `k444`, `nbands=26`, `nfreq=16` (`run-20260813T075641Z-80efe676aa`) | `3004753` | `3004798` | `3004810` | `3004825` | `3004835` |
| frequency coarse: `k444`, `nbands=26`, `nfreq=12` (`run-20260813T075654Z-4b7c45dd32`) | `3004754` | `3004801` | `3004811` | `3004828` | `3004836` |
| empty-state coarse: `k444`, `nbands=22`, `nfreq=16` (`run-20260813T075658Z-92006c0096`) | `3004755` | `3004802` | `3004813` | `3004829` | `3004837` |
| screening coarse: `k333`, `nbands=26`, `nfreq=16` (`run-20260813T075701Z-e9ea71f6bc`) | `3004757` | `3004803` | `3004815` | `3004830` | `3004838` |

The candidate's immutable plan digest is
`3530018ac7dd6827ce15dccabd0b960d377fc216f0048502d7eb8b7888b111b7`.
Its final GW gap is `6.06097 eV`; QPE, finite-value, continuation, root, and
positive-gap diagnostics all pass.

Candidate artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| `KS_band_spin_1.dat` | `c7a54f6d5901440ef617157f52ee9563899d06151131082d6377a36c712420d2` |
| `EXX_band_spin_1.dat` | `201f1ff081023b0a382614ae78ebb6fbf27c08dc547cf46e857c2fabfc9ef8de` |
| `GW_band_spin_1.dat` | `a1d33f87d7fec065b7519a6701c79712702b046bceaf3ac94a995034b1c3d605` |
| `band_out` | `ce0bc5169f36e0d20fd7331e871fc633913d33d8dc07e22b9a4b33ebf9306d46` |
| `stru_out` | `e9b77fb9f6b28a45585f26ff607ce33111edb8d8102477f6367a3513eeb130eb` |

## Initial scientific convergence result

OML compares every `VBM-3` through `CBM+3` state at all three band-path
k points. An axis passes only when both the maximum GW-state change and the
fundamental-gap change are no larger than `0.05 eV`.

| Axis | Coarse -> fine | Coarse gap | Fine gap | Max GW-state change | Gap change | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `nfreq` | `12 -> 16` | `5.99677 eV` | `6.06097 eV` | `0.34178 eV` | `0.06420 eV` | FAIL |
| empty states | `nbands 22 -> 26` | `2.17812 eV` | `6.06097 eV` | `7.65755 eV` | `3.88285 eV` | superseded v4 verdict |
| screening k grid | `3x3x3 -> 4x4x4` | `-5.57335 eV` | `6.06097 eV` | not accepted | not accepted | FAIL |

The `k333` result fails before a numerical delta is accepted because its GW gap
is nonpositive. Two of the three band-path points are also outside that regular
screening grid. Earlier `k222` diagnostics gave `-139.25042 eV` with symmetry
and head/wing, `-132.67662 eV` with head/wing disabled, and the same
`-132.67662 eV` with both symmetry and head/wing disabled. A `k444` run with
both disabled recovered `6.01506 eV`. This rules out symmetry as the main cause
and does not support treating head/wing as the sole cause; the strong screening
grid and band-path dependence must be resolved by a dedicated convergence
campaign.

The original evaluator-v4 candidate report is
`science-f0e8a334a03635db0637`: all execution hard gates pass, but all three
required convergence axes fail. `score_case` therefore reports `75/100` and
verdict `FAIL`. The result is operationally complete but not scientifically
accepted. No reference will be promoted from it.

The v4 empty-state verdict used only the numerical-delta threshold. Evaluator
v6 supersedes that interpretation when the fine run contains the complete
finite state space of the fixed NAO basis.

## 2026-08-18 convergence follow-up

Four additional immutable runs changed one variable at a time from the
`k444`, `nbands=26`, `nfreq=16` baseline. All 20 jobs ended `COMPLETED` with
`ExitCode 0:0`; SCF, PyATB, NSCF, preprocess, and LibRPA inspections reported
3, 39, 3, 3, and 4 PASS gates respectively, with no failed gate.

| Run and isolated setting | SCF | PyATB | NSCF | preprocess | LibRPA | GW gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `nfreq=24` (`run-20260818T004928Z-1d90de4457`) | `3039799` | `3039807` | `3039814` | `3039899` | `3040193` | `6.00029 eV` |
| `nbands=24` (`run-20260818T004929Z-af50dd499c`) | `3039800` | `3039808` | `3039815` | `3039902` | `3040194` | `7.37080 eV` |
| `nbands=25` (`run-20260818T004931Z-2a2456f9e7`) | `3039801` | `3039809` | `3039816` | `3039906` | `3040195` | `6.13999 eV` |
| `k888` (`run-20260818T004932Z-4236d88430`) | `3039802` | `3039810` | `3039817` | `3039910` | `3040196` | `6.07034 eV` |

Evaluator v6 records the following one-axis comparisons:

| Axis | Coarse -> fine | Max GW-state change | Gap change | Result | Report |
| --- | --- | ---: | ---: | --- | --- |
| `nfreq` | `16 -> 24` | `0.33829 eV` | `0.06068 eV` | FAIL | `science-3a7834c651531d8f9142` |
| empty states | `24 -> 26` of basis dimension 26 | `2.37228 eV` | `1.30983 eV` | PASS endpoint | `science-00913c6716a5b2f0f70b` |
| empty states | `25 -> 26` of basis dimension 26 | `0.59081 eV` | `0.07902 eV` | PASS endpoint | `science-4031fb9591c3a38af825` |
| screening k grid | `4x4x4 -> 8x8x8` | `0.70466 eV` | `0.00937 eV` | FAIL | `science-9358e239c10a0b65de4a` |

The empty-state comparisons pass as `COMPLETE_BASIS_STATE_SPACE`, not because
their numerical changes are below `0.05 eV`. The fine run uses all 26 states in
the 26-dimensional `basis_wfc_out` space, so a request for more than 26 states
is impossible without changing the NAO basis. The large `25 -> 26` change is
retained evidence that the last available state matters. This endpoint closes
empty-state truncation only; it does not evaluate NAO basis completeness.

The `nfreq` axis still fails both the state and gap limits. The `k444 -> k888`
gap changes by only `0.00937 eV`, but the maximum GW-state change is
`0.70466 eV` and therefore fails. These exploratory runs do not form one
candidate with all fine settings, and no definition-matched reference exists,
so each v6 OML report remains `NOT_EVALUATED` overall. The campaign checkpoint
is execution `PASS` and scientific acceptance `FAIL`; reference promotion stays
blocked. The machine-readable record is
`benchmarks/live/df-bn-reader-v1-2026-08-18.json`.

## Independent consumer check

The same pinned LibRPA executable was run against the official frozen
`g0w0_band_abacus_BN_headwing_sym_kpara_shrink_v1_libri` dataset. Job
`3003038` completed, and both EXX and GW band tables matched the LibRPA 0.7.0
references with maximum absolute difference `0.0 eV`. This isolates the fixed
reader-v1/shrink consumer path; it does not make a newly produced dataset a
scientific reference.

## Retained evidence and next gates

All source bundles, runs, terminal logs, snapshots, scientific reports, and
negative diagnostics were retained. OML did not clean or overwrite any result.
The earlier no-shrink head/wing failure with one singular auxiliary direction
(`n_singular = 1`, `n_nonsingular = 118`, `n_abf = 119`) also remains retained.

The next three-dimensional campaign must extend `nfreq` beyond 24 and test
finer screening grids while keeping the band path and every non-axis definition
fixed. It must then build one candidate at all accepted fine settings. Empty
states must remain at the complete 26-state endpoint for this NAO basis; larger
state counts require a separate larger-NAO basis ladder. Only after the
frequency, screening-grid, combined-candidate, basis-completeness, and reference
gates pass can a reference be reviewed and promoted. Analytic continuation,
shrink thresholds, and strict 2D remain separate gates.
