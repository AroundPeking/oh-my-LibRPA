---
name: oh-my-librpa-mcp-test
description: Opt-in experimental OML MCP harness for admission, controlled execution, and benchmark testing.
---

# Oh-My-LibRPA MCP Test

Use this skill only when the user explicitly requests the experimental MCP
harness. Ordinary GW, magnetic, SOC, historical, and molecular tasks stay on
the stable `oh-my-librpa` skill workflow.

Apply `librpa-openmp-mkl-threading`.

1. Run `inspect_profile`, `ingest_case`, `plan_case`, and `validate_case`;
   repair `FAIL` and report `WARN`. Use `inspect_reader_v1`,
   `inspect_grid_coulomb_consistency`, and `inspect_sternheimer_comparison`.
2. Controlled non-SOC periodic GW uses `prepare_run`, `submit_stage`,
   `get_status`, `inspect_stage`, `finalize_case`, then `score_case`.
3. The controlled executor currently accepts only nonmagnetic `nspin=1`,
   non-SOC, periodic 3D GW. Treat `ROUTE_NOT_EXECUTABLE` as missing MCP
   coverage, not as evidence that an established external workflow is wrong.
4. Use `inspect_admission_manifest`, `inspect_route_benchmark`,
   `evaluate_route_benchmark`, `evaluate_route_benchmark_suite`, and
   `evaluate_admission` for frozen evidence. `propose_evolution_candidate`
   remains `PROPOSAL_ONLY`.

Default profile `abacus-librpa-2026-09-06-v6` uses reader v1. Keep
`abacus-librpa-2026-09-06-v5`, `abacus-librpa-2026-09-03-v4`, and
`abacus-librpa-2026-08-30-v2` historical; use
`abacus-librpa-2026-08-30-v3` only for its dedicated metric. Registered scope
includes periodic 3D GW, strict-2D GW, molecular Delta-Sternheimer RPA, and
solid Delta-Sternheimer RPA, but registration does not imply executable or
scientific acceptance.

Profile `abacus-librpa-2026-09-03-strict2d-sos-rpa-v2` is `ENABLED` only for
reference-bounded benchmark `strict2d-sos-rpa-mos2-qavg-v1`; it is not
strict-2D GW acceptance and makes no asymptotic exponent claim.

Never bypass MCP inside this experimental lane. Do not relax its scope to make
a case pass. Return unsupported work to the stable skill in a fresh task or
continue the user's already reviewed external workflow without changing it.

FHI-aims writes on existing reviewed routes; use their ownership gate.
Symmetry comes from `stru_out`; copy no sidecars. PyATB dimensions must match
ABACUS and `bz_sampling_out`.
