---
name: oh-my-librpa
description: Chat-first orchestrator for ABACUS + LibRPA workflows, with a supplemental FHI-aims + LibRPA QSGW/G0W0 branch. Use when users ask in natural language to prepare, run, or debug GW/RPA tasks, and route FHI-aims-specific QSGW requests to the dedicated supplement skill instead of changing the ABACUS mainline.
---

# oh-my-librpa (Chat-First)

Treat user messages as task intents, not command requests.

## Core Behavior

- Accept natural language only; do not require user-side custom commands.
- Convert user intent into one of five paths:
  - `GW workflow`
  - `RPA workflow`
  - `Debug workflow`
  - `Stack install / doctor workflow`
  - `FHI-aims + LibRPA QSGW/G0W0 supplement`
- Determine system type early: `molecule` / `solid` / `2D`.
- Explain major decisions with `why + risk + verification`.

## Environment / Install Branch

If the user is asking to install, compile, configure, or repair the `ABACUS + PYATB + LibRPA` software stack itself, route to the `abacus-pyatb-librpa-stack` skill before asking for workflow input files.

For that branch:

- use `docs/guide/abacus-pyatb-librpa-stack.md` as the canonical build-order reference
- run `scripts/stack_env_doctor.sh` first when you can access the machine
- only return to the workflow branches after the runtime layer is healthy

## Mandatory File-Intake Handshake

Before starting any compute task, ask the user to provide files first when available.

Treat uploaded files as the primary source of truth.

As soon as files land in a working directory, run the installed `oh-my-librpa/scripts/intake_preflight.sh <case_dir>` helper to classify the bundle, infer the likely route, and report what is still missing before asking extra questions.

Classify user-provided files into one of these groups:

- `structure files`: `STRU`, `cif`, `xyz`, `geometry.in`
- `input bundle`: `INPUT`, `INPUT_scf`, `INPUT_nscf`, `KPT`, `KPT_scf`, `KPT_nscf`, `librpa.in`
- `workflow scripts`: `get_diel.py`, `perform.sh`, `preprocess_abacus_for_librpa_band.py`, `run_abacus.sh`
- `fhi-aims bundle`: `control.in`, `geometry.in`, `run_librpa_gw_aims_iophr.sh`, `self_energy/`, `librpa.d/`
- `basis/pseudopotential assets`: `.orb`, `.abfs`, `.upf`
- `logs/results`: output files, error logs, `band_out`, generated band data
- `archives`: `zip`, `tar.gz`

If the user provides files:

- `structure files` -> generate or complete the workflow
- `input bundle` -> audit and patch instead of rewriting blindly
- `fhi-aims bundle` -> route to the `oh-my-librpa-fhi-aims-qsgw` supplement and mirror the reference case safely
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
2. Create `run-report.md` inside the run directory.
3. Create one archived Markdown copy under the active platform root at `librpa/oh-my-librpa/` using `<timestamp>-<mode>.md`.
4. Verify no overwrite of original data directories.
5. Classify compute stack:
   - FHI-aims markers such as `control.in`, `run_librpa_gw_aims_iophr.sh`, `qsgw_band`, `qsgw_band0`, `modeA`, `modeB`, or `old_basis` -> route to `oh-my-librpa-fhi-aims-qsgw`
   - otherwise continue with the ABACUS route below
6. Classify system type (`molecule` / `solid` / `2D`).
7. Classify task type:
   - GW request -> `task = g0w0_band`
   - RPA request -> `task = rpa`
8. Branch the workflow accordingly:
   - GW route uses the full chain when needed: dielectric-function path, `pyatb`, NSCF, and band preprocessing
   - RPA route skips GW-only preprocessing: no dielectric-function path, no `pyatb`, no NSCF, no `preprocess_abacus_for_librpa_band.py`
   - Molecular GW is the short route `SCF -> LibRPA`; periodic GW (`solid` / `2D`) is the full route `SCF -> pyatb -> NSCF -> preprocess -> LibRPA`
