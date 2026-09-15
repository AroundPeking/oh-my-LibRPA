# NAO Translation-Projector Band Unfolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add the validated exact-supercell NAO unfolding calculation to OML as
a documented, tested Python post-processing module.

**Architecture:** Keep the finite-group projector, ABACUS readers, and path
driver in one focused module because they share a small data contract. Expose a
module command line while leaving plotting and LibRPA execution unchanged.

**Tech Stack:** Python 3.11+, NumPy, unittest, ABACUS LCAO output.

---

### Task 1: Freeze The Supported Mathematics

**Files:**
- Create: tests/test_band_unfolding.py
- Create: oml_mcp/band_unfolding.py

- [x] Write tests for folded sectors, atom translation permutations, boundary
  Bloch phases, nonorthogonal projector weights, and sector completeness.
- [x] Run the focused test and confirm it fails because the module is absent.
- [x] Implement the minimal pure-mathematics API and make the tests pass.

### Task 2: Add ABACUS Readers And Path Driver

**Files:**
- Modify: tests/test_band_unfolding.py
- Modify: oml_mcp/band_unfolding.py

- [x] Add tests for CSR overlap records, positive Fourier phase, complex-LCAO
  binaries, Direct-coordinate inputs, and one synthetic end-to-end path.
- [x] Confirm the new tests fail for the missing readers and driver.
- [x] Implement the readers, CSV/JSON output, and
  python -m oml_mcp.band_unfolding entry point.
- [x] Add fail-closed tests for multi-element structures without per-atom NAO
  metadata, non-exact translations, non-Direct structures, and spin/SOC
  requests.

### Task 3: Document Scope And Verify

**Files:**
- Create: docs/guide/nao-band-unfolding.md
- Modify: README.md

- [x] Document the formulas, file inputs, command line, output fields,
  diagnostics, supported scope, and PyATB comparison.
- [x] Run tests/test_band_unfolding.py, tests/test_scientific_bands.py, and
  the complete OML test suite.
- [x] Run static Python compilation and inspect the final diff without touching
  unrelated untracked files.
