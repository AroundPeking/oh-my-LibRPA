---
name: abacus-librpa-gw
description: ABACUS + LibRPA GW workflow guidance and static input checks. Use when planning, preparing, or validating GW runs, including SCF/DF/NSCF chaining, librpa.in consistency, and safe run-directory setup.
---

# ABACUS + LibRPA GW

Execution order depends on system type:

- `molecule`: `SCF -> NSCF/band preparation as needed -> LibRPA` (skip `pyatb`)
- `solid`: `SCF -> DF (pyatb_librpa_df) -> NSCF -> preprocess_abacus_for_librpa_band.py -> LibRPA`

## Required Checks

- Verify `nbands` consistency between `INPUT_scf` and `INPUT_nscf` under the same basis-size convention.
- Verify `librpa.in` is generated from the same ABACUS workflow chain.
- Verify the run is in a fresh directory to avoid stale-output contamination.

## Default `librpa.in` Preset for GW

For GW requests, set:

- `task = g0w0_band`
- `nfreq = 16`
- `option_dielect_func = 3`
- `replace_w_head = t`
- `use_scalapack_gw_wc = t`
- `use_scalapack_ecrpa = t`
- `parallel_routing = libri`
- `vq_threshold = 0`
- `sqrt_coulomb_threshold = 0`
- `use_fullcoul_exx = t`
- `output_gw_sigc_mat_rf = t`
- `libri_chi0_threshold_C = 1e-4`
- `libri_chi0_threshold_G = 1e-5`
- `libri_exx_threshold_V = 1e-1`
- `libri_exx_threshold_C = 1e-4`
- `libri_exx_threshold_D = 1e-4`
- `libri_g0w0_threshold_C = 1e-5`
- `libri_g0w0_threshold_G = 1e-5`
- `libri_g0w0_threshold_Wc = 1e-6`

## System-Type Branches for GW

### Molecule

- Set `KPT` to `1 1 1`
- Add `gamma_only 1` to `INPUT_scf`
- Use official ABACUS input names from the ABACUS input reference
- Do not run `pyatb`
- Set `replace_w_head = f`

### Solid

- Ask the user how many k-points to use in `KPT`; default to `8 8 8`
- Require a band path in `KPT_nscf`
- After SCF, run `pyatb` to generate the `pyatb_librpa_df` directory
- Then run NSCF
- Then run `preprocess_abacus_for_librpa_band.py`
- Then run `LibRPA`

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
