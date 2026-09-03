---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use OML MCP first.

Apply `librpa-openmp-mkl-threading` before LibRPA work.

1. Run `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`; repair `FAIL` and report `WARN`. Validate reader v1 with `inspect_reader_v1`; use `inspect_grid_coulomb_consistency` and `inspect_sternheimer_comparison` for their declared gates. Sternheimer requires `v1_sternheimer_coulomb_iq_*`; ordinary reader Coulomb is diagnostic.
2. Controlled non-SOC periodic GW uses `prepare_run`, `submit_stage`, `get_status`, `inspect_stage`, `finalize_case`, then `score_case`.
3. Keep `abacus-librpa-2026-08-30-v2` historical; use `abacus-librpa-2026-08-30-v3` for corrected Sternheimer. The periodic 3D GW, strict-2D GW, molecular Delta-Sternheimer RPA, and solid Delta-Sternheimer RPA routes remain admission-only. Use `inspect_admission_manifest` and v3-default `evaluate_admission`.
4. `abacus-librpa-2026-09-03-strict2d-sos-rpa-v2` is `ENABLED` only for benchmark-bound `strict_2d_sos_rpa`. Call `inspect_route_benchmark` and `evaluate_route_benchmark` with `strict2d-sos-rpa-mos2-qavg-v1`. This reference-bounded result makes no asymptotic exponent claim and is not strict-2D GW acceptance.
5. `propose_evolution_candidate` changes one registered axis and stays `PROPOSAL_ONLY`.

Load `references/delta-st-route.md` only after MCP selects Delta-ST.

Never bypass MCP with shell, SSH, Slurm, cleanup, overwrite, or retry. Block stale plans, changed manifests, unknown binaries, duplicates, and blocked stages.

Keep FHI-aims writes on existing reviewed routes and use their ownership gate.

Symmetry comes from `stru_out`; copy no sidecars. PyATB dimensions must match ABACUS and `bz_sampling_out`.

For FHI-aims, keep `periodic_gw_optimize_kgrid_symmetry` q-point reduction
separate from LibRPA `use_symmetry_exx`, `use_symmetry_rpa`, and
`use_symmetry_gw`.
