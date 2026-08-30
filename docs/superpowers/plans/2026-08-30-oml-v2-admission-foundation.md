# OML v2 Admission Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second pinned compatibility generation, four testable route plans, immutable admission receipts, controlled one-axis evolution proposals, and a non-compensating v2 scorecard without changing OML 0.3.1 behavior.

**Architecture:** Keep the old profile as the default and add a profile registry keyed by immutable profile ID. Route planning receives an explicit profile ID and response method; admission receipts and evolution proposals are pure deterministic modules so Fisherd execution can consume them without embedding remote commands in the MCP API.

**Tech Stack:** Python 3.11+, dataclasses, JSON, SHA-256 canonical digests, unittest, MCP stdio server.

---

### Task 1: Register and Validate the v2 Compatibility Profile

**Files:**
- Modify: `oml_mcp/profiles.py`
- Create: `oml_mcp/profiles/abacus-librpa-pyatb-2026-08-v2.json`
- Create: `profiles/abacus-librpa-pyatb-2026-08-v2.json`
- Modify: `tests/test_profiles.py`

- [x] **Step 1: Write failing registry and v2 contract tests**

Add tests which call `list_profiles()` and
`load_profile(profile_id="abacus-librpa-2026-08-30-v2")`, then assert the three
pinned revisions, four `TESTABLE` capabilities, admission levels `L0` through
`L4`, reader-v1 production values, `stru_out` symmetry source, and an empty
legacy-sidecar copy list. Assert an unknown profile ID raises `ProfileError`.

- [x] **Step 2: Run the focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_profiles -v`

Expected: FAIL because `list_profiles` and the v2 registry do not exist.

- [x] **Step 3: Add the profile registry and schema-v2 validator**

Implement these public interfaces while retaining `load_profile()` as the old
default:

```python
PROFILE_NAMES = {
    "abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08":
        "abacus-librpa-pyatb-2026-08.json",
    "abacus-librpa-2026-08-30-v2":
        "abacus-librpa-pyatb-2026-08-v2.json",
}

def list_profiles() -> Sequence[str]:
    return tuple(PROFILE_NAMES)

