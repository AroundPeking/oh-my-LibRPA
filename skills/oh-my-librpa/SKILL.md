---
name: oh-my-librpa
description: Chat-first orchestrator for ABACUS + LibRPA workflows. Use when users ask in natural language to prepare, run, audit, or debug GW/RPA tasks, especially when the agent must classify uploaded files, choose local vs server execution, route by system type (molecule, solid, 2D), and keep the interaction operational instead of exposing raw CLI complexity.
---

# oh-my-librpa

Treat the user message as an intent, not as a command request.

Keep the conversation short, operational, and stage-based.

## Act as the front router

Do these steps in order:

1. Ask for files first when the user already has a case bundle.
2. Decide the upstream stack before deeper routing:
   - strong `ABACUS -> LibRPA` markers: `INPUT*`, `KPT*`, `STRU`, `.orb`, `.abfs`, `.upf`, `OUT.ABACUS/`, ABACUS logs
   - strong `FHI-aims -> LibRPA` markers: `control.in`, `run_librpa_gw_aims_iophr.sh`, explicit `FHI-aims` user intent, or task names such as `qsgw_band`, `qsgw_band0`, `qsgw`, `qsgwa`
   - supporting markers only: `geometry.in`, `librpa.d/`, `self_energy/`; they are not enough on their own to claim `FHI-aims -> LibRPA`
3. If strong ABACUS markers are present, route through `skills/oh-my-librpa-abacus-librpa/`.
4. If strong FHI-aims markers are present and there are no conflicting ABACUS markers, route through `skills/oh-my-librpa-fhi-aims-qsgw/`.
5. If a bundle mixes both families, stop and ask which upstream stack owns the source of truth before editing anything.
6. For `ABACUS -> LibRPA`, classify the task as `GW`, `RPA`, or `Debug`.
7. For `ABACUS -> LibRPA`, classify the system as `molecule`, `solid`, or `2D`.
8. Ask where execution should happen: local or server.
9. Create a fresh isolated run directory before any real run.
10. If the case needs PP/NAO/ABFS assets and the user did not provide a complete bundle, read `references/pp-nao-abfs-library.md` and select files from the bundled asset library.
11. For `ABACUS -> LibRPA`, route into the matching reference file and follow it strictly:
   - `references/gw-route.md`
   - `references/rpa-route.md`
   - `references/debug-route.md`
12. If the ABACUS case uses the user's merged local ABACUS checkout or helper scripts copied from local Downloads, also read `references/abacus-merge-compat.md`.
13. If server execution is chosen, also read `references/server-profiles.md` before submission.
14. For `ABACUS -> LibRPA`, before any real submission, run `scripts/intake_preflight.sh <case_dir> --mode <...> --system-type <...> --compute-location <...>` and block on any `FAIL` from the static checks.
15. When route defaults, stage checks, or repair actions are still uncertain, load the most relevant cards under `rules/cards/` instead of inventing new workflow behavior.
16. Keep FHI-aims file conventions isolated from ABACUS `INPUT*` / `KPT*` / `STRU` conventions.
17. If the user asks how to obtain, generate, select, validate, or document `ABFS_ORBITAL` / `.abfs` files, load `skills/abacus-librpa-abfs-orbital/`.

If the route is still ambiguous, ask the smallest possible clarification set.

## Mandatory file-intake handshake

Treat uploaded files as the primary source of truth.

Classify provided files into these groups:

- `structure files`: `STRU`, `cif`, `xyz`, `geometry.in`
- `input bundle`: `INPUT`, `INPUT_scf`, `INPUT_nscf`, `KPT`, `KPT_scf`, `KPT_nscf`, `librpa.in`
- `fhi-aims strong markers`: `control.in`, `run_librpa_gw_aims_iophr.sh`, explicit `qsgw_band` / `qsgw_band0` / `qsgw` / `qsgwa` task settings
- `fhi-aims supporting markers`: `geometry.in`, `self_energy/`, `librpa.d/`
- `symmetry sidecars`: `irreducible_sector.txt`, `symrot_R.txt`, `symrot_k.txt`, `symrot_abf_k.txt`
- `workflow scripts`: `get_diel.py`, `perform.sh`, `preprocess_abacus_for_librpa_band.py`, `run_abacus.sh`, `output_librpa.py`, `plot_gw_band_paper.py`, `env.sh`, `probe_batch.sh`
- `basis/pseudopotential assets`: `.orb`, `.abfs`, `.upf`
- `logs/results`: output files, error logs, `band_out`, generated band data
- `archives`: `zip`, `tar.gz`

Use these intake rules:

- `structure files` -> generate or complete the workflow
- `input bundle` -> audit and patch; do not rewrite blindly
- `input bundle` that is clearly ABACUS-based -> hand off to `skills/oh-my-librpa-abacus-librpa/`
- `fhi-aims strong markers` with no conflicting ABACUS markers -> route to `skills/oh-my-librpa-fhi-aims-qsgw/`
- `fhi-aims supporting markers` alone do not override ABACUS routing; ask only if ownership is still unclear after checking for strong markers
- `symmetry sidecars` -> keep them tied to the exact SCF that produced them; if one exists for periodic GW, verify the full required set before LibRPA
- `.abfs` files -> treat as authoritative candidates for `ABFS_ORBITAL`
- `logs/results` -> start in Debug mode first
- `archives` -> unpack and classify before asking more questions

