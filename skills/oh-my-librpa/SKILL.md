---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use OML MCP first.

Apply `librpa-openmp-mkl-threading` before LibRPA submission or performance
diagnosis; producer thread settings do not define LibRPA settings.

1. Call `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`. Repair each `FAIL`; report each `WARN`. Use `inspect_reader_v1` for reader v1 artifacts.
2. Production supports approved non-SOC periodic GW only: `prepare_run`, fixed-order `submit_stage`, `get_status`, `inspect_stage`, `finalize_case`, then `score_case`.
3. Profile `abacus-librpa-2026-08-30-v2` keeps periodic 3D GW, strict-2D GW, molecular Delta-Sternheimer RPA, and solid Delta-Sternheimer RPA admission-only. Use `inspect_admission_manifest` and `evaluate_admission`.
4. `propose_evolution_candidate` changes one registered axis and returns `PROPOSAL_ONLY`; it never submits or promotes.

Load `references/delta-st-route.md` only after MCP selects Delta-ST.

Never bypass MCP with direct shell, SSH, Slurm, cleanup, overwrite, or automatic retry. Never submit stale plans, changed manifests, unknown binaries, duplicates, or stages with unmet prerequisites.

Keep FHI-aims writes on existing reviewed routes and use their dedicated ownership gate.

Symmetry comes from `stru_out`; LibRPA rebuilds rotations. Do not copy legacy
sidecars. PyATB dimensions must match ABACUS and `bz_sampling_out`.

For FHI-aims, keep `periodic_gw_optimize_kgrid_symmetry` q-point reduction
separate from LibRPA `use_symmetry_exx`, `use_symmetry_rpa`, and
`use_symmetry_gw`.
