---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use OML MCP first.

1. Call `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`. Repair each `FAIL`; report each `WARN`. Use `inspect_reader_v1` for reader v1 artifacts.
2. The old profile permits approved non-SOC periodic GW production only. Use `prepare_run`, then fixed-order `submit_stage`, read-only `get_status`, terminal `inspect_stage`, `finalize_case`, and `score_case`.
3. Profile `abacus-librpa-2026-08-30-v2` registers periodic 3D GW, strict-2D GW, molecular Delta-Sternheimer RPA, and solid Delta-Sternheimer RPA as admission-only `TESTABLE` routes. Do not send them through the production materializer.
4. Automatic evolution changes one registered axis and returns `PROPOSAL_ONLY`; it cannot submit or promote a route.

Never bypass MCP with direct shell, SSH, Slurm, cleanup, overwrite, or automatic retry. Never submit stale plans, changed manifests, unknown binaries, duplicates, or stages with unmet prerequisites.

Keep FHI-aims writes on existing reviewed routes and use their dedicated ownership gate.

Symmetry comes from `stru_out`; LibRPA rebuilds rotations. Legacy symmetry sidecars are neither copied nor required. PyATB state, eigenvector, velocity, and symmetry dimensions must match ABACUS and `bz_sampling_out`.
