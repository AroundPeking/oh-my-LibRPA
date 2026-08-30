# Fisherd OML v2 Admission Execution Plan

> **Execution policy:** Run this plan autonomously in order. Do not promote a
> route from scheduler or process completion alone; preserve separate process,
> numerical, and scientific gates.

**Goal:** Build the pinned ABACUS, LibRPA, and PyATB sources in a clean Fisherd
campaign and obtain reproducible L0-L3 evidence for periodic 3D GW, strict-2D
GW, molecular Delta-ST RPA, and solid Delta-ST RPA.

**Machine contract:** The executable checklist is
`admission/fisherd-v2-2026-08-30.json`. It fixes the source revisions, reader-v1
handoff, `stru_out` symmetry source, full-Ewald strict-2D production route,
compile limit of 16 jobs, execution limit of 48 threads, and remote campaign
root `/home/ghj/oml-admission/20260830-v2`.

---

### Task 1: Freeze and Verify the Campaign Definition

**Files:**
- `admission/fisherd-v2-2026-08-30.json`
- `oml_mcp/admission_manifests/fisherd-v2-2026-08-30.json`
- `oml_mcp/admission_manifest.py`
- `tests/test_admission_manifest.py`

- [x] Validate the manifest against profile `abacus-librpa-2026-08-30-v2`.
- [x] Require exact ABACUS, LibRPA, and PyATB revisions.
- [x] Require reader v1 and no copied legacy symmetry sidecars.
- [x] Require complete four-route coverage and ordered levels L0-L3.
- [x] Reject compile settings above `-j16` and executions above 48 threads.
- [ ] Commit and push the campaign definition before creating remote outputs.

### Task 2: Create a Fresh Fisherd Campaign Root

- [ ] Confirm the campaign root does not already contain an active attempt.
- [ ] Create `src`, `build`, `logs`, `receipts`, `fixtures`, and `runs` beneath
  the campaign root without changing old Fisherd trees.
- [ ] Record hostname, CPU, memory, OS, oneAPI, compiler, MPI, MKL, CMake, and
  Python fingerprints.
- [ ] Save the manifest and its SHA-256 digest in the campaign root.

**Stop gate:** If an existing attempt is present, inspect and resume it; never
create a duplicate build or calculation.

### Task 3: L0 Clean Checkout and Build

- [ ] Clone each source into its dedicated `src` directory and detach at the
  manifest revision. Initialize only required submodules.
- [ ] Record `HEAD`, submodule revisions, remote URLs, and clean-tree status.
- [ ] Configure LibRPA with Intel MPI/LLVM, MKL, LibRI, and tests enabled.
- [ ] Configure ABACUS with MPI, LibRI, LibComm, GreenX, tests, and debug
  diagnostics enabled; require the `abacus_3p` executable.
- [ ] Build both projects with at most 16 concurrent compile jobs.
- [ ] Validate PyATB import and the head/wing-producing entry points from its
  clean pinned checkout.
- [ ] Emit immutable L0 receipts with build and log hashes.

**Stop gate:** Do not start L1 if a revision is wrong, a tree is dirty, a
configure/build fails, or the required executable/entry point is absent.

### Task 4: L1 Source-Level Contract Tests

- [ ] Enumerate CTest targets before execution and fail if a registered target
  in the manifest is missing.
- [ ] Run LibRPA head/wing, strict-2D metadata, Sternheimer RPA, symmetry, and
  q-sum tests.
- [ ] Run ABACUS 2D Coulomb/Ewald and Sternheimer runtime, Delta, periodic
  solver, and k+q tests, including the four-rank Ewald distribution test.
- [ ] Save per-target logs and an L1 receipt.

**Stop gate:** A source-test failure blocks only its dependent route, but must
not be relabeled as a physical failure. Diagnose before attempting that route's
L2/L3 work.

### Task 5: L2 Existing-Artifact Replays

- [ ] Inventory Fisherd fixtures without modifying their producer outputs.
- [ ] Prefer same-version reader-v1 artifacts; mark older-profile data as
  migration evidence rather than current scientific acceptance.
- [ ] Replay periodic 3D reader-v1 and `stru_out` symmetry reconstruction.
- [ ] Replay strict-2D full-Ewald analytic head/wing data before producing a new
  2D case; do not use cut Coulomb as production evidence.
- [ ] Validate molecular and solid Delta-ST reader-v1 artifacts, finite arrays,
  dimensions, q/frequency identity, and producer completion markers.
- [ ] Emit route-specific L2 receipts.

### Task 6: L3 Bounded End-to-End Smokes

- [ ] Run the smallest complete insulating periodic 3D GW fixture.
- [ ] Run a strict-2D GW smoke only after the replay and source gates pass.
- [ ] Run H2 as the first molecular Delta-ST smoke.
- [ ] Run Si at a representative finite q and imaginary frequency as the first
  solid Delta-ST smoke, including a same-state SOS comparison.
- [ ] Keep each process at or below 48 threads and record CPU, wall, and disk
  use. Do not duplicate any active or complete case.
- [ ] Emit L3 receipts with process, numerical, and scientific statuses kept
  separate.

### Task 7: Integrate Evidence into OML

- [ ] Add the verified receipts and compact evidence summaries to the repo.
- [ ] Update only routes whose required L0-L3 gates pass from `TESTABLE` to
  `EXPERIMENTAL`; `ENABLED` still requires a separate reviewed profile commit.
- [ ] Encode observed failure signatures and narrow recovery proposals without
  adding arbitrary remote-command execution to MCP.
- [ ] Run the full unit suite, explicit-workspace self-test, build/package
  checks, and manifest consistency check.
- [ ] Commit and push the integrated admission evidence.