def load_profile(
    path: str | Path | None = None,
    *,
    profile_id: str | None = None,
) -> dict[str, Any]:
    if path is not None and profile_id is not None:
        raise ProfileError("path and profile_id are mutually exclusive")
    if path is not None:
        selected = Path(path)
    else:
        selected_id = profile_id or DEFAULT_PROFILE_ID
        try:
            selected = packaged_profile_dir() / PROFILE_NAMES[selected_id]
        except KeyError as exc:
            raise ProfileError(f"unknown profile_id: {selected_id}") from exc
    data = json.loads(selected.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProfileError("profile root must be an object")
    validate_profile(data)
    return data
```

Schema v1 keeps the exact old capability constraints. Schema v2 accepts only
`BLOCKED`, `TESTABLE`, `EXPERIMENTAL`, or `ENABLED`, requires all four route
capabilities, and validates the profile's admission-level and reader-v1
contract objects.

- [x] **Step 4: Run profile tests and confirm GREEN**

Run: `.venv/bin/python -m unittest tests.test_profiles -v`

Expected: all profile tests pass.

- [x] **Step 5: Commit Task 1**

Commit message: `Add OML v2 compatibility profile`

### Task 2: Plan the Four v2 Testable Routes

**Files:**
- Modify: `oml_mcp/planner.py`
- Modify: `oml_mcp/control.py`
- Modify: `oml_mcp/materializer.py`
- Modify: `oml_mcp/server.py`
- Modify: `tests/test_intake_planner.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing route-planning tests**

Add tests for these explicit calls and stage graphs:

```python
plan_case(root, task="gw", system_type="2d", profile_id=V2_PROFILE_ID)
# strict_2d_gw: scf, pyatb, nscf, preprocess, librpa

plan_case(
    root,
    task="rpa",
    system_type="molecule",
    response_method="sternheimer",
    profile_id=V2_PROFILE_ID,
)
# molecular_delta_st_rpa: ground_state, sternheimer, librpa

plan_case(
    root,
    task="rpa",
    system_type="solid",
    response_method="sternheimer",
    profile_id=V2_PROFILE_ID,
)
# solid_delta_st_rpa: ground_state, sternheimer, librpa
```

Assert every v2 plan contains its `TESTABLE` capability and reader format
`v1`. Assert the old default strict-2D plan remains deferred and stage-free.

- [ ] **Step 2: Run planner tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_intake_planner -v`

Expected: FAIL because `profile_id` and `response_method` are unsupported.

- [ ] **Step 3: Implement profile-aware deterministic planning**

Add route stages:

```python
"strict_2d_gw": ("scf", "pyatb", "nscf", "preprocess", "librpa"),
"molecular_delta_st_rpa": ("ground_state", "sternheimer", "librpa"),
"solid_delta_st_rpa": ("ground_state", "sternheimer", "librpa"),
```

Include `profile_id`, `response_method`, `reader_format`, and the selected
capability in the plan digest. A `TESTABLE` capability returns a warning that
only registered admission execution is permitted. Preserve all old route
digests when the new arguments are omitted.

Update source-plan reproduction to pass the stored profile and response method.
Keep v2 routes blocked from the existing production materializer with stable
`ADMISSION_ONLY_ROUTE` evidence until the Fisherd admission executor is added.

- [ ] **Step 4: Expose the new read-only planner parameters through MCP**

Extend `inspect_profile` with `profile_id` and extend `plan_case` with optional
`profile_id` and `response_method: Literal["sos", "sternheimer"]`. Do not add an
arbitrary command parameter.

- [ ] **Step 5: Run planner and MCP tests and confirm GREEN**

Run: `.venv/bin/python -m unittest tests.test_intake_planner tests.test_server -v`

Expected: all focused tests pass and old default route assertions remain green.

- [ ] **Step 6: Commit Task 2**

Commit message: `Plan OML v2 admission routes`

### Task 3: Add Immutable Admission Receipts

**Files:**
- Create: `oml_mcp/admission.py`
- Create: `tests/test_admission.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing receipt tests**

Test `build_admission_receipt()` with pinned revisions, build hashes, host,
input manifest digest, stage, resources, process status, gates, scientific
status, and promotion eligibility. Assert equivalent input returns the same
receipt digest, a non-SHA build fingerprint is rejected, resource use above 16
compile jobs or 48 execution threads is rejected, and `ENABLED` promotion
eligibility is rejected by this builder.

- [ ] **Step 2: Run receipt tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_admission -v`

Expected: FAIL because `oml_mcp.admission` does not exist.

- [ ] **Step 3: Implement deterministic receipt construction**

Create frozen `AdmissionResources` and `AdmissionReceipt` dataclasses:

```python
@dataclass(frozen=True)
class AdmissionResources:
    compile_jobs: int = 0
    execution_threads: int = 1
    cpu_hours: float = 0.0
    wall_seconds: int = 0
    disk_bytes: int = 0

@dataclass(frozen=True)
class AdmissionReceipt:
    payload: dict[str, object]
    receipt_digest: str
```

Implement `build_admission_receipt` with the complete keyword interface listed
in Step 1. Canonical JSON excluding `receipt_digest` supplies the SHA-256
receipt digest.

- [ ] **Step 4: Run receipt tests and confirm GREEN**

Run: `.venv/bin/python -m unittest tests.test_admission -v`

Expected: all admission receipt tests pass.

- [ ] **Step 5: Commit Task 3**

Commit message: `Add immutable admission receipts`

### Task 4: Add Controlled Evolution Proposals

**Files:**
- Create: `oml_mcp/evolution.py`
- Create: `tests/test_evolution.py`

- [ ] **Step 1: Write failing mutation-policy tests**

Test route registries for 3D GW, strict-2D Ewald GW, molecular Delta-ST, and
solid Delta-ST. Test that `propose_candidate()` permits one registered axis,
rejects two changed axes, rejects an unregistered key, rejects a duplicate
definition digest, rejects exhausted candidate/CPU/wall/disk budgets, and
returns `PROPOSAL_ONLY` with no submission command.

- [ ] **Step 2: Run evolution tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_evolution -v`

Expected: FAIL because `oml_mcp.evolution` does not exist.

- [ ] **Step 3: Implement route registries and proposal validation**

Create frozen `EvolutionBudget`, `EvolutionUsage`, and `CandidateProposal`
dataclasses. Register exact parameter keys by route:

```python
ROUTE_MUTATION_AXES = {
    "periodic_gw": frozenset({"nfreq", "nbands", "screening_kgrid", "nao_family", "abfs_family", "shrink_threshold"}),
    "strict_2d_gw": frozenset({"nfreq", "nbands", "in_plane_kgrid", "vacuum", "ewald_precision"}),
    "molecular_delta_st_rpa": frozenset({"box_size", "nfreq", "grid_cutoff", "pca_threshold", "occupied_basis"}),
    "solid_delta_st_rpa": frozenset({"grid_cutoff", "nfreq", "pca_threshold", "coulomb_metric", "kq_sampling"}),
}
```

Implement `propose_candidate` with the baseline, candidate, existing digest,
budget, and usage keyword inputs from Step 1. The proposal records exactly one
changed axis and a canonical definition digest. It has status `PROPOSAL_ONLY`
and contains no execution method.

- [ ] **Step 4: Run evolution tests and confirm GREEN**

Run: `.venv/bin/python -m unittest tests.test_evolution -v`

Expected: all controlled-evolution tests pass.

- [ ] **Step 5: Commit Task 4**

Commit message: `Add controlled evolution proposals`

### Task 5: Add the Non-Compensating v2 Scorecard

**Files:**
- Create: `benchmarks/scorecard-v2.json`
- Create: `oml_mcp/benchmarks/scorecard-v2.json`
- Modify: `oml_mcp/evals.py`
- Modify: `pyproject.toml`
- Modify: `tests/test_evals.py`

- [ ] **Step 1: Write failing v2 scorecard tests**

Load `scorecard-v2.json` explicitly and assert weights 20/15/20/15/20/10 for
reproducibility, prevention, stage evidence, numerical evaluation, scientific
evaluation, and diagnosis quality. Assert any false stack/contract/finite/
completeness/scientific hard gate forces score zero, while a missing hard gate
or dimension produces `INCOMPLETE` rather than `FAIL`.

- [ ] **Step 2: Run scorecard tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_evals -v`

Expected: FAIL because the v2 scorecard files do not exist.

- [ ] **Step 3: Add v2 card and preserve generic evaluator behavior**

Define six dimensions totaling 100 and hard gates:

```json
["stack_identity", "file_contract", "finite_output", "channel_completeness", "scientific_acceptance"]
```

Keep `score_run()` on scorecard v1 until route-specific v2 receipts are wired in
the Fisherd implementation. Package both scorecards.

- [ ] **Step 4: Run scorecard tests and confirm GREEN**

Run: `.venv/bin/python -m unittest tests.test_evals -v`

Expected: all v1 and v2 scorecard tests pass.

- [ ] **Step 5: Commit Task 5**

Commit message: `Add OML admission scorecard v2`

### Task 6: Verify, Document, and Push the Foundation

**Files:**
- Modify: `README.md`
- Modify: `skills/oh-my-librpa/SKILL.md`
- Modify: `tests/test_phase2_docs.py`

- [ ] **Step 1: Write failing documentation assertions**

Assert the README and routing skill name the v2 profile, all four admission
routes, reader v1, no symmetry-sidecar copying, and proposal-only automatic
evolution.

- [ ] **Step 2: Run documentation tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_phase2_docs -v`

Expected: FAIL because the current documentation still describes strict 2D as
globally blocked.

- [ ] **Step 3: Update concise user-facing documentation**

Describe the old production profile and new testable profile separately. State
that v2 routes remain admission-only until receipts promote them, and that the
MCP service never copies the four legacy symmetry sidecars.

- [ ] **Step 4: Run full verification**

Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
scripts/self_test.sh
.venv/bin/python -m build
```

Expected: unit suite, self-test, source distribution, and wheel build all pass.

- [ ] **Step 5: Check worktree and commit attribution**

Run `git diff --check`, inspect the complete branch diff, and verify every new
commit has author `Codex <codex@openai.com>` and committer
`AroundPeking <gonghuanjing@iphy.ac.cn>`.

- [ ] **Step 6: Commit and push**

Commit message: `Document OML v2 admission foundation`

Push branch `codex/oml-mcp-route-admission` to `origin`.
