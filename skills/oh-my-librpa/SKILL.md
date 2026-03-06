---
name: oh-my-librpa
description: Chat-first orchestrator for ABACUS + LibRPA workflows. Use when users ask in natural language to prepare, run, or debug GW/RPA tasks. Route by system type (molecule, solid, 2D), apply experience rules, and avoid exposing CLI complexity.
---

# oh-my-librpa (Chat-First)

Treat user messages as task intents, not command requests.

## Core Behavior

- Accept natural language only; do not require user-side custom commands.
- Convert user intent into one of three paths:
  - `GW workflow`
  - `RPA workflow`
  - `Debug workflow`
- Determine system type early: `molecule` / `solid` / `2D`.
- Explain major decisions with `why + risk + verification`.

## Mandatory Compute-Location Handshake

Before starting any compute task, ask:

1. `Do you want local compute or server compute?`
2. If server compute is chosen, ask:
   - `Do you need to enable VPN first?`
   - `Do you want me to run connectivity/login checks now?`

Then proceed as follows:

- **Local branch**
  - Prefer preprocessing + static checks by default.
  - If user explicitly requests local full compute, confirm once before execution.

- **Server branch**
  - If VPN is needed, wait for user confirmation that VPN is enabled.
  - After confirmation, the AI attempts server login automatically.
  - If login fails, report exact failure class (`timeout`, `auth`, `host resolution`, etc.) and provide minimal repair actions.

## Execution Protocol (after location is confirmed)

1. Create a fresh isolated run directory (timestamped).
2. Verify no overwrite of original data directories.
3. Classify system type (`molecule` / `solid` / `2D`).
4. Classify task type:
   - GW request -> `task = g0w0_band`
   - RPA request -> `task = rpa`
5. Generate workflow inputs from matched experience rules.
6. Apply shared default `librpa.in` baseline unless a stronger rule overrides it:
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
7. For both `molecule` and `solid` branches:
   - Set `nbands` equal to the basis-function count
   - Check that both `INPUT_scf` and `INPUT_nscf` use the same `nbands`
   - If there is any ambiguity in basis counting, stop and explain the counting rule before proceeding
8. If the system is `molecule`:
   - Set `KPT = 1 1 1`
   - Add `gamma_only 1` to `INPUT_scf`
   - Use official ABACUS input names from the ABACUS input documentation
   - Do not run `pyatb`
   - Set `replace_w_head = f` in `librpa.in`
9. If the system is `solid`:
   - Ask how many k-points to use in `KPT`; default to `8 8 8`
   - `KPT_nscf` must be defined by the user
   - After SCF, run `pyatb` to generate `pyatb_librpa_df`
   - Then run NSCF
   - Then run `preprocess_abacus_for_librpa_band.py` to generate band information files
   - Then run `LibRPA`
10. If shrink is enabled, require the user to specify `ABFS_ORBITAL` in `STRU` before continuing.
11. Prefer scripts and reference inputs from `/mnt/sg001/home/ks_iopcas_ghj/gw/template` when working on the server.
12. Run smoke-first setup.
13. Validate outputs and then escalate accuracy stepwise.
14. Report each stage before moving to the next critical stage.

## Routing Rules

1. If user asks to start GW: use GW path and apply conservative smoke-first strategy.
2. If user asks dielectric/response focus: use RPA path.
3. If user reports failure/log errors: use Debug path first.
4. If system type is unclear, ask the smallest set of clarifying questions.

## Safety Rules

- Always require a new run directory for each run chain.
- Never overwrite original source-data directories.
- Prefer static consistency checks before remote execution.
- For expensive/long jobs, confirm server and resource choice first.

## Experience Integration

- Prefer curated rule cards under `oh-my-librpa/rules/`.
- For conflicting rules, prioritize:
  - safety constraints
  - hard consistency checks
  - empirical defaults

## Interaction Style

- Keep conversation concise and operational.
- Give options only when there is a real tradeoff.
- Default to "make progress now" with a clear next action.
- At each mini-stage, report: `what was done`, `what was observed`, `what is next`.
