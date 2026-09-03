# Periodic 3D GW Current-Stack Benchmark Plan

**Goal:** Freeze the 2026-09-03 Fisherd bulk-BN replay as a current-stack L3
benchmark without promoting it to a scientific reference.

### Task 1: Run the current producer

- [x] Run current ABACUS SCF with symmetry and reader-v1 output.
- [x] Verify 24 operations in `stru_out` and no copied legacy sidecars.
- [x] Run current NSCF with `symmetry = -1` and preprocess the band path.

### Task 2: Separate consumer and end-to-end controls

- [x] Compare all 208 regular-grid QP rows with the official reference.
- [x] Run current LibRPA on the complete official frozen dataset.
- [x] Compare current output across `1x48` and `4x1` layouts.
- [x] Isolate the historical degenerate-gauge mismatch with mixed datasets.

### Task 3: Freeze and publish the verdict

- [x] Add a machine-readable live receipt and regression tests.
- [x] Document the interface/scientific acceptance boundary.
- [x] Update the benchmark matrix and active GW route guide.
- [x] Run all local verification, mirror the installed skill, commit, and push.
