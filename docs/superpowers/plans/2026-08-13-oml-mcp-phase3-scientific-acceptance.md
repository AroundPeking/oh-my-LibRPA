# OML MCP Phase 3 Scientific Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add version-blocked strict-2D discovery plus definition-matched and convergence-based scientific acceptance for the approved 3D periodic GW route.

**Architecture:** Keep profile capability policy, scientific parsing/evaluation, registry lookup, persistence, and MCP transport in separate modules. `finalize_case` resolves administrator-managed identifiers, reads only immutable passed-run snapshots, writes one immutable scientific report, and lets `score_case` consume that report without inferring validity from scheduler or artifact completion.

**Tech Stack:** Python 3.11+, standard library dataclasses/JSON/SQLite, MCP 2.x, unittest, existing OML execution profiles and immutable run snapshots, ABACUS/LibRPA/PyATB on DF Slurm.

---

## File Structure

- Modify `profiles/abacus-librpa-pyatb-2026-08.json` and its packaged copy: declare route capabilities.
- Modify `oml_mcp/profiles.py`: validate capability records.
- Modify `oml_mcp/planner.py`, `oml_mcp/validators.py`, and `oml_mcp/materializer.py`: expose and enforce the deferred 2D route.
- Create `oml_mcp/scientific_bands.py`: parse KS/EXX/GW tables and select the insulating state window.
- Create `oml_mcp/scientific_definition.py`: build and compare canonical physical-definition signatures.
- Create `oml_mcp/scientific_evaluation.py`: evaluate definition-matched regression and single-axis convergence.
- Create `oml_mcp/scientific_registry.py`: resolve typed benchmark and convergence IDs without arbitrary paths.
- Create `oml_mcp/scientific_benchmarks/bn-reader-v1-3d-v1.json`: versioned BN policy with no accepted reference yet.
- Modify `oml_mcp/state.py`: persist immutable scientific reports.
- Modify `oml_mcp/control.py`: implement `finalize_case` and bind reports to passed LibRPA snapshots.
- Modify `oml_mcp/evals.py`: consume only matching persisted reports.
- Modify `oml_mcp/server.py`: expose the bounded `finalize_case` MCP tool.
- Modify version metadata, thin skill, installation guide, controlled-execution guide, benchmark documentation, and tests.

### Task 1: Version-Gated Strict-2D Capability

**Files:**
- Modify: `profiles/abacus-librpa-pyatb-2026-08.json`
- Modify: `oml_mcp/profiles/abacus-librpa-pyatb-2026-08.json`
- Modify: `oml_mcp/profiles.py`
- Modify: `oml_mcp/planner.py`
- Modify: `oml_mcp/validators.py`
- Modify: `oml_mcp/materializer.py`
- Test: `tests/test_profiles.py`
- Test: `tests/test_intake_planner.py`
- Test: `tests/test_validators.py`
- Test: `tests/test_materializer.py`

- [ ] **Step 1: Write failing capability-schema and route tests**

Add assertions equivalent to:

```python
profile = load_profile()
blocked = profile["capabilities"]["strict_2d_gw"]
self.assertEqual(blocked["status"], "BLOCKED")
self.assertEqual(blocked["reason_code"], "LIBRPA_070_STRICT_2D_INVALID")

plan = plan_case(root, task="gw", system_type="2d")
self.assertEqual(plan.route, "strict_2d_gw_deferred")
self.assertEqual(plan.stages, ())
self.assertEqual(plan.gates[0].status, "WARN")

report = validate_case(root, task="gw", system_type="2d", stage="input")
self.assertEqual(self.gate(report, "route.strict_2d_capability").status, "FAIL")

with self.assertRaises(OMLError) as raised:
    prepare_run(source, plan.digest, profile, execution_receipt=receipt)
self.assertEqual(raised.exception.code, "CAPABILITY_BLOCKED")
self.assertEqual(tuple(profile.allowed_run_roots[0].glob("run-*")), ())
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_profiles tests.test_intake_planner tests.test_validators tests.test_materializer
```

Expected: failures for missing `capabilities`, missing deferred route, and the old generic `ROUTE_NOT_EXECUTABLE` error.

- [ ] **Step 3: Add and validate capability records**

