---
name: oh-my-librpa-fhi-aims-qsgw
description: Supplemental workflow for FHI-aims + LibRPA QSGW/G0W0 work. Use when users ask to mirror existing FHI-aims + LibRPA cases, prepare staged k-point or basis campaigns, run aims before LibRPA, submit case-local Slurm scripts, or debug QSGW band workflows such as qsgw_band and qsgw_band0.
---

# oh-my-librpa-fhi-aims-qsgw

Treat existing case directories as the source of truth when the user says `follow`, `mirror`, `same settings`, or `same path as Si/MgO/...`.

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
  - `failed`
  - `finished`
- For OMP inconsistency, deterministic reduction, or evidence-led reports, reuse the relevant local LibRPA debugging and validation workflows when available.
