# FHI-Aims + LibRPA G0W0-Band Guide

This guide defines the periodic-solid `FHI-aims + LibRPA` single-shot GW route. Its filename retains the older `g0w0_band` name for discoverability; LibRPA 0.7.0 input uses `task = g0w0`.

It is intentionally separate from the QSGW route.

## Scope

Use this route when all of the following are true:

- the workflow is FHI-aims-owned
- the target is a single-shot `g0w0` calculation
- the system is a periodic solid

Do not use this route for:

- `qsgw_band`
- `qsgw_band0`
- `qsgw`
- `qsgwa`
- molecules
- 2D systems

Use the QSGW route for QSGW-family tasks, and use the build skill when the request is about compiling FHI-aims itself.

## Core Defaults

The default workflow is always two-stage:

- `run_aims.sh`
- `run_librpa.sh`

The default division of labor is:

- `FHI-aims`: MPI-heavy
- `LibRPA`: OpenMP-heavy

Do not default to a single script that chains both stages together.

## Geometry and Control Inputs

For periodic solids:

- `geometry.in` is in Angstrom
- use `lattice_vector`
- atomic coordinates may use `atom` or `atom_frac`

If `control.in` is missing:

- generate a periodic-solid skeleton from `geometry.in`
- source the species blocks from `defaults_2020/intermediate_gw`
- then patch the global header to match the target calculation

## `librpa.in` Baseline

This route stays focused on `g0w0`. A compact baseline is:

```text
task = g0w0
option_dielect_func = 3
replace_w_head = t
use_scalapack_gw_wc = t
parallel_routing = libri
```

Set `nfreq` to the same integer used by `frequency_points` in `control.in`, unless a trusted old reference case explicitly overrides that pairing.

Keep thresholds and special switches aligned with a trusted old reference case when one exists.

## ABACUS Comparison Rule

These runs are often prepared as a cross-check against `ABACUS + LibRPA`. When an ABACUS comparison case exists, preserve:

- structure
- `k_grid`
- band path
- number of points on each band segment

Comparability wins over inventing a different FHI-aims-only band path.

## Route Boundary

This route owns:

- periodic-solid `FHI-aims + LibRPA`
- single-shot `g0w0`
- stage-only preparation
- fresh-run preparation

This route does not own:

- QSGW-family FHI-aims tasks
- FHI-aims build or repair work
- ABACUS-side GW workflows
