---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use OML MCP first.

Apply `librpa-openmp-mkl-threading` before LibRPA submission or diagnosis.

1. Run `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`; repair `FAIL` and report `WARN`. Inspect reader v1 with `inspect_reader_v1`, then use `inspect_grid_coulomb_consistency` before solid response and `inspect_sternheimer_comparison` afterward. Require `v1_sternheimer_coulomb_iq_*`: disagreement with its optional grid diagnostic blocks; ordinary `v1_coulomb_full_iq_*` differences are diagnostic only.
2. Production supports approved non-SOC periodic GW only: `prepare_run`, `submit_stage`, `get_status`, `inspect_stage`, `finalize_case`, then `score_case`.
3. `abacus-librpa-2026-08-30-v2` preserves the historical result; use `abacus-librpa-2026-08-30-v3` for the corrected handoff. periodic 3D GW, strict-2D GW, molecular Delta-Sternheimer RPA, and solid Delta-Sternheimer RPA remain admission-only. Use `inspect_admission_manifest` and `evaluate_admission`.
4. `propose_evolution_candidate` changes one registered axis and returns `PROPOSAL_ONLY`; it never submits or promotes.

Load `references/delta-st-route.md` only after MCP selects Delta-ST.

Never bypass MCP with direct shell, SSH, Slurm, cleanup, overwrite, or retry. Never submit stale plans, changed manifests, unknown binaries, duplicates, or blocked stages.

Keep FHI-aims writes on existing reviewed routes and use their ownership gate.

Symmetry comes from `stru_out`; LibRPA rebuilds rotations. Do not copy legacy sidecars. PyATB dimensions must match ABACUS and `bz_sampling_out`.

For FHI-aims, keep `periodic_gw_optimize_kgrid_symmetry` q-point reduction
separate from LibRPA `use_symmetry_exx`, `use_symmetry_rpa`, and
`use_symmetry_gw`.
