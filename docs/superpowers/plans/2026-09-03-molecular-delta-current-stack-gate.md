# Molecular Delta-ST Current-Stack Gate Implementation Plan

> **For agentic workers:** Execute each checked task in order and preserve the
> distinction between producer completion, handoff acceptance, and scientific
> acceptance.

**Goal:** Freeze the 2026-09-03 Fisherd H2 replay as a current-stack negative
compatibility benchmark without promoting the molecular Delta-ST route.

**Architecture:** Keep the accepted v3 handoff receipt immutable. Add a second
live receipt for current `master_ghj`, a regression test over its hard gates,
and concise documentation in the benchmark matrix and Delta-ST route guide.

**Tech Stack:** JSON evidence, Python `unittest`, Markdown, Fisherd ABACUS and
LibRPA binaries.

---

### Task 1: Freeze the expected compatibility verdict

**Files:**
- Create: `tests/test_fisherd_molecular_delta_current.py`
- Create: `benchmarks/live/fisherd-molecular-delta-current-2026-09-03.json`

- [x] Require exact revisions, executable hashes, clean source, and 7/7 tests.
- [x] Require a successful 30-equation FD8 producer with bounded residuals.
- [x] Require the missing dedicated metric to block the handoff.
- [x] Require the ordinary-metric result to remain diagnostic only.
- [x] Require scientific and promotion status to stay blocked.

### Task 2: Publish the evidence boundary

**Files:**
- Create: `docs/live-benchmarks/2026-09-03-fisherd-molecular-delta-current.md`
- Modify: `docs/benchmarks/benchmark-matrix-v1.md`
- Modify: `skills/oh-my-librpa/references/delta-st-route.md`

- [x] Record the live producer and matrix-comparison measurements.
- [x] Explain why the finite diagnostic energy is not an accepted result.
- [x] Keep the molecular benchmark row `REFERENCE_PENDING`.
- [x] Mirror the active installed OML route guide byte-for-byte.

### Task 3: Verify and publish

- [x] Run the focused new test and existing Sternheimer tests.
- [x] Run the complete unittest suite and repository self-test.
- [x] Build wheel and source distributions.
- [x] Review the diff and confirm the historical v3 receipt is unchanged.
- [x] Commit with the configured author/committer attribution.
- [x] Push the branch and verify the remote head.
