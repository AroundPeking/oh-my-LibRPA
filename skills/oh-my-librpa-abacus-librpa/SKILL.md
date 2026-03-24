---
name: oh-my-librpa-abacus-librpa
description: Stack-layer workflow for ABACUS -> LibRPA cases. Use when users provide ABACUS-style inputs such as INPUT/INPUT_scf/INPUT_nscf/KPT/STRU, or ask to run, validate, or debug LibRPA starting from ABACUS outputs. Route inside this layer to the existing GW, RPA, or Debug skills instead of mixing ABACUS conventions with FHI-aims workflows.
---

# oh-my-librpa-abacus-librpa

Treat this skill as the ABACUS-side router below the top-level `oh-my-librpa` entrypoint.

## Core Behavior

- Confirm the case is ABACUS-based before proceeding.
- Classify the task as:
  - `GW`
  - `RPA`
  - `Debug`
- Classify the system as:
  - `molecule`
  - `solid`
  - `2D`
- Keep the ABACUS workflow isolated from any FHI-aims-specific file conventions.

## Routing Rules

- `GW` -> follow `skills/abacus-librpa-gw/`
- `RPA` -> follow `skills/abacus-librpa-rpa/`
- `Debug` or user-provided failure logs -> follow `skills/abacus-librpa-debug/`

## Intake Rules

Treat these as ABACUS markers:

- `INPUT`, `INPUT_scf`, `INPUT_nscf`
- `KPT`, `KPT_scf`, `KPT_nscf`
- `STRU`
- `.orb`, `.abfs`, `.upf`
- `running_scf.log`, `running_nscf.log`, `band_out`, `OUT.ABACUS/`

If these markers are absent and the case instead revolves around `control.in` and `run_librpa_gw_aims_iophr.sh`, stop and hand the task to `skills/oh-my-librpa-fhi-aims-qsgw/`.

## Hard Separation Rule

- Do not reuse `control.in` or `geometry.in` conventions from FHI-aims when preparing ABACUS cases.
- Do not reuse `INPUT_scf`, `KPT_nscf`, or ABACUS helper-script expectations when handling FHI-aims cases.
- If a bundle mixes both families, stop and explain the mismatch before editing anything.

## Shared Safety Rules

- Create a fresh run directory before real execution.
- Audit copied bundles instead of blindly reusing stale outputs.
- Run static checks before submission.
- Keep the conversation operational and report `what was done`, `what was observed`, and `what is next`.
