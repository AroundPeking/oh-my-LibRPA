---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use OML MCP first.

1. Call `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`. Repair every `FAIL`; report every `WARN`. Use `inspect_reader_v1` for PyATB or binary-v1 artifacts.
2. Controlled execution currently supports only approved non-SOC periodic GW plans. For these, call `prepare_run` with the reviewed plan digest and registered execution profile ID.
3. For each fixed stage in order, call `submit_stage`, monitor with read-only `get_status`, and call `inspect_stage` only when the scheduler reports completion. A scheduler-completed job is not a passed stage until artifact gates pass.
4. Call `score_case` after preparation, failures, repairs, and final inspection. Preserve `NOT_EVALUATED` dimensions; never describe them as passed.

Never bypass MCP controlled execution with direct shell, SSH, Slurm, cleanup, overwrite, or automatic retry operations. Do not submit stale plans, changed manifests, unknown binaries, duplicate attempts, or a stage whose prerequisites have not passed.

Keep RPA, molecular/atomic GW, strict 2D, magnetic/SOC, FHI-aims, regression, and Delta-Sternheimer execution on their existing reviewed routes. MCP read-only inspection still applies where compatible.

Symmetry metadata comes from `stru_out`; legacy symmetry sidecars are neither copied nor required.
