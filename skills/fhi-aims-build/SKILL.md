---
name: fhi-aims-build
description: Use when the user asks to install, configure, compile, rebuild, or debug a FHI-aims build, especially when CMake reports missing ELSI content, MPI wrapper mismatches, or stale compiler and MKL cache paths.
---

# FHI-aims Build

> **Entry point:** this is a sub-route of `oh-my-librpa`. Load
> `oh-my-librpa` first — it fixes the version profile, PP/NAO/ABFS identity,
> k-mesh and spin/symmetry contract that this file assumes. If you arrived
> here without loading it, go back and load it before acting.

Use this skill for FHI-aims source-tree setup and compilation, not for QSGW/G0W0 case preparation.

## Scope

- installing or rebuilding FHI-aims
- fixing `cmake` configure failures
- fixing `make` compile or link failures
- diagnosing vendored or external dependency issues such as ELSI

If the request is about preparing or running an FHI-aims + LibRPA case instead of building the executable itself, hand the task back to `skills/oh-my-librpa-fhi-aims-qsgw/`.

## First classification

1. Identify the source tree, build directory, host, and exact failing command.
2. Classify the failure layer:
   - configure-time
   - compile-time
   - link-time
3. Determine dependency mode:
   - vendored `external_libraries/*`
   - external packages such as `EXTERNAL_ELSI_PATH`
4. If the build runs on a remote host from `~/.ssh/config`, also use `ghj-remote-ssh`.
5. If the host is `df_iopcas_ghj`, read [references/df-fhi-aims-build.md](references/df-fhi-aims-build.md).

## Required checks before any fix

- Determine whether the source tree is a real git clone:
  - inspect `.git`
  - inspect `.gitmodules`
- For vendored ELSI, verify that `external_libraries/elsi_interface/CMakeLists.txt` exists and the directory is not empty.
- Compare MPI wrappers and cache flags:
  - `which mpif90 mpiifort mpiifx ifort ifx icx icpx gcc gfortran`
  - `mpif90 -show`
- Validate the compiler names and library roots stored in:
  - `initial_cache*.cmake`
  - `CMakeCache.txt`
- If `cmake` already ran, capture the first real configure blocker from:
  - `CMakeError.log`
  - the failing try-compile output

## Repair order

1. Fix the missing vendored dependency or switch to a verified external dependency.
2. Align MPI wrappers with the compiler flags in the cache.
3. Replace stale compiler names such as `icc` and `icpc`.
4. Replace stale library roots such as old MKL paths.
5. Clean `CMakeCache.txt` and `CMakeFiles/`.
6. Re-run `cmake`.
7. Only after configure passes, re-run `make`.
8. If a new failure appears, report that first real blocker instead of stacking more speculative edits.

## Common patterns

- `.gitmodules` without `.git` means `GIT_SUBMODULE=ON` cannot populate submodules automatically.
- An empty vendored dependency directory counts as missing content.
- `mpif90` can resolve to GNU even on oneAPI hosts. Never trust the wrapper name alone.
- Old Intel cache files often hardcode:
  - `icc`
  - `icpc`
  - `/opt/intel/...`
  paths that no longer exist.
- Before rewriting a large cache file, probe the actual compiler triplet with one-file test compiles.

## Verification

- prove `cmake` passes from a clean build directory
- prove `make` reaches the expected binary
- record:
  - the host
  - the repair applied
  - the final binary path
- if the fix is host-specific, add or update a reference document instead of bloating this main skill
