---
name: abacus-pyatb-librpa-stack
description: Bootstrap, validate, and repair a fresh ABACUS + PYATB + LibRPA environment on Ubuntu/WSL or Linux, including oneAPI, Python venv, auxiliary libraries, smoke tests, and runtime diagnosis.
---

# ABACUS + PYATB + LibRPA Stack

Use this skill when the user is asking to install, compile, configure, or repair the software stack itself rather than a single GW/RPA case.

## Scope

This stack includes:

- `ABACUS`
- `LibRPA`
- `PYATB`
- helper dependencies commonly needed in practice:
  - Intel oneAPI (`icpx`, `ifx`, MPI, MKL)
  - Python venv + `numpy/scipy/mpi4py/matplotlib/pybind11`
  - `Eigen`
  - `ELPA`
  - `Libxc`
  - `LibRI`, `LibComm`, `cereal` from the LibRPA tree

## First Move

Before proposing changes, classify the request into one of two branches:

1. `fresh install`
2. `repair existing environment`

Then run the installed helper first:

```bash
bash oh-my-librpa/scripts/stack_env_doctor.sh [--env-script <path>] [--case-dir <path>]
```

Use its output as the baseline instead of guessing from memory.

## Canonical Reference

Use `oh-my-librpa/docs/guide/abacus-pyatb-librpa-stack.md` as the canonical build order.

That guide is derived from the maintained Ubuntu/WSL installation note and should be preferred over ad-hoc command fragments.

## Mandatory Build Order

When the user wants a full fresh stack, keep this order:

1. system packages: `git`, `cmake`, `python3-dev`, `python3-venv`
2. Intel oneAPI base + HPC toolkits
3. Python virtual environment for PYATB-related Python packages
4. `LibRPA` source checkout + submodules
5. `Eigen` for `PYATB`
6. `PYATB`
7. `GCC` (only if ABACUS build truly needs a custom GCC)
8. `ELPA`
9. `Libxc`
10. `ABACUS`
11. environment script export
12. smoke validation

Do not reorder this casually.

## Known Critical Fixes

Always remember these known issues from the maintained note:

- Newer oneAPI releases rename old compilers:
  - `icpc -> icpx`
  - `ifort -> ifx`
  - `mpiicpc -> mpiicpx`
  - `mpiifort -> mpiifx`
- On Ubuntu 23+ / 24+, prefer Python venv instead of system `pip` because of externally-managed Python protection.
- For `PYATB`, `siteconfig.py` should use `icpx` and a real Eigen include path.
- For `LibRPA`, update `LibComm` / `LibRI` submodules before building.
- For the known `LibRI` issue in this workflow, check whether `this->period` must be replaced by `this->lri.period` in `RPA.hpp`.
- For `ABACUS`, use out-of-source CMake builds and be ready to add Intel math/runtime libraries when linking with `ELPA` / `Libxc`.
- If custom GCC is being built, clear oneAPI compiler environment first before configuring GCC.
- If `chi0_main.exe` fails with `libqsgw.so` missing, inspect `LD_LIBRARY_PATH` or prefer a matching build-tree/runtime library layout.

## Environment Output Policy

If the stack is broken, report fixes in this order:

- `symptom`
- `most_likely_root_cause`
- `minimal_fix_action`
- `verification_command`

Keep repair actions narrow. Do not rewrite the whole environment if a single missing path, venv, or runtime library explains the problem.

## Smoke Validation Protocol

After installation or repair, run the smoke helper when a case directory is available:

```bash
bash oh-my-librpa/scripts/stack_smoke_test.sh \
  --case-dir <case_dir> \
  [--env-script <path>] \
  [--abacus-bin <path>] \
  [--librpa-bin <path>]
```

Interpret the smoke test as follows:

- `ABACUS` success: SCF markers exist
- `PYATB` success: `pyatb_librpa_df/band_out` and `KS_eigenvector_*.dat` exist
- `LibRPA` success: rank-0 output reaches `Timer stop:  total.`

If the full periodic GW chain is not available, it is acceptable to:

- validate `ABACUS -> PYATB` on the active case
- validate `LibRPA` on an exported `input_librpa` bundle in the same smoke run

State clearly when the result is a `stack smoke test` rather than a `full numerical end-to-end GW reproduction`.

## Handoff Back To Workflow Skills

Only hand the user back to `oh-my-librpa` / `abacus-librpa-gw` / `abacus-librpa-rpa` after:

- `stack_env_doctor.sh` reports no hard failures, and
- the required smoke path has passed.