Add identical profile records:

```json
"capabilities": {
  "periodic_3d_gw": {"status": "ENABLED"},
  "strict_2d_gw": {
    "status": "BLOCKED",
    "reason_code": "LIBRPA_070_STRICT_2D_INVALID",
    "component": "librpa",
    "component_revision": "dd169fa11fa920d580d4f39dc11e218a7f17f7b5",
    "enablement_requires": [
      "replacement pinned LibRPA revision with the strict-2D defect fixed",
      "definition-matched strict-2D regression fixtures",
      "finite-q and Gamma head/wing acceptance tests",
      "vacuum, in-plane k-grid, and final GW convergence gates"
    ]
  }
}
```

In `validate_profile`, require `periodic_3d_gw.status == "ENABLED"`, require the blocked record fields, and require its component revision to equal the pinned LibRPA revision.

- [ ] **Step 4: Implement deferred planning and hard execution blocking**

Add:

```python
ROUTE_STAGES["strict_2d_gw_deferred"] = ()
```

Route 2D separately from 3D, add a `WARN` plan gate with the profile reason and repair action, and include the capability record in `options["capability"]`. Make `_route_policy_gate` return `route.strict_2d_capability = FAIL`. In `prepare_run`, detect this route immediately after digest matching and raise:

```python
raise OMLError(
    "CAPABILITY_BLOCKED",
    "strict 2D GW is blocked for the pinned LibRPA 0.7.0 profile",
    evidence=(profile_id, reason_code, component_revision),
    recovery="pin a corrected LibRPA profile and add the required strict-2D gates before execution",
)
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Commit the capability boundary**

```bash
git add profiles oml_mcp/profiles oml_mcp/profiles.py oml_mcp/planner.py oml_mcp/validators.py oml_mcp/materializer.py tests/test_profiles.py tests/test_intake_planner.py tests/test_validators.py tests/test_materializer.py
git commit -m "Block strict 2D for LibRPA 0.7.0"
```

### Task 2: GW Band Parsing and Low-Energy Window

**Files:**
- Create: `oml_mcp/scientific_bands.py`
- Create: `tests/test_scientific_bands.py`

- [ ] **Step 1: Write failing parser and state-window tests**

Create fixtures with reordered k-point rows and bands around four occupied states. Test:

```python
bundle = load_band_bundle(root)
window = select_insulating_window(bundle, occupied_value=2.0, padding=3)
self.assertEqual(window["vbm_band"], 4)
self.assertEqual(window["cbm_band"], 5)
self.assertEqual(window["band_start"], 1)
self.assertEqual(window["band_stop"], 8)
self.assertEqual(window["state_count"], 16)  # two k-points x eight bands
self.assertAlmostEqual(window["fundamental_gw_gap_ev"], 1.25)
```

Also test duplicate periodic coordinates, inconsistent row widths, KS/EXX/GW shape mismatch, NaN, partial occupation, changing occupied count, and equivalent coordinates such as `0.5` and `-0.5`.

- [ ] **Step 2: Run the new test and verify RED**

```bash
.venv/bin/python -m unittest tests.test_scientific_bands
```

Expected: import failure because `oml_mcp.scientific_bands` does not exist.

- [ ] **Step 3: Implement typed parsing and periodic state identity**

Implement these public interfaces:

```python
class ScientificBandError(ValueError):
    code: str
    details: dict[str, object]

