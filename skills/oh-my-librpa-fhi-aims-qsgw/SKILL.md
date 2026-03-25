---
name: oh-my-librpa-fhi-aims-qsgw
description: Stack-layer workflow for FHI-aims -> LibRPA QSGW/G0W0 cases. Use when users ask to mirror existing FHI-aims + LibRPA cases, prepare staged k-point or basis campaigns, run aims before LibRPA, submit case-local Slurm scripts, or debug QSGW band workflows such as qsgw_band and qsgw_band0. Keep this layer separate from ABACUS INPUT/KPT/STRU workflows.
---

# oh-my-librpa-fhi-aims-qsgw

Treat existing case directories as the source of truth when the user says `follow`, `mirror`, `same settings`, or `same path as Si/MgO/...`.

Treat this skill as the FHI-aims-side router below the top-level `oh-my-librpa` entrypoint.

## Environment gate (mandatory first step)

- Detect host side before running commands.
- Distinguish local orchestration from the remote cluster that will actually execute `FHI-aims` and LibRPA.
- Before submission, confirm whether the target host relies on interactive-shell initialization for MPI, compiler, module, or oneAPI setup.

## Core Behavior

- Determine the requested task early:
  - `g0w0_band`
  - `qsgw_band`
  - `qsgw_band0`
  - `qsgw`
  - `qsgwa`
- Distinguish two execution modes:
  - `FHI-aims + LibRPA fresh run`
  - `LibRPA-only reuse`
- Explain major decisions with `why + risk + verification`.

## Intake Markers

Treat these as strong FHI-aims ownership markers:

- `control.in`
- `run_librpa_gw_aims_iophr.sh`
- explicit task names such as `qsgw_band`, `qsgw_band0`, `qsgw`, and `qsgwa`
- explicit user intent that the case follows an existing FHI-aims reference workflow

Treat these as supporting markers only:

- `geometry.in`
- `librpa.d/`
- `self_energy/`

If the bundle instead centers on `INPUT_scf`, `INPUT_nscf`, `KPT_*`, `STRU`, `.orb`, `.abfs`, `.upf`, `OUT.ABACUS/`, or ABACUS logs, stop and hand the task to `skills/oh-my-librpa-abacus-librpa/`.

If only supporting markers are present, do not claim FHI-aims ownership yet. Ask which upstream stack owns the source of truth.

## Stage-Only Workflow

Use this branch when the user wants directories and scripts prepared first, then confirmation before submission.

1. Create the new campaign root and case directories.
2. Copy the reference inputs.
3. Keep basis and species settings from the reference `control.in`.
4. Change only the requested axes:
   - `k_grid`
   - `task`
   - job name
   - node count
   - root or mode label
5. Keep executable paths aligned with the chosen reference case unless the user asks to switch builds.
6. Create expected runtime folders such as `librpa.d/` and `self_energy/`.
7. Verify:
   - `k_grid`
   - `frequency_points`
   - `task`
   - `aims` path
   - `librpaexe` path
   - `#SBATCH --nodes`
   - line endings
8. Stop before `sbatch` until the user confirms.

## Fresh FHI-aims + LibRPA Workflow

- Derive `nfreq` from `control.in`.
- Keep the `aims` stage active before LibRPA unless the user explicitly wants to reuse existing generated inputs.
- In shared cluster scripts, use `OMP_NUM_THREADS=1` for the `aims` stage.
- For band workflows, the common `librpa.in` baseline is:
  - `option_dielect_func = 0`
  - `replace_w_head = t`
  - `use_scalapack_gw_wc = t`
  - `parallel_routing = libri`
  - `binary_input = t`

## Operational Notes for FHI-aims + LibRPA

- Treat the successful reference case as the source of truth for executable paths, Slurm resource style, and script structure. Do not switch builds or recompile the environment unless the user explicitly asks.
- Run `FHI-aims` successfully before trusting any downstream LibRPA stage. A handoff is only considered valid after `aims.out` shows:
  - `Self-consistency cycle converged.`
  - `Leaving FHI-aims.`
  - `Have a nice day.`
- Before calling the case `LibRPA-ready`, verify the generated handoff artifacts in the case root. Typical files include:
  - `KS_eigenvector_*`
  - `coulomb_mat_*`
  - `S_spin_*`
  - `xc_matr_*`
  - `Cs_data_*`
- Prefer the original case-local submission script. If the user says to follow a previous Si or MgO case, mirror that script instead of inventing a new launcher.
- Submit only from the case directory. If the target host loads MPI, compiler, or oneAPI modules only in interactive shells, prefer an interactive-shell submission such as `ssh <host> bash -ic "cd <case> && sbatch run_librpa_gw_aims_iophr.sh"` so the batch job inherits the same environment as known-good reference runs.
- Do not patch the cluster environment just because a non-interactive shell missed `mpirun` or module setup. First check whether the reference workflow depends on interactive shell initialization.
- Do not claim that QSGW iterations have started just because LibRPA is running. Separate these stages explicitly:
  - `running aims`
  - `running librpa` in pre-iteration stages such as `chi0`, `Wc`, or correlation self-energy
  - `running qsgw iterations` only after lines such as `Iteration ... HOMO = ...` appear or `homo_lumo_vs_iterations.dat` becomes non-empty

## Submission Rules

- Submit only through Slurm:
  - `cd <case> && sbatch run_librpa_gw_aims_iophr.sh`
- Do not run production `mpirun` from the login node.
- If the user wants a helper submit script, it may only call `sbatch`.
- If one case already has trusted results, skip it explicitly instead of mutating the old directory.

## Monitoring and Debug

- Use `squeue` and case-local outputs to classify the state as:
  - `queued`
  - `running aims`
  - `running librpa`
  - `running qsgw iterations`
  - `failed`
  - `finished`
- `running aims` should be confirmed from `aims.out` growth and completion markers, not only from Slurm state.
- `running librpa` should be confirmed from `librpa.out` growth and stage markers such as `chi0`, `Wc`, or correlation self-energy.
- `running qsgw iterations` should be confirmed from `Iteration ... HOMO` or `Converged after` lines, not guessed early.
- For OMP inconsistency, deterministic reduction, or evidence-led reports, reuse the relevant local LibRPA debugging and validation workflows when available.
