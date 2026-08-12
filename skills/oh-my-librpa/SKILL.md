---
name: oh-my-librpa
description: Use when users ask to prepare, inspect, validate, run, debug, or regression-test ABACUS or FHI-aims workflows that feed LibRPA GW/RPA calculations.
---

# Oh-My-LibRPA

Use the OML MCP before loading detailed workflow references.

1. Call `inspect_profile` to establish the pinned ABACUS `master_ghj`, LibRPA `v0.7.0`, and PyATB `enable_head_wing` contract.
2. Call `ingest_case` on every provided case directory. Stop on mixed ABACUS/FHI-aims ownership.
3. For ABACUS cases, call `plan_case`, then `validate_case` at `input` or `pre_librpa` stage. Repair every `FAIL`; report every `WARN`.
4. Use `inspect_reader_v1` for eigenvector, velocity, or PyATB head/wing artifacts.
5. Only after MCP validation, load the execution route:
   - ABACUS: `skills/oh-my-librpa-abacus-librpa/`
   - FHI-aims single-shot GW: `skills/oh-my-librpa-fhi-aims-g0w0-band/`
   - FHI-aims QSGW: `skills/oh-my-librpa-fhi-aims-qsgw/`
   - LibRPA regression work: `references/regression-route.md`
   - Delta-Sternheimer: `references/delta-st-route.md`

Ownership markers: ABACUS uses `INPUT*`, `KPT*`, and `STRU`; FHI-aims uses `control.in` plus explicit FHI-aims intent. Treat as supporting markers only: `geometry.in`, `librpa.d/`, `self_energy/`.

Real physics compute runs on a server in a fresh directory. Local work is limited to inspection, staging, parsing, and plotting. Do not submit, overwrite source data, or trust results until the pinned source revisions and pre-run gates pass.
