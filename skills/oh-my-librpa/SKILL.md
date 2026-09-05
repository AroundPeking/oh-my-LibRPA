---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use OML MCP first.

Apply `librpa-openmp-mkl-threading`.

1. Run `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`; repair `FAIL`, report `WARN`. Use `inspect_reader_v1`, `inspect_grid_coulomb_consistency`, and `inspect_sternheimer_comparison`. Sternheimer requires `v1_sternheimer_coulomb_iq_*`.
2. Controlled non-SOC periodic GW uses `prepare_run`, `submit_stage`, `get_status`, `inspect_stage`, `finalize_case`, then `score_case`.
3. Default `abacus-librpa-2026-09-06-v6` requires reader v1 and `stru_out`; periodic 3D GW is L3 `EXPERIMENTAL`. BN passes `nfreq=24 -> 32`, screening `12x12x12 -> 14x14x14`, and a `4x4x4` no-head/wing symmetry/full-q control. Empty-state, NAO, ABFS, transfer, and physical-reference gates remain; status is `NOT_EVALUATED`; molecular Delta-Sternheimer RPA and solid Delta-Sternheimer RPA await the metric. Keep `abacus-librpa-2026-09-06-v5`, `abacus-librpa-2026-09-03-v4`, and `abacus-librpa-2026-08-30-v2` historical; use `abacus-librpa-2026-08-30-v3` only for that metric.
4. `abacus-librpa-2026-09-03-strict2d-sos-rpa-v2` is `ENABLED` only for reference-bounded `strict2d-sos-rpa-mos2-qavg-v1`. Use `inspect_route_benchmark`, `evaluate_route_benchmark`, and `evaluate_route_benchmark_suite`; this is not strict-2D GW acceptance and proves no asymptotic exponent.
5. Use `inspect_admission_manifest` and `evaluate_admission`; `propose_evolution_candidate` stays `PROPOSAL_ONLY`.

Load `references/delta-st-route.md` only after MCP selects Delta-ST.

Never bypass MCP for execution. Block stale plans, manifests, unknown binaries, duplicates, and blocked stages.

FHI-aims writes on existing reviewed routes; use their ownership gate.

Symmetry comes from `stru_out`; copy no sidecars. PyATB dimensions must match ABACUS and `bz_sampling_out`.

For FHI-aims, keep `periodic_gw_optimize_kgrid_symmetry` q-point reduction
separate from LibRPA `use_symmetry_exx`, `use_symmetry_rpa`, and
`use_symmetry_gw`.
