---
name: abacus-librpa-gw
description: ABACUS + LibRPA GW workflow guidance and static input checks. Use when planning, preparing, or validating GW runs, including SCF/DF/NSCF chaining, librpa.in consistency, and safe run-directory setup.
---

# ABACUS + LibRPA GW

Execution order: `SCF -> DF (pyatb_librpa_df) -> NSCF -> LibRPA`.

## Required Checks

- Verify `nbands` consistency between `INPUT_scf` and `INPUT_nscf` under the same basis-size convention.
- Verify `librpa.in` is generated from the same ABACUS workflow chain.
- Verify the run is in a fresh directory to avoid stale-output contamination.

## Coupled Parameter Rule

If `use_shrink_abfs = t`, the following coupled parameters must exist:

- `rpa 1`
- `exx_pca_threshold 10`
- `shrink_abfs_pca_thr 1e-4`
- `shrink_lu_inv_thr 1e-3`
- `cs_inv_thr 1e-5`

## Output Requirement

For each recommendation, provide:

- why this change is needed
- what risk it addresses
- how to validate it with minimal cost
