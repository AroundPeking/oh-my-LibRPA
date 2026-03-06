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

## Mandatory File-Intake Handshake

Before starting any compute task, ask the user to provide files first when available.

Treat uploaded files as the primary source of truth.

Classify user-provided files into one of these groups:

- `structure files`: `STRU`, `cif`, `xyz`, `geometry.in`
- `input bundle`: `INPUT`, `INPUT_scf`, `INPUT_nscf`, `KPT`, `KPT_scf`, `KPT_nscf`, `librpa.in`
- `workflow scripts`: `get_diel.py`, `perform.sh`, `preprocess_abacus_for_librpa_band.py`, `run_abacus.sh`
- `basis/pseudopotential assets`: `.orb`, `.abfs`, `.upf`
- `logs/results`: output files, error logs, `band_out`, generated band data
- `archives`: `zip`, `tar.gz`

If the user provides files:

- `structure files` -> generate or complete the workflow
- `input bundle` -> audit and patch instead of rewriting blindly
- `basis/pseudopotential assets` -> use them directly as authoritative inputs for basis and auxiliary-basis setup
- `logs/results` -> enter debug mode first
- `archives` -> unpack and classify before proceeding

When the user provides `.abfs` files, treat them as direct candidates for `ABFS_ORBITAL` entries in `STRU`.

Canonical server-side template bundle is under `/mnt/sg001/home/ks_iopcas_ghj/gw/template` and includes:

- `INPUT`, `INPUT_scf`, `INPUT_nscf`
- `KPT`, `KPT_scf`, `KPT_nscf`
- `STRU`, `geometry.in`, `librpa.in`
- `get_diel.py`, `perform.sh`, `preprocess_abacus_for_librpa_band.py`, `run_abacus.sh`

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
5. Branch the workflow accordingly:
   - GW route uses the full chain when needed: dielectric-function path, `pyatb`, NSCF, and band preprocessing
   - RPA route skips GW-only preprocessing: no dielectric-function path, no `pyatb`, no NSCF, no `preprocess_abacus_for_librpa_band.py`
6. Classify spin/SOC state and keep `INPUT`, workflow scripts, and `librpa.in` aligned:
   - Collinear spin, no SOC -> `nspin = 2`, `lspinorb = 0`
   - Noncollinear with SOC -> `nspin = 4`, `lspinorb = 1`
   - In `get_diel.py`, update `nspin` and `use_soc` consistently
   - In `preprocess_abacus_for_librpa_band.py`, update `use_soc` consistently
   - In `librpa.in`, only switch `use_soc = 0/1`
7. Generate workflow inputs from matched experience rules.
8. Apply task-specific `librpa.in` defaults unless a stronger rule overrides them:
   - shared runtime baseline:
     - `nfreq = 16`
     - `use_soc = 0/1` according to the chosen spin/SOC branch
     - `use_scalapack_gw_wc = t`
     - `use_scalapack_ecrpa = t`
     - `parallel_routing = libri`
     - `vq_threshold = 0`
     - `sqrt_coulomb_threshold = 0`
     - `use_fullcoul_exx = t`
     - `libri_chi0_threshold_C = 1e-4`
     - `libri_chi0_threshold_G = 1e-5`
     - `libri_exx_threshold_V = 1e-1`
     - `libri_exx_threshold_C = 1e-4`
     - `libri_exx_threshold_D = 1e-4`
   - GW-specific additions:
     - `option_dielect_func = 3`
     - `replace_w_head = t`
     - `output_gw_sigc_mat_rf = t`
     - `libri_g0w0_threshold_C = 1e-5`
     - `libri_g0w0_threshold_G = 1e-5`
     - `libri_g0w0_threshold_Wc = 1e-6`
   - RPA-specific rule:
     - keep `task = rpa`
     - do not insert GW-only dielectric-function preprocessing settings into the workflow
9. For both `molecule` and `solid` branches:
   - Modify `INPUT_scf` and `INPUT_nscf` so `nbands` equals the basis-function count when both files are part of the route
   - Count basis functions from `.orb` files using `s=1`, `p=3`, `d=5`, `f=7`, ... with radial multiplicity, then sum over all atoms in the primitive cell
   - If SOC is enabled, multiply the final basis count by `2`
   - Cross-check the chosen `nbands` against ABACUS `NBASE`
   - If there is any ambiguity in basis counting, stop and explain the counting rule before proceeding
10. If the system is `molecule`:
   - Set `KPT = 1 1 1`
   - Add `gamma_only 1` to `INPUT_scf`
   - Use official ABACUS input names from the ABACUS input documentation
   - For GW: do not run `pyatb` and set `replace_w_head = f` in `librpa.in`
   - For RPA: keep the short route `SCF -> LibRPA`
11. If the system is `solid`:
   - Ask how many k-points to use in `KPT`; default to `8 8 8`
   - For GW:
     - `KPT_nscf` must be defined by the user
     - After SCF, run `pyatb` to generate `pyatb_librpa_df`
     - Then run NSCF
     - Then run `preprocess_abacus_for_librpa_band.py` to generate band information files
     - Then run `LibRPA`
   - For RPA:
     - do not run `pyatb`
     - do not run NSCF
     - do not require `KPT_nscf`
     - run `SCF -> LibRPA`
12. If shrink is enabled, require the user to specify `ABFS_ORBITAL` in `STRU` before continuing.
13. Prefer scripts and reference inputs from `/mnt/sg001/home/ks_iopcas_ghj/gw/template` when working on the server.
14. Run smoke-first setup.
15. Validate outputs and then escalate accuracy stepwise.
16. Report each stage before moving to the next critical stage.

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
