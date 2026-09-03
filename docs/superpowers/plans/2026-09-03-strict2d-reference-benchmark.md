# Strict-2D Reference Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a machine-evaluated MoS2 four-mesh L4 benchmark and an immutable production profile for strict-2D SOS-RPA.

**Architecture:** Keep the existing L3 profile and manifest unchanged. Add a route-benchmark registry/evaluator, expose it through MCP, and create a new L4 profile whose production claim points to the passing benchmark.

**Tech Stack:** Python 3.11, JSON registry files, unittest, FastMCP.

---

### Task 1: Freeze the benchmark contract

**Files:**
- Create: `tests/test_route_benchmark.py`
- Create: `benchmarks/routes/strict2d-sos-rpa-mos2-qavg-v1.json`
- Create: `oml_mcp/route_benchmarks/strict2d-sos-rpa-mos2-qavg-v1.json`
- Create: `oml_mcp/route_benchmark.py`

- [x] Write tests for schema validation, immutable identity, derived metrics, passing evaluation, and one-gate failure.
- [x] Run the new test file and verify that imports or registry lookup fail before implementation.
- [x] Implement registry loading, validation, metric calculation, and non-compensating gates.
- [x] Run the new test file and verify all route-benchmark tests pass.

### Task 2: Add the L4 profile without rewriting L3 history

**Files:**
- Modify: `tests/test_strict2d_sos_rpa_route.py`
- Modify: `oml_mcp/profiles.py`
- Modify: `oml_mcp/planner.py`
- Modify: `oml_mcp/validators.py`
- Create: `profiles/abacus-librpa-strict2d-sos-rpa-2026-09-v2.json`
- Create: `oml_mcp/profiles/abacus-librpa-strict2d-sos-rpa-2026-09-v2.json`

- [x] Write tests that require the historical v1 profile to remain TESTABLE/L3 and the new v2 profile to be ENABLED/L4.
- [x] Run the strict-2D test file and verify the new-profile tests fail.
- [x] Register the new profile family, validate its benchmark-bound acceptance contract, and allow planner/validator selection.
- [x] Run the strict-2D and route-benchmark tests and verify they pass.

### Task 3: Expose the benchmark through MCP

**Files:**
- Modify: `tests/test_route_benchmark.py`
- Modify: `oml_mcp/server.py`

- [x] Write async tests for `inspect_route_benchmark` and `evaluate_route_benchmark`.
- [x] Run the async tests and verify the tools are absent.
- [x] Register both MCP tools and map validation errors into structured tool errors.
- [x] Run the async tests and verify both tools return structured PASS evidence.

### Task 4: Publish the benchmark matrix and user guidance

**Files:**
- Create: `docs/benchmarks/benchmark-matrix-v1.md`
- Modify: `README.md`
- Modify: `docs/guide/installation.md`
- Modify: `docs/live-benchmarks/2026-09-02-df-dcu-strict2d-sos-rpa.md`
- Modify: `skills/abacus-librpa-rpa/SKILL.md`
- Modify: `skills/abacus-librpa-version-guard/SKILL.md`
- Modify: `skills/oh-my-librpa/references/rpa-route.md`

- [x] Add documentation tests that distinguish operational convergence from an asymptotic exponent claim and SOS-RPA from GW.
- [x] Update the live benchmark conclusion, profile tables, route guidance, and future material matrix.
- [x] Mirror the affected installed Codex skills and verify byte identity.

### Task 5: Verify, commit, and push

- [x] Run `python -m unittest tests.test_route_benchmark tests.test_strict2d_sos_rpa_route`.
- [x] Run the complete unittest suite and `scripts/self_test.sh --workspace "$PWD"`.
- [x] Build the wheel and source distribution.
- [x] Review the diff for accidental historical-profile or unrelated-file changes.
- [x] Commit with Codex as author and AroundPeking as committer.
- [x] Push the feature branch and verify the remote head.

### Task 6: Freeze the evaluator regression suite

- [x] Add one known-good and ten blocked route fixtures.
- [x] Report false-pass, false-block, and fixture-receipt mismatch separately.
- [x] Expose read-only suite replay through MCP.
- [x] Re-run tests, package smoke tests, commit, and push.