def parse_band_table(path: str | Path, *, quantity: str) -> dict[str, object]: ...
def load_band_bundle(root: str | Path) -> dict[str, object]: ...
def select_insulating_window(
    bundle: dict[str, object], *, occupied_value: float = 2.0, padding: int = 3
) -> dict[str, object]: ...
```

Normalize each fractional coordinate modulo one with a `1e-8` boundary snap, key states by `(spin, normalized_kpoint, one_based_band)`, and reject non-finite values before building the bundle. Return JSON-compatible dictionaries with energies in eV and explicit worst-case evidence fields.

- [ ] **Step 4: Implement conservative QPE diagnostics**

Add:

```python
def inspect_qpe_diagnostics(root: str | Path) -> dict[str, object]: ...
```

Scan every safe LibRPA rank-0/main log for `QPE failed`, invalid Padé/analytic-continuation markers, unstable-root markers, `nan`, and `inf`. Report matching file and line excerpts. Any explicit unmatched failure is conservatively attached to the complete evaluated window rather than ignored.

- [ ] **Step 5: Run the new tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Commit the parser**

```bash
git add oml_mcp/scientific_bands.py tests/test_scientific_bands.py
git commit -m "Parse GW state windows for scientific checks"
```

### Task 3: Canonical Physical-Definition Signatures

**Files:**
- Modify: `oml_mcp/parsers.py`
- Create: `oml_mcp/scientific_definition.py`
- Create: `tests/test_scientific_definition.py`
- Modify: `tests/test_parsers.py`

- [ ] **Step 1: Write failing KPT and signature tests**

Test Gamma meshes and line paths, then create two run receipts that differ only by `nfreq`:

```python
left = build_definition_signature(left_run)
right = build_definition_signature(right_run)
diff = compare_definitions(left, right)
self.assertEqual([item["field"] for item in diff], ["librpa.nfreq"])
self.assertNotEqual(left["digest"], right["digest"])

allowed = compare_definitions(left, right, allowed_axis="nfreq")
self.assertEqual(allowed, [])
```

Test changes in PP SHA, `use_fullcoul_exx`, head/wing, k-grid, `nbands`, and software revision. Test that an `nfreq` comparison changing PP at the same time is rejected.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_parsers tests.test_scientific_definition
```

Expected: missing KPT/signature APIs.

- [ ] **Step 3: Add deterministic KPT parsers**

Implement:

```python
def parse_abacus_kpt(path: str | Path) -> dict[str, object]: ...
```

Return either `{"mode": "mesh", "grid": [nx, ny, nz], "offset": [...]}` or `{"mode": "path", "points": [...], "segments": [...]}` and reject unsupported/malformed modes.

- [ ] **Step 4: Build canonical signatures from immutable receipts**

Implement:

```python
CONVERGENCE_AXES = {
    "nfreq": {"librpa.nfreq"},
    "empty_states": {"abacus.nbands"},
    "screening_kgrid": {"kpoints.scf_grid"},
}

def build_definition_signature(run_root: str | Path) -> dict[str, object]: ...
def compare_definitions(
    left: dict[str, object],
    right: dict[str, object],
    *,
    allowed_axis: str | None = None,
) -> list[dict[str, object]]: ...
```

Read only `.oml/plan.json`, `.oml/execution.json`, `.oml/manifest.json`, approved input files, and their recorded SHA-256 values. Include every field listed in the design specification, serialize with `digest_json`, and return field-level old/new differences.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Commit definition signatures**

```bash
git add oml_mcp/parsers.py oml_mcp/scientific_definition.py tests/test_parsers.py tests/test_scientific_definition.py
git commit -m "Fingerprint GW physical definitions"
```

### Task 4: Benchmark Registry and Definition-Matched Regression

**Files:**
- Create: `oml_mcp/scientific_registry.py`
- Create: `oml_mcp/scientific_evaluation.py`
- Create: `oml_mcp/scientific_benchmarks/bn-reader-v1-3d-v1.json`
- Modify: `pyproject.toml`
- Create: `tests/test_scientific_registry.py`
- Create: `tests/test_scientific_evaluation.py`

- [ ] **Step 1: Write failing registry and 1 meV boundary tests**

Test identifier-only resolution and exact boundaries:

```python
report = evaluate_regression(candidate, reference, tolerance_ev=0.001)
self.assertEqual(report["status"], "PASS")
self.assertEqual(report["max_abs_error_ev"], 0.001)

candidate_over = shifted(reference, state=worst, delta_ev=0.001001)
self.assertEqual(
    evaluate_regression(candidate_over, reference, tolerance_ev=0.001)["status"],
    "FAIL",
)

mismatch = evaluate_regression(candidate, reference_with_other_nfreq, tolerance_ev=0.001)
self.assertEqual(mismatch["status"], "NOT_EVALUATED")
self.assertEqual(mismatch["reason_code"], "DEFINITION_MISMATCH")
```