If the user did not provide PP/NAO/ABFS assets, consult the bundled library described in `references/pp-nao-abfs-library.md`.

If a server-side reference bundle already exists, prefer it over rebuilding from scratch.

## Mandatory compute-location handshake

Before compute, ask:

1. `Do you want local compute or server compute?`
2. If server: `Do you need VPN first?`
3. If server: `Do you want me to run connectivity/login checks now?`

Then branch:

- Local -> prefer preprocessing and static checks first; confirm once before any full local compute
- Server -> wait for VPN confirmation if needed, then verify login/connectivity, then materialize explicit runtime config before submission

Do not trust interactive shell defaults for `python3`, MPI launchers, or executable paths.

## Run discipline

Always do all of the following:

- Create a fresh timestamped run directory
- When cloning a prior case into a new run directory, copy only source inputs and helper scripts; do not copy generated outputs such as `OUT.ABACUS`, `band_out`, `coulomb_*`, `LibRPA*.out`, `librpa.d`, `time.json`, or old `GW_band_spin_*`
- Create `run-report.md` in that directory
- Create an archived Markdown copy under `${CODEX_HOME:-$HOME/.codex}/workspace/librpa/oh-my-librpa/`
- Refuse to overwrite original data directories
- Prefer smoke-first validation before expensive runs
- For server smoke runs, start from the smallest batch payload that can print `pwd`, list files, and run one stage; do not add `.bashrc`, `conda`, `setvars.sh`, or `mpirun -np 1` unless a probe proves they are needed
- On any server, remind the user to confirm that both `abacus_work` and `librpa_work` were compiled against the same latest LibRI that includes the nearest-fix bugfix; do not mix one side built against older LibRI
- On `df_iopcas_ghj`, do not use `source ~/.bashrc` as the default Slurm batch entrypoint. In batch mode it can leave conda-injected paths without the intended oneAPI/module toolchain, or fail immediately with empty `slurm` output. Prefer explicit `module load cmake/3.31.7`, `module load oneapi/2024.2`, and compiler exports in the script itself
- For ABACUS-side Coulomb validation, allow `SCF`-only runs; do not force `pyatb`, `NSCF`, or `LibRPA` if the user is only checking `coulomb_mat_*` / `coulomb_cut_*`
- For ABACUS symmetry-on Coulomb validation, do not flatten-compare `symmetry=1` output with `symmetry=-1` output: symmetry-on exports IBZ q only, while symmetry-off exports the full BZ q-grid. Compare symmetry-on `mpi1` vs `mpiN` directly, compare Gamma/no-rotation blocks, or restore the full q-star before comparing to symmetry-off data
- Apply route-aware static checks before remote submission
- For reused or cloned case bundles, treat input-key compatibility as mandatory, not optional: run the preflight checker and patch deprecated ABACUS keywords before submitting
- Report after every mini-stage: `what was done`, `what was observed`, `what is next`
- Only enable heavy ABACUS Coulomb debug envs such as `ABACUS_DEBUG_CUT_MPI=1` for short targeted traces; they can distort runtime badly, especially on `shrink` + single-MPI control runs

## Routing rules

- User provides ABACUS-style inputs such as `INPUT_scf`, `INPUT_nscf`, `KPT_*`, `STRU`, or ABACUS logs -> route to `skills/oh-my-librpa-abacus-librpa/`
- User explicitly says `FHI-aims`, or provides `control.in`, `run_librpa_gw_aims_iophr.sh`, or explicit tasks such as `qsgw_band` / `qsgw_band0` / `qsgw` / `qsgwa` with no conflicting ABACUS markers -> route to `skills/oh-my-librpa-fhi-aims-qsgw/`
- If a bundle mixes both ABACUS and FHI-aims markers, stop and ask which upstream stack owns the source of truth before editing anything.
- If neither stack is explicit, preserve existing behavior and route by task intent:
  - GW requests -> `references/gw-route.md`
  - dielectric/response/RPA requests -> `references/rpa-route.md`
  - failure reports, weird output, parser/read issues, mixed inputs, or logs-first requests -> `references/debug-route.md`

## Safety rules

- Always require a new run directory for each run chain
- Never overwrite original source-data directories
- Prefer static consistency checks before remote execution
- Never submit a reused GW case bundle to a newer ABACUS branch without a keyword-compatibility audit
- Confirm server and resource choice before expensive or long jobs
- When the basis count, route, or spin/SOC alignment is ambiguous, stop and explain the ambiguity before proceeding
- When SOC is enabled, do not use the periodic symmetry lane: keep ABACUS on `symmetry -1` and disable the LibRPA symmetry flags
- For symmetry-on/off comparisons, keep every non-symmetry input identical and only patch the symmetry knobs plus sidecar staging

## Output style

Keep replies concise and useful.

Only offer options when there is a real tradeoff.

Default to a clear next action that moves the case forward now.
