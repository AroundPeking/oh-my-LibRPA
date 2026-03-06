---
name: abacus-librpa-gw
description: ABACUS + LibRPA GW workflow guidance and static input checks. Use when planning, preparing, or validating GW runs, including SCF/DF/NSCF chaining, librpa.in consistency, and safe run-directory setup.
---

# ABACUS + LibRPA GW

Execution order depends on system type:

- `molecule`: `SCF -> NSCF/band preparation as needed -> LibRPA` (skip `pyatb`)
- `solid`: `SCF -> DF (pyatb_librpa_df) -> NSCF -> preprocess_abacus_for_librpa_band.py -> LibRPA`

## Required Checks

- Verify `nbands` in both `INPUT_scf` and `INPUT_nscf` is equal to the basis-function count.
- Verify `INPUT_scf` and `INPUT_nscf` use the same `nbands`.
- Verify spin/SOC settings are aligned across files:
  - collinear spin without SOC -> `nspin = 2`, `lspinorb = 0`
  - noncollinear with SOC -> `nspin = 4`, `lspinorb = 1`
- Verify `get_diel.py` uses matching `nspin` and `use_soc`.
- Verify `preprocess_abacus_for_librpa_band.py` uses matching `use_soc`.
- Verify `librpa.in` uses matching `use_soc = 0/1`.
- Verify `librpa.in` is generated from the same ABACUS workflow chain.
- Verify the run is in a fresh directory to avoid stale-output contamination.
- Prefer server-side scripts and reference inputs from `/mnt/sg001/home/ks_iopcas_ghj/gw/template` when available.
- Recognize the canonical file bundle from server examples:
  - `INPUT`, `INPUT_scf`, `INPUT_nscf`
  - `KPT`, `KPT_scf`, `KPT_nscf`
  - `STRU`, `geometry.in`, `librpa.in`
  - `get_diel.py`, `perform.sh`, `preprocess_abacus_for_librpa_band.py`, `run_abacus.sh`
  - `.orb`, `.abfs`, `.upf`

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

## Spin and SOC Branches

Use the following alignment for spin-sensitive GW workflows:

- Collinear spin, no SOC:
  - `INPUT`: `nspin = 2`, `lspinorb = 0`
  - `get_diel.py`: set matching `nspin` and `use_soc = False`
  - `preprocess_abacus_for_librpa_band.py`: set `use_soc = False`
  - `librpa.in`: set `use_soc = 0`

- Noncollinear with SOC:
  - `INPUT`: `nspin = 4`, `lspinorb = 1`
  - `get_diel.py`: set matching `nspin` and `use_soc = True`
  - `preprocess_abacus_for_librpa_band.py`: set `use_soc = True`
  - `librpa.in`: set `use_soc = 1`

## System-Type Branches for GW

### Molecule

- Set `KPT` to `1 1 1`
- Add `gamma_only 1` to `INPUT_scf`
- Use official ABACUS input names from the ABACUS input reference
- Do not run `pyatb`
- Set `replace_w_head = f`

### Solid

- Ask the user how many k-points to use in `KPT`; default to `8 8 8`
- `KPT_nscf` must be provided by the user
- After SCF, run `pyatb` to generate the `pyatb_librpa_df` directory
- Then run NSCF
- Then run `preprocess_abacus_for_librpa_band.py`
- Then run `LibRPA`

## Default Shrink Strategy

Use shrink by default:

- `use_shrink_abfs = t`
- `rpa 1`
- `exx_pca_threshold 10`
- `shrink_abfs_pca_thr 1e-4`
- `shrink_lu_inv_thr 1e-3`
- `cs_inv_thr 1e-5`

Interpretation:

- `shrink_abfs_pca_thr` controls the size of the compressed auxiliary basis; default to `1e-4`.
- `shrink_lu_inv_thr` is used to control inversion-error handling for the output `sinvS`; default to `1e-3`.
- `exx_pca_threshold = 10` means the large-basis path expects external input when shrink is enabled.
- When shrink is enabled, `ABFS_ORBITAL` in `STRU` must be specified by the user.
- If the user provides `.abfs` files, use those filenames directly in `ABFS_ORBITAL` entries.
- Server examples include names such as `Ga_str_4s4p3d2f2g_1e-4.abfs` and `As_str_4s4p3d2f2g_1e-4.abfs`.

## Output Requirement

For each recommendation, provide:

- why this change is needed
- what risk it addresses
- how to validate it with minimal cost