Reject benchmark IDs containing `/`, `..`, or absolute paths. Verify a profile-private registry root takes precedence over the packaged policy, while both must pass schema validation.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_scientific_registry tests.test_scientific_evaluation
```

Expected: missing registry and evaluator modules.

- [ ] **Step 3: Implement identifier-only registry lookup**

Implement:

```python
def load_benchmark(benchmark_id: str, roots: tuple[Path, ...] = ()) -> dict[str, object]: ...
def load_convergence_bundle(bundle_id: str, roots: tuple[Path, ...] = ()) -> dict[str, object]: ...
```

Resolve roots from `OML_SCIENCE_REGISTRY_ROOTS`, then packaged data. Require schema version, identifier equality, tolerances, required axes, approval state, and complete provenance. Do not accept a path argument from MCP.

- [ ] **Step 4: Implement definition-matched state comparison**

Implement:

```python
def evaluate_regression(
    candidate: dict[str, object],
    reference: dict[str, object] | None,
    *,
    tolerance_ev: float,
) -> dict[str, object]: ...
```

Return max/RMS errors for KS, EXX, and GW, the worst state and values, exact state-set differences, definition differences, QPE evidence, and status `PASS`, `FAIL`, or `NOT_EVALUATED`. A missing or unapproved reference returns `NOT_EVALUATED`.

- [ ] **Step 5: Add the BN policy without inventing a reference**

Create a packaged policy containing:

```json
{
  "schema_version": 1,
  "benchmark_id": "bn-reader-v1-3d-v1",
  "system_type": "solid",
  "regression_tolerance_ev": 0.001,
  "convergence_tolerance_ev": 0.05,
  "state_window": {"below_vbm": 3, "above_cbm": 3},
  "required_axes": ["nfreq", "empty_states", "screening_kgrid"],
  "reference": null,
  "reference_status": "NOT_AVAILABLE"
}
```

Package `scientific_benchmarks/*.json` in `pyproject.toml`.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 7: Commit registry and regression evaluation**

```bash
git add oml_mcp/scientific_registry.py oml_mcp/scientific_evaluation.py oml_mcp/scientific_benchmarks pyproject.toml tests/test_scientific_registry.py tests/test_scientific_evaluation.py
git commit -m "Evaluate definition-matched GW regressions"
```

### Task 5: Single-Axis 0.05 eV Convergence

**Files:**
- Modify: `oml_mcp/scientific_evaluation.py`
- Modify: `tests/test_scientific_evaluation.py`
- Create: `benchmarks/replays/periodic-gw-convergence-pass-v1.json`
- Create: `benchmarks/replays/periodic-gw-convergence-incomplete-v1.json`

- [ ] **Step 1: Write failing convergence boundary and axis-isolation tests**

Add:

```python
axis = evaluate_convergence_axis(
    coarse,
    fine,
    axis="nfreq",
    tolerance_ev=0.05,
)
self.assertEqual(axis["status"], "PASS")
self.assertEqual(axis["max_abs_gw_change_ev"], 0.05)
self.assertEqual(axis["gap_change_ev"], 0.05)

self.assertEqual(
    evaluate_convergence_axis(coarse, shifted(fine, delta_ev=0.050001), axis="nfreq", tolerance_ev=0.05)["status"],
    "FAIL",
)

with self.assertRaisesRegex(ScientificEvaluationError, "more than the declared axis"):
    evaluate_convergence_axis(changed_nfreq_and_pp, fine, axis="nfreq", tolerance_ev=0.05)
```

Test missing axes and an explicit QPE marker.

- [ ] **Step 2: Run focused test and verify RED**

```bash
.venv/bin/python -m unittest tests.test_scientific_evaluation
```

Expected: missing convergence APIs.

- [ ] **Step 3: Implement per-axis and aggregate convergence**

Implement:

```python
def evaluate_convergence_axis(
    coarse: dict[str, object],
    fine: dict[str, object],
    *,
    axis: str,
    tolerance_ev: float,
) -> dict[str, object]: ...

def aggregate_convergence(
    reports: dict[str, dict[str, object]],
    *,
    required_axes: tuple[str, ...],
) -> dict[str, object]: ...
```

Compare the common state window, require identical state sets there, report KS/EXX changes, and gate on GW max change plus fundamental-gap change. Return `NOT_EVALUATED` if an axis is missing, and `FAIL` for complete evaluated evidence exceeding a threshold or containing QPE failures.

- [ ] **Step 4: Add frozen scorecard replays**

Add one complete science PASS replay and one missing-axis replay. Keep `periodic-gw-finite-unvalidated-v1.json` unchanged at `INCOMPLETE 55/100`.

- [ ] **Step 5: Run evaluator and scorecard tests and verify GREEN**

```bash
.venv/bin/python -m unittest tests.test_scientific_evaluation tests.test_evals
```

Expected: PASS with boundary values reported exactly.

- [ ] **Step 6: Commit convergence evaluation**

```bash
git add oml_mcp/scientific_evaluation.py tests/test_scientific_evaluation.py benchmarks/replays
git commit -m "Gate GW convergence by low-energy states"
```

### Task 6: Immutable Scientific Reports and `finalize_case`

**Files:**
- Modify: `oml_mcp/state.py`
- Modify: `oml_mcp/control.py`
- Modify: `oml_mcp/evals.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_control.py`
- Modify: `tests/test_evals.py`

- [ ] **Step 1: Write failing persistence, finalization, and scoring tests**

Test an immutable report bound to the final LibRPA attempt:

```python
first = store.record_scientific_report(report)
same = store.record_scientific_report(report)
self.assertEqual(first, same)

with self.assertRaisesRegex(OMLError, "SCIENTIFIC_REPORT_CONFLICT"):
    store.record_scientific_report({**report, "status": "PASS"})

finalized = service.finalize_case(run_id, plan_digest, "bn-reader-v1-3d-v1")
self.assertEqual(finalized["scientific_status"], "NOT_EVALUATED")
self.assertEqual(finalized["regression"]["reason_code"], "REFERENCE_NOT_AVAILABLE")
self.assertTrue(Path(run_dir, ".oml/science", finalized["report_id"] + ".json").is_file())

score = service.score_case(run_id, plan_digest)
self.assertEqual(
    dimension(score, "numerical_scientific_validity")["status"],
    "NOT_EVALUATED",
)
```

Also test missing/pending/failed LibRPA, stale plan digest, changed final attempt, manifest tampering, report/file conflict, and a complete PASS report producing score value `1.0`.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_state tests.test_control tests.test_evals
```

Expected: missing scientific-report state and service APIs.

- [ ] **Step 3: Add immutable SQLite scientific-report storage**

Create a migrated table:

```sql
CREATE TABLE IF NOT EXISTS scientific_reports (
  report_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  plan_digest TEXT NOT NULL,
  benchmark_id TEXT NOT NULL,
  convergence_bundle_id TEXT,
  request_digest TEXT NOT NULL,
  final_attempt_id TEXT NOT NULL REFERENCES stage_attempts(attempt_id),
  manifest_digest TEXT NOT NULL,
  scientific_status TEXT NOT NULL,
  report_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

Implement `record_scientific_report`, `get_scientific_report`, and `latest_scientific_report`. Existing identical content is idempotent; identity/content mismatch raises `SCIENTIFIC_REPORT_CONFLICT`.

- [ ] **Step 4: Implement controlled finalization**

Add:

```python
def finalize_case(
    self,
    run_id: str,
    plan_digest: str,
    benchmark_id: str,
    convergence_bundle_id: str | None = None,
) -> dict[str, Any]: ...
```

Require all planned stages and the latest LibRPA attempt to be `PASSED`, require its accepted immutable stage inspection and snapshot, re-run receipt/manifest/profile checks, load bands and diagnostics from that snapshot, evaluate the registry policy, and bind every comparison run in a convergence bundle to its own passed final snapshot. Write the report path by joining `.oml/science`, the computed report ID, and `.json` via a temporary file plus `os.replace`, then record the exact same payload in SQLite.

- [ ] **Step 5: Make score consumption lineage-strict**

Extend `score_run` with a scientific report only when its run ID, plan digest, manifest digest, profile ID, and final LibRPA attempt match. Map `PASS -> 1.0`, evaluated `FAIL -> 0.0`, and `NOT_EVALUATED/INCOMPLETE -> None`. Add `scientific_report_id` and scientific status to score progress.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 7: Commit finalization and scoring**

```bash
git add oml_mcp/state.py oml_mcp/control.py oml_mcp/evals.py tests/test_state.py tests/test_control.py tests/test_evals.py
git commit -m "Persist immutable GW scientific verdicts"
```

### Task 7: MCP Surface, Documentation, and Version 0.3.0

**Files:**
- Modify: `oml_mcp/server.py`
- Modify: `oml_mcp/__init__.py`
- Modify: `pyproject.toml`
- Modify: `.codex-plugin/plugin.json`
- Modify: `skills/oh-my-librpa/SKILL.md`
- Modify: `docs/guide/installation.md`
- Modify: `docs/guide/controlled-execution.md`
- Modify: `docs/live-benchmarks/2026-08-13-df-bn-reader-v1-shrink.md`
- Modify: `tests/test_server.py`
- Modify: `tests/test_phase2_docs.py`

- [ ] **Step 1: Write failing MCP and documentation tests**

Require `finalize_case` in the exact tool surface, read-write/idempotent annotations, identifier-only schema, version `0.3.0`, and thin-skill ordering `inspect -> execute -> finalize -> score`. Require the guide to contain `LIBRPA_070_STRICT_2D_INVALID`, `0.001 eV`, `0.05 eV`, and `VBM-3`/`CBM+3`.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
.venv/bin/python -m unittest tests.test_server tests.test_phase2_docs
```

Expected: missing tool and old version metadata.

- [ ] **Step 3: Add the bounded MCP tool**

Expose:

```python
@server.tool(
    name="finalize_case",
    description="Evaluate one passed 3D GW run against registered regression and convergence policy.",
    annotations=_write_annotations(idempotent=True),
    structured_output=True,
)
def finalize_case(
    run_id: str,
    plan_digest: str,
    benchmark_id: str,
    execution_profile_id: str,
    convergence_bundle_id: str | None = None,
) -> dict[str, Any]: ...
```

No parameter may contain a path, command, scheduler argument, tolerance, or arbitrary JSON evidence.

- [ ] **Step 4: Update version and concise operating instructions**

Bump all three version surfaces to `0.3.0`. Update the thin skill to require `finalize_case` before treating a completed run as scientifically evaluated, and state that strict 2D is profile-blocked until a corrected LibRPA revision and 2D gates are installed.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 6: Commit MCP and docs**

```bash
git add oml_mcp/server.py oml_mcp/__init__.py pyproject.toml .codex-plugin/plugin.json skills/oh-my-librpa/SKILL.md docs/guide docs/live-benchmarks tests/test_server.py tests/test_phase2_docs.py
git commit -m "Expose controlled GW scientific finalization"
```

### Task 8: Full Local Verification and Skill Synchronization

**Files:**
- Modify only files required by failures found in this task.
- Synchronize: `skills/oh-my-librpa/` -> `/Users/ghj/.codex/skills/oh-my-librpa/`

- [ ] **Step 1: Run the complete Python suite**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Expected: all tests PASS with no errors or warnings that indicate skipped core coverage.

- [ ] **Step 2: Run repository self-test and static checks**

```bash
bash scripts/self_test.sh --workspace "$PWD" --installed-root "$PWD"
git diff --check
```

Expected: all selected tests pass and `git diff --check` is silent.

- [ ] **Step 3: Synchronize the installed thin skill**

Compare while excluding bytecode:

```bash
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' skills/oh-my-librpa/ /Users/ghj/.codex/skills/oh-my-librpa/
diff -qr --exclude='__pycache__' --exclude='*.pyc' skills/oh-my-librpa /Users/ghj/.codex/skills/oh-my-librpa
```

Expected: `diff` is silent.

- [ ] **Step 4: Commit any verification fixes**

```bash
git status --short
git add oml_mcp tests profiles benchmarks pyproject.toml .codex-plugin skills docs/guide docs/live-benchmarks
git commit -m "Complete OML scientific acceptance checks"
```

Skip this commit if verification required no code changes.

### Task 9: DF BN Single-Variable Convergence Campaign

**Files:**
- Create outside git: `/Users/ghj/.config/oh-my-librpa/science/` private benchmark/convergence records.
- Create outside git: fresh immutable sources/runs under the approved OML DF profile roots.
- Modify: `docs/live-benchmarks/2026-08-13-df-bn-reader-v1-shrink.md`

- [ ] **Step 1: Re-inspect the pinned DF profile and binaries**

Through OML MCP, call `inspect_profile`, then inspect the registered DF execution profile. Require exact revisions:

```text
ABACUS 3efad9ed5ca066aee1d1b2214e43f92a2d2a567e
LibRPA dd169fa11fa920d580d4f39dc11e218a7f17f7b5
PyATB 9fb9028c59b1dbaf9cf66965280961fc2225d9eb
```

Expected verdict: `match`. No 2D source or job is prepared.

- [ ] **Step 2: Freeze independent 3D campaign levels**

Starting from the accepted BN reader-v1/symmetry/shrink/cut-EXX source, create fresh source bundles with only these intended changes:

```text
nfreq axis:          6, 12, 16   at nbands=26 and k=2x2x2
empty_states axis:  18, 22, 26  at nfreq=16 and k=2x2x2
screening_kgrid:     2x2x2, 3x3x3, 4x4x4 at nfreq=16 and nbands=26
```

Keep structure, PP, NAO, generated/shrunk ABFS settings, reader-v1, head/wing, Coulomb convention, and all non-axis thresholds fixed. Call `plan_case` and verify definition differences before preparation.

- [ ] **Step 3: Execute one immutable run per unique plan**

For each plan, call MCP `prepare_run`, then the fixed stage sequence:

```text
scf -> pyatb -> nscf -> preprocess -> librpa
```

Observe with `get_status`; inspect only after scheduler completion. Never resubmit while an equivalent job exists, and never reuse a failed run directory. Reuse the already completed `nfreq=6`, `nbands=26`, `k=2x2x2` run only if its exact definition signature matches.

- [ ] **Step 4: Finalize and evaluate each axis**

Register private convergence bundles by stable ID, then call `finalize_case`. Report for each axis:

```text
max low-energy GW change (eV) / threshold 0.05 eV
fundamental-gap change (eV) / threshold 0.05 eV
QPE/NaN/analytic-continuation state
PASS, FAIL, or NOT_EVALUATED
remaining decision
```

Do not create an accepted 1 meV reference. If all axes pass, record the final level only as `CANDIDATE_REFERENCE` for explicit later review.

- [ ] **Step 5: Update the live benchmark record**

Append exact run IDs, Slurm IDs, source and binary hashes, per-axis measurements, thresholds, artifact paths, scorecard verdicts, and unresolved decisions. Explicitly state that strict 2D was not run because the pinned profile reports `LIBRPA_070_STRICT_2D_INVALID`.

- [ ] **Step 6: Re-run local tests after recording live evidence**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
bash scripts/self_test.sh --workspace "$PWD" --installed-root "$PWD"
git diff --check
```

Expected: all tests and self-tests PASS.

### Task 10: Final Commit and Verified Push

**Files:**
- All reviewed Phase 3 code, tests, and documentation from prior tasks.

- [ ] **Step 1: Inspect the final diff and worktree**

```bash
git status --short --branch
git diff --stat origin/codex/oml-mcp-phase2...HEAD
git diff --check origin/codex/oml-mcp-phase2...HEAD
```

Expected: only scoped OML Phase 3 changes, with no generated run data or private registry files tracked.

- [ ] **Step 2: Create the final documentation commit if needed**

```bash
GIT_AUTHOR_NAME='Codex' \
GIT_AUTHOR_EMAIL='codex@openai.com' \
GIT_COMMITTER_NAME='AroundPeking' \
GIT_COMMITTER_EMAIL='gonghuanjing@iphy.ac.cn' \
git commit -m 'Validate 3D GW scientific acceptance'
```

Skip if all changes are already committed.

- [ ] **Step 3: Verify attribution and push**

```bash
git log -1 --format='%H%nAuthor: %an <%ae>%nCommitter: %cn <%ce>%n%s'
git push origin codex/oml-mcp-phase2
git ls-remote --heads origin codex/oml-mcp-phase2
git rev-parse HEAD
```

Expected: author `Codex <codex@openai.com>`, committer `AroundPeking <gonghuanjing@iphy.ac.cn>`, and remote SHA equal to local `HEAD`.
