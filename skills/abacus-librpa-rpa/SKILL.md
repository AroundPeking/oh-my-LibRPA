---
name: abacus-librpa-rpa
description: ABACUS + LibRPA RPA workflow guidance with conservative defaults and static checks. Use when preparing or troubleshooting RPA calculations.
---

# ABACUS + LibRPA RPA

Before any RPA compute, restart, audit, debug, or result interpretation, apply `skills/abacus-librpa-version-guard/`. Real ABACUS+LibRPA physics compute must run on a server by default, and ABACUS/LibRPA executable commits must be checked against local `master_ghj` unless this is a recorded feature-branch or old-version reproduction.

Primary objective: get stable and reproducible RPA results first, then optimize performance and scale.

## Execution Order

RPA uses a shorter path than GW:

- `SCF -> LibRPA`

Do not use the GW-only dielectric-function path for RPA:

- do not run `pyatb`
- do not run NSCF for the standard RPA route
- do not run `preprocess_abacus_for_librpa_band.py`
- do not require `KPT_nscf`

## Default `librpa.in` Preset for RPA

For RPA requests, set:

- `task = rpa`
- `nfreq = 16`
- `use_scalapack_gw_wc = t`
- `use_scalapack_ecrpa = t`
- `parallel_routing = libri`
- `use_soc = 0/1` according to the INPUT spin/SOC state
- `vq_threshold = 0`
- `sqrt_coulomb_threshold = 0`
- `use_fullcoul_exx = t`
- `libri_chi0_threshold_C = 1e-4`
- `libri_chi0_threshold_G = 1e-5`
- `libri_exx_threshold_V = 1e-1`
- `libri_exx_threshold_C = 1e-4`
- `libri_exx_threshold_D = 1e-4`

## Recommended Flow

- Start with a small-system smoke case to validate the SCF -> LibRPA chain.
- Increase `nfreq` and related accuracy settings step by step.
- For full execution, prefer the installed `run_rpa_workflow.sh` runner so stage execution, verification, and reporting stay in one flow.

## Static Checklist

- Verify server execution and ABACUS/LibRPA version provenance before queue submission.
- Ensure paths come from one consistent SCF source chain.
- Ensure no GW-only preprocessing step is inserted into the RPA route.
- Ensure frequency-grid parameters are self-consistent.
- Ensure key file paths are not stitched from unrelated directories.

## Output Requirement

- Prioritize minimal viable fixes.
- Change one major variable per iteration to reduce coupled uncertainty.
- Call the installed `report_stage.sh` helper to update both task Markdown logs and send the user a short stage summary after each stage.
