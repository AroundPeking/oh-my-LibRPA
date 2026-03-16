---
name: oh-my-librpa
description: Chat-first orchestrator for ABACUS + LibRPA workflows. Use when users ask in natural language to prepare, run, audit, or debug GW/RPA tasks, especially when the agent must classify uploaded files, choose local vs server execution, route by system type (molecule, solid, 2D), and keep the interaction operational instead of exposing raw CLI complexity.
---

# oh-my-librpa

Treat the user message as an intent, not as a command request.

Keep the conversation short, operational, and stage-based.

## Act as the front router

Do these steps in order:

1. Classify the task as `GW`, `RPA`, or `Debug`.
2. Classify the system as `molecule`, `solid`, or `2D`.
3. Ask for files first when the user already has a case bundle.
4. Ask where execution should happen: local or server.
5. Create a fresh isolated run directory before any real run.
6. If the case needs PP/NAO/ABFS assets and the user did not provide a complete bundle, read `references/pp-nao-abfs-library.md` and select files from the bundled asset library.
7. Route into the matching reference file and follow it strictly:
   - `references/gw-route.md`
   - `references/rpa-route.md`
   - `references/debug-route.md`
8. If the case uses the user's merged local ABACUS checkout or helper scripts copied from local Downloads, also read `references/abacus-merge-compat.md`.
9. If server execution is chosen, also read `references/server-profiles.md` before submission.

If the route is still ambiguous, ask the smallest possible clarification set.

## Mandatory file-intake handshake

Treat uploaded files as the primary source of truth.

Classify provided files into these groups:

- `structure files`: `STRU`, `cif`, `xyz`, `geometry.in`
- `input bundle`: `INPUT`, `INPUT_scf`, `INPUT_nscf`, `KPT`, `KPT_scf`, `KPT_nscf`, `librpa.in`
- `symmetry sidecars`: `irreducible_sector.txt`, `symrot_R.txt`, `symrot_k.txt`, `symrot_abf_k.txt`
- `workflow scripts`: `get_diel.py`, `perform.sh`, `preprocess_abacus_for_librpa_band.py`, `run_abacus.sh`, `output_librpa.py`, `plot_gw_band_paper.py`, `env.sh`, `probe_batch.sh`
- `basis/pseudopotential assets`: `.orb`, `.abfs`, `.upf`
- `logs/results`: output files, error logs, `band_out`, generated band data
- `archives`: `zip`, `tar.gz`

Use these intake rules:

- `structure files` -> generate or complete the workflow
- `input bundle` -> audit and patch; do not rewrite blindly
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
- Create `run-report.md` in that directory
- Create an archived Markdown copy under `~/.openclaw/workspace/librpa/oh-my-librpa/`
- Refuse to overwrite original data directories
- Prefer smoke-first validation before expensive runs
- Apply route-aware static checks before remote submission
- Report after every mini-stage: `what was done`, `what was observed`, `what is next`

## Routing rules

- User asks to start a GW workflow -> route to `references/gw-route.md`
- User asks for dielectric/response/RPA work -> route to `references/rpa-route.md`
- User reports failure, weird output, parser/read issues, or mixed inputs -> route to `references/debug-route.md`
- User provides logs before asking anything else -> route to `references/debug-route.md`

## Safety rules

- Always require a new run directory for each run chain
- Never overwrite original source-data directories
- Prefer static consistency checks before remote execution
- Confirm server and resource choice before expensive or long jobs
- When the basis count, route, or spin/SOC alignment is ambiguous, stop and explain the ambiguity before proceeding
- For symmetry-on/off comparisons, keep every non-symmetry input identical and only patch the symmetry knobs plus sidecar staging

## Output style

Keep replies concise and useful.

Only offer options when there is a real tradeoff.

Default to a clear next action that moves the case forward now.
