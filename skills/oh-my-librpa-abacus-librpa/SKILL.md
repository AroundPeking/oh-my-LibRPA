---
name: oh-my-librpa-abacus-librpa
description: Use when ABACUS inputs, reader-v1 handoffs, producer outputs, or ABACUS-to-LibRPA failures are involved, especially with INPUT, KPT, STRU, GW, RPA, or Debug cases.
---

# oh-my-librpa-abacus-librpa

Treat this skill as the ABACUS-side router below the top-level `oh-my-librpa` entrypoint.

## Environment gate (mandatory first step)

- Detect host side before running commands.
- Confirm that the source-of-truth bundle is ABACUS-owned before applying ABACUS workflow assumptions.
- If the execution host and the source-data host differ, state which side is orchestration and which side is execution.

## Core Behavior

- Confirm the case is ABACUS-based before proceeding.
- Apply `skills/abacus-librpa-version-guard/` before any compute, audit, debug, restart, or result interpretation. Physics runs are server-side by default and must match the pinned ABACUS `master_ghj`, LibRPA `v0.7.0`, and when used PyATB `enable_head_wing` profile unless a reproduction exception is recorded.
- Apply `$librpa-openmp-mkl-threading` before preparing, submitting, restarting, or diagnosing the LibRPA stage. This is mandatory even when the upstream producer is ABACUS.
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
- `geometry.in` when it appears only as a supporting structure or plotting file alongside ABACUS inputs

Do not treat these as FHI-aims ownership markers on their own:

- `geometry.in`
- `librpa.d/`
- `self_energy/`

If ABACUS canonical markers are absent and the case instead has stronger FHI-aims ownership markers such as `control.in`, `run_librpa_gw_aims_iophr.sh`, or explicit `qsgw_band` / `qsgw_band0` / `qsgw` / `qsgwa` intent, stop and hand the task to `skills/oh-my-librpa-fhi-aims-qsgw/`.

## Hard Separation Rule

- Do not reuse `control.in` or `geometry.in` conventions from FHI-aims when preparing ABACUS cases.
- Do not treat `geometry.in` by itself as proof that a case belongs to FHI-aims; some ABACUS bundles carry it for interop or plotting.
- Do not reuse `INPUT_scf`, `KPT_nscf`, or ABACUS helper-script expectations when handling FHI-aims cases.
- Do not use vague catch-all routing phrases that define a case only by not being ABACUS-owned.
- If a bundle mixes both families, stop and ask which upstream stack owns the source of truth before editing anything.

## Shared Safety Rules

- Create a fresh run directory before real execution.
- Audit copied bundles instead of blindly reusing stale outputs.
- Check server executable provenance and source SHAs against the MCP profile before submission; do not rely on unverified binaries.
- Run static checks before submission.
- When editing ABACUS source, INPUT metadata, reader-v1 producer output, or the ABACUS/LibRPA handoff, **REQUIRED SUB-SKILL:** use `abacus-development-conventions`. Split implementation fragments must use responsibility-based names; do not use opaque sequence names such as `impl_00` or `impl_01`.
- Treat an INPUT rename as one contract across the public keyword, `Input_Item`, the backing `Input_para`/runtime member, defaults, serialized keys, generated documentation, tests, and every runtime read. Keep each identifier in that contract within 15 characters, and do not leave a long internal member after shortening the public spelling.
- For any rename, inspect the writer/producer and every reader/consumer, run a repository-wide `rg` check for old and new spellings, and verify that only intentional compatibility aliases remain. Check duplicate registration, case variants, default and unknown-key behavior, and restart/serialization paths when present.
- When resolving a PR conflict, inspect both sides and the producer/consumer contract; never resolve by blindly taking `ours` or `theirs`. Remove every conflict marker, then repeat the static and residual-name checks.
- When source, INPUT metadata, or documentation changes, inspect Read the Docs jobs separately (including `abacus-develop` and `abacus-rtd` when configured); a green code check does not close the documentation gate.
- Keep ABACUS producer MPI/OpenMP/MKL settings separate from the LibRPA stage. For one LibRPA MPI rank per node, require `OMP_NUM_THREADS == MKL_NUM_THREADS == SLURM_CPUS_PER_TASK`; never inherit an unexplained `MKL_NUM_THREADS=1`.
- On any server, confirm that ABACUS and LibRPA were built against the same latest LibRI with the nearest-fix bugfix. If the host has a site-specific LibRI root, record it in the host profile instead of assuming a cross-server default.
- Keep the conversation operational and report `what was done`, `what was observed`, and `what is next`.
