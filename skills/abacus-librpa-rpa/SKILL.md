---
name: abacus-librpa-rpa
description: ABACUS + LibRPA RPA workflow guidance with focus on dielectric setup, frequency grids, and convergence-oriented static checks. Use when preparing or troubleshooting RPA calculations.
---

# ABACUS + LibRPA RPA

Primary objective: get stable and reproducible RPA results first, then optimize performance and scale.

## Default `librpa.in` Preset for RPA

For RPA requests, set:

- `task = rpa`
- `nfreq = 16`
- `option_dielect_func = 3`
- `replace_w_head = t`
- `use_scalapack_gw_wc = t`
- `use_scalapack_ecrpa = t`
- `parallel_routing = libri`
- `use_soc = 0/1` according to the INPUT spin/SOC state
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

## Recommended Flow

- Start with a small-system smoke case to validate the full input chain.
- Increase `nfreq`, k-point density, and band cutoffs step by step.

## Static Checklist

- Ensure paths come from one consistent SCF/NSCF source chain.
- Ensure frequency-grid parameters are self-consistent.
- Ensure key file paths are not stitched from unrelated directories.

## Output Requirement

- Prioritize minimal viable fixes.
- Change one major variable per iteration to reduce coupled uncertainty.