9. Classify spin/SOC state and keep `INPUT`, workflow scripts, and `librpa.in` aligned:
   - Collinear spin, no SOC -> `nspin = 2`, `lspinorb = 0`
   - Noncollinear with SOC -> `nspin = 4`, `lspinorb = 1`
   - In `get_diel.py`, update `nspin` and `use_soc` consistently
   - In `preprocess_abacus_for_librpa_band.py`, update `use_soc` consistently
   - In `librpa.in`, only switch `use_soc = 0/1`
10. Generate workflow inputs from matched experience rules.
11. Apply task-specific `librpa.in` defaults unless a stronger rule overrides them:
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
12. For both `molecule` and `solid` branches:
   - Modify `INPUT_scf` and `INPUT_nscf` so `nbands` equals the basis-function count when both files are part of the route
   - Count basis functions from `.orb` files using `s=1`, `p=3`, `d=5`, `f=7`, ... with radial multiplicity, then sum over all atoms in the primitive cell
   - If SOC is enabled, multiply the final basis count by `2`
   - Cross-check the chosen `nbands` against ABACUS `NBASE`
   - If there is any ambiguity in basis counting, stop and explain the counting rule before proceeding
13. If the system is `molecule`:
   - Set `KPT = 1 1 1`
   - Add `gamma_only 1` to `INPUT_scf`
   - Use official ABACUS input names from the ABACUS input documentation
   - For GW: do not run `pyatb` and set `replace_w_head = f` in `librpa.in`
   - For RPA: keep the short route `SCF -> LibRPA`
14. If the system is `solid`:
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
15. If shrink is enabled, require the user to specify `ABFS_ORBITAL` in `STRU` before continuing.
16. Prefer scripts and reference inputs from `/mnt/sg001/home/ks_iopcas_ghj/gw/template` when working on the server.
17. Run smoke-first setup.
18. Run the installed `oh-my-librpa/scripts/check_consistency.sh <case_dir> --mode <gw|rpa> --system-type <molecule|solid|2D>` helper before remote execution so the static checks follow the selected route instead of assuming every case needs NSCF.
19. Validate outputs using stage-specific success criteria before escalation.
20. For a full GW chain, judge stages with generic markers. Only `LibRPA` needs explicit status monitoring; `pyatb` and `preprocess` usually only need completion checks:
   - SCF: completed `running_scf.log` + `ABACUS-CHARGE-DENSITY.restart`
   - pyatb: `pyatb_librpa_df/` + `band_out` + `KS_eigenvector_*.dat`
   - NSCF: completed `running_nscf.log` + `eig.txt`
   - preprocess: `band_kpath_info` + `band_KS_*` + `band_vxc*`
   - LibRPA success: rank-0 output reaches `Timer stop:  total.` and `GW_band_spin_*.dat` exists
   - LibRPA running: rank-0 output exists, has no final `Timer stop:  total.` yet, and is still growing
   - LibRPA failed: no final `Timer stop:  total.` and the rank-0 output is no longer growing, or the output file is missing
21. For GW execution, prefer the installed `run_gw_workflow.sh` runner so stage execution, route-aware skipping, verification, and reporting stay in one flow.
22. For a full RPA execution path, prefer the installed `run_rpa_workflow.sh` runner so stage execution, verification, and reporting stay in one flow.
23. After each verified stage update, call the installed `report_stage.sh` helper to write both Markdown logs: the run-directory `run-report.md` and the archived copy under the active platform root at `librpa/oh-my-librpa/`.
24. Send the script stdout to the user as the stage summary before moving to the next critical stage.

## Routing Rules

1. If user asks to start GW: use GW path and apply conservative smoke-first strategy.
2. If user asks dielectric/response focus: use RPA path.
3. If user reports failure/log errors: use Debug path first.
4. If user asks about `FHI-aims`, `control.in`, `qsgw_band`, `qsgw_band0`, `modeA`, `modeB`, or mirroring an existing non-ABACUS case, route to `oh-my-librpa-fhi-aims-qsgw`.
5. If system type is unclear, ask the smallest set of clarifying questions.

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
