---
name: oh-my-librpa-abacus-librpa
description: Stack-layer workflow for ABACUS -> LibRPA cases. Use when users provide ABACUS-style inputs such as INPUT/INPUT_scf/INPUT_nscf/KPT/STRU, or ask to run, validate, or debug LibRPA starting from ABACUS outputs. Route inside this layer to the existing GW, RPA, or Debug skills instead of mixing ABACUS conventions with FHI-aims workflows.
---

# oh-my-librpa-abacus-librpa

Treat this skill as the ABACUS-side router below the top-level `oh-my-librpa` entrypoint.

## Environment gate (mandatory first step)

- Detect host side before running commands.
- Confirm that the source-of-truth bundle is ABACUS-owned before applying ABACUS workflow assumptions.
- If the execution host and the source-data host differ, state which side is orchestration and which side is execution.

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

Do not treat these as FHI-aims ownership markers on their own:

- `geometry.in`
- `librpa.d/`
- `self_energy/`

If ABACUS canonical markers are absent and the case instead has stronger FHI-aims ownership markers such as `control.in`, `run_librpa_gw_aims_iophr.sh`, or explicit `qsgw_band` / `qsgw_band0` / `qsgw` / `qsgwa` intent, stop and hand the task to `skills/oh-my-librpa-fhi-aims-qsgw/`.

## Hard Separation Rule

- Do not reuse `control.in` or `geometry.in` conventions from FHI-aims when preparing ABACUS cases.
- Do not reuse `INPUT_scf`, `KPT_nscf`, or ABACUS helper-script expectations when handling FHI-aims cases.
- Do not use vague catch-all routing phrases that define a case only by not being ABACUS-owned.
- If a bundle mixes both families, stop and ask which upstream stack owns the source of truth before editing anything.

## Shared Safety Rules

- Create a fresh run directory before real execution.
- Audit copied bundles instead of blindly reusing stale outputs.
- Run static checks before submission.
- Keep the conversation operational and report `what was done`, `what was observed`, and `what is next`.
