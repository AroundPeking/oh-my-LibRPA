# ks_ghj_3 `~/gw` Sampling Results (Round 1)

## Collection Metadata

- Time: 2026-03-06 12:26 (GMT+8)
- Source: `ks_ghj_3:~/gw`
- Index file: `data/gw-index-20260306-122643.tsv`
- Parameter snapshot: `data/param-snapshots/params-20260306-122643.txt`

## Dataset Size

- Total lines (including header): 278
- Actual cases: 277
  - `GW_CASE`: 258
  - `ABACUS_CASE`: 19

Interpretation: this dataset is GW-heavy, matching the first-release focus of `oh-my-LibRPA`.

## Top Directory Buckets

Top-level buckets by case count:

- `AlAs`: 31
- `shrink_test`: 26
- `reg_test`: 25
- `GaAs`: 22
- `MgO`: 19
- `abacus_input`: 15
- `CdS`: 15
- `nonlin_soc_gw`: 14

Interpretation: `shrink_test`, `reg_test`, and `nonlin_soc_gw` are strong candidates for next rule extraction.

## Key Parameter Snapshot

### `nfreq`

- 16 (176 occurrences)
- 6 (22 occurrences)
- 8 (14 occurrences)
- 24 (13 occurrences)

Interpretation: `nfreq=16` is the strongest default mode for smoke runs.

### `use_shrink_abfs`

- `t` (156 occurrences)
- `f` (9 occurrences)

Interpretation: shrink-abfs should be treated as a primary workflow lane, not a corner case.

### `rpa`

- `1` (208 occurrences)

Interpretation: this aligns with existing experience and can be enforced as a strong check.

### Typical Coupled Thresholds

- `exx_pca_threshold`: 10 (367 occurrences)
- `shrink_lu_inv_thr`: 1e-3 (74 occurrences)
- `cs_inv_thr`: 1e-5 (51 occurrences)
- `shrink_abfs_pca_thr`: 1e-6 (92 occurrences), next is 1e-4 (14 occurrences)

Interpretation: a practical default set is `exx_pca_threshold=10`, `shrink_lu_inv_thr=1e-3`, `cs_inv_thr=1e-5`; `shrink_abfs_pca_thr` still needs system-level branching.

## Direct Actions for oh-my-LibRPA

1. Add recommendation levels in `check_consistency.sh`:
   - hard constraints: `rpa=1` + complete coupled keys
   - recommendation: `nfreq=16` for smoke

2. Add two rule-card families:
   - `shrink-abfs-default-lane`
   - `nfreq-smoke-ladder` (16 -> 24/32 escalation)

3. Next-round focus:
   - `shrink_test/*`
   - `reg_test/*`
   - `nonlin_soc_gw/*`
   Then map failure keywords (including `stod`) to repair actions.
