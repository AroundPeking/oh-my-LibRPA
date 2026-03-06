---
name: abacus-librpa-rpa
description: ABACUS + LibRPA RPA workflow guidance with focus on dielectric setup, frequency grids, and convergence-oriented static checks. Use when preparing or troubleshooting RPA calculations.
---

# ABACUS + LibRPA RPA

Primary objective: get stable and reproducible RPA results first, then optimize performance and scale.

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
