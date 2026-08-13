---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use OML MCP first.

1. Call `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`. Repair each `FAIL`; report each `WARN`. Use `inspect_reader_v1` for binary-v1 artifacts.
2. Controlled writes support approved non-SOC periodic GW only. Call `prepare_run` with the reviewed digest and registered execution profile.
3. In fixed order, call `submit_stage`, monitor with read-only `get_status`, and call `inspect_stage` only for terminal `COMPLETED`, `FAILED`, or `CANCELLED`. Every terminal outcome is snapshotted. Failed/cancelled states are forced `FAIL`; completed jobs still need artifact gates.
4. After final 3D GW inspection, call `finalize_case` with registered benchmark/convergence IDs, then `score_case`. Never promote `NOT_EVALUATED` to PASS.

Never bypass MCP controlled execution with direct shell, SSH, Slurm, cleanup, overwrite, or automatic retry operations. Do not submit stale plans, changed manifests, unknown binaries, duplicate attempts, or a stage whose prerequisites have not passed.

Keep RPA, molecular/atomic GW, magnetic/SOC, FHI-aims, and Delta-Sternheimer on reviewed routes. Strict 2D is blocked as `LIBRPA_070_STRICT_2D_INVALID` pending corrected LibRPA and dedicated gates.

Symmetry metadata comes from `stru_out`; legacy symmetry sidecars are neither copied nor required.

PyATB `band_out`, `k_path_info`, eigenvectors, and velocities must use the ABACUS `band_out` state count. Never pass extra full-AO states to LibRPA 0.7.0.
