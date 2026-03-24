# FHI-aims + LibRPA QSGW/G0W0 Supplement

This guide adds a supplemental route to `oh-my-LibRPA` for teams that already use `FHI-aims + LibRPA` case directories and want the chat-first layer to reuse that practice safely.

## Scope

Use this supplement when the workflow is based on FHI-aims-generated LibRPA inputs rather than the ABACUS mainline. Typical triggers include:

- `control.in`
- `geometry.in`
- `run_librpa_gw_aims_iophr.sh`
- `qsgw_band`
- `qsgw_band0`
- `modeA` / `modeB`
- mirroring an older Si, MgO, or similar reference case

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
