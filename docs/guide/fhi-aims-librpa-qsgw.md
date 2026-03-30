# FHI-aims + LibRPA QSGW/G0W0 Stack-Layer Guide

This guide defines the `FHI-aims -> LibRPA` stack-layer route inside `oh-my-LibRPA`.

It exists to keep two workflow families separated:

- `ABACUS -> LibRPA`
- `FHI-aims -> LibRPA`

The top-level router `skills/oh-my-librpa/` should decide between those two layers first.

After that:

- `skills/oh-my-librpa-abacus-librpa/` owns ABACUS-style bundles such as `INPUT_scf`, `KPT_nscf`, and `STRU`
- `skills/oh-my-librpa-fhi-aims-qsgw/` owns FHI-aims-style bundles such as `control.in` and `run_librpa_gw_aims_iophr.sh`

This separation is intentional. It prevents the agent from mixing ABACUS input conventions with FHI-aims case layouts.

## Scope

Use this route when the workflow is based on FHI-aims-generated LibRPA inputs rather than the ABACUS route. Typical triggers include:

- `control.in`
- `run_librpa_gw_aims_iophr.sh`
- `qsgw_band`
- `qsgw_band0`
- `modeA` / `modeB`
- mirroring an older Si, MgO, or similar reference case

Treat `geometry.in`, `librpa.d/`, and `self_energy/` as supporting markers only. They are not enough on their own to claim FHI-aims ownership, because reused ABACUS-side bundles and plotting helpers may also carry them.

If the bundle instead centers on:

- `INPUT`, `INPUT_scf`, `INPUT_nscf`
- `KPT`, `KPT_scf`, `KPT_nscf`
- `STRU`
- `.orb`, `.abfs`, `.upf`

do not use this guide. Route to `skills/oh-my-librpa-abacus-librpa/` instead.

## Routing Contract

Follow this contract strictly:

1. `skills/oh-my-librpa/` only decides which stack layer owns the case.
2. `skills/oh-my-librpa-fhi-aims-qsgw/` owns all `FHI-aims -> LibRPA` case handling.
3. `skills/oh-my-librpa-abacus-librpa/` owns all `ABACUS -> LibRPA` case handling.
4. Do not borrow file expectations across the two layers.

In practice, that means:

- do not reuse `control.in` or `geometry.in` conventions when preparing ABACUS cases
- do not reuse `INPUT_scf`, `KPT_nscf`, or `STRU` conventions when handling FHI-aims cases
- if a bundle mixes both families, stop and explain the mismatch before editing anything
- if only `geometry.in`, `librpa.d/`, or `self_energy/` is present, do not auto-route here; inspect for stronger ownership markers first

## Core Rules

1. Treat the reference case as authoritative for:
   - basis settings
   - executable paths
   - directory layout
   - Slurm resource style
2. Change only the requested axes:
   - `k_grid`
   - `task`
   - job name
   - node count
   - target root or mode label
3. For fresh runs, keep the execution order:
   - `FHI-aims -> LibRPA`
4. Derive `nfreq` from `frequency_points` in `control.in` when the script uses the common pattern.
5. Submit production work only through `sbatch` from the case directory.
6. Do not launch production `mpirun` from a login node.

## Layer Responsibility

Within this layer, the agent should:

- mirror or stage FHI-aims-based case directories safely
- decide between fresh `FHI-aims -> LibRPA` execution and `LibRPA-only` reuse
- keep `qsgw_band`, `qsgw_band0`, `qsgw`, `qsgwa`, and `g0w0_band` task choices inside the FHI-aims family
- stop before submission when the user asks for staging only

## Typical `librpa.in` Baseline for Band Workflows

```text
option_dielect_func = 0
replace_w_head = t
use_scalapack_gw_wc = t
parallel_routing = libri
binary_input = t
```

## Common Task Mapping

- `task = g0w0_band`: single-shot band reference
- `task = qsgw_band`: mode-B style band update
- `task = qsgw_band0`: older mode-A style band update
- `task = qsgw`: self-consistent QSGW loop
- `task = qsgwa`: QSGW-A variant when explicitly requested

## Recommended Chat Examples

- `Mirror the MgO old-basis modeA setup, but switch the task to qsgw_band and stage a modeB k-point sweep first.`
- `Use the same LibRPA build path as the Si old_qsgw_B case and submit all cases except k888.`
- `Prepare the directories first, then wait for confirmation before submitting any QSGW jobs.`
