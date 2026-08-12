# Oh-My-LibRPA Read-Only MCP Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an installable, read-only Codex plugin and MCP server that validates the pinned ABACUS `master_ghj`, LibRPA `v0.7.0`, and PyATB `enable_head_wing` reader-v1 workflow from source-derived contracts.

**Architecture:** Keep scientific parsing and policy in a dependency-light `oml_mcp` Python package, with the MCP SDK used only by the stdio server adapter. Store the exact upstream revisions and parameter contract in versioned JSON, return structured gate results, and leave all submission or compute actions outside this milestone.

**Tech Stack:** Python 3.11+, standard library, MCP Python SDK 2.x, JSON, `unittest`, Codex plugin manifest and stdio MCP configuration.

---

## File Structure

- `pyproject.toml`: package metadata, Python requirement, MCP dependency, console entry point.
- `.codex-plugin/plugin.json`: Codex plugin metadata and discovery paths.
- `.mcp.json`: stdio server declaration using the repository-local launcher.
- `bin/oh-my-librpa-mcp`: stable launcher that resolves the plugin root and project environment.
- `oml_mcp/models.py`: structured gate, intake, plan, and artifact result types.
- `oml_mcp/parsers.py`: ABACUS/LibRPA key-value and small metadata parsers.
- `oml_mcp/profiles.py`: load and validate the pinned compatibility profile.
- `oml_mcp/artifacts.py`: reader-v1 eigenvector, velocity, `k_path_info`, and `stru_out` inspection.
- `oml_mcp/intake.py`: case discovery, classification, and input fingerprints.
- `oml_mcp/planner.py`: deterministic route selection for the initial ABACUS GW/RPA lanes.
- `oml_mcp/validators.py`: source-version, parameter, symmetry, shrink, and head/wing gates.
- `oml_mcp/server.py`: read-only MCP tool registration and stdio entry point.
- `profiles/abacus-librpa-pyatb-2026-08.json`: exact SHAs, canonical parameters, filenames, markers, and policy.
- `scripts/audit_upstream_contract.py`: verify local upstream checkouts and print a reproducible contract audit.
- `scripts/install_codex_plugin.sh`: create the plugin environment and install the repository package.
- `tests/fixtures/`: minimal valid and faulty ABACUS/LibRPA/PyATB cases.
- `tests/test_*.py`: unit and MCP integration tests.
- `docs/upstream-parameter-audit-2026-08-12.md`: human-readable source evidence and corrected old assumptions.

### Task 1: Freeze The Source-Derived Compatibility Contract

**Files:**
- Create: `profiles/abacus-librpa-pyatb-2026-08.json`
- Create: `scripts/audit_upstream_contract.py`
- Create: `tests/test_profiles.py`
- Create: `docs/upstream-parameter-audit-2026-08-12.md`

- [ ] **Step 1: Write failing profile tests**

Test exact component SHAs, ABACUS `out_librpa_reader_version = 1`, LibRPA canonical reader-v1 names, canonical symmetry keys, deprecated `g0w0_band`, and the two PyATB binary markers. The test must reject the obsolete `use_input_exx_symmetry` and `use_input_gw_symmetry` spellings as canonical keys.

- [ ] **Step 2: Run the profile tests and confirm the profile loader is missing**

Run: `python -m unittest tests.test_profiles -v`

Expected: FAIL because `oml_mcp.profiles` and the profile JSON do not exist.

- [ ] **Step 3: Add the profile and audit script**

The profile must contain these fixed revisions:

```json
{
  "abacus": "3efad9ed5ca066aee1d1b2214e43f92a2d2a567e",
  "librpa": "dd169fa11fa920d580d4f39dc11e218a7f17f7b5",
  "pyatb": "9fb9028c59b1dbaf9cf66965280961fc2225d9eb"
}
```

The audit script accepts `--abacus`, `--librpa`, and `--pyatb` checkout paths, verifies `HEAD`, and searches the pinned source for the registered parameter names and reader markers. It exits nonzero on a SHA or source-contract mismatch.

- [ ] **Step 4: Document the verified corrections**

Record that:

- ABACUS defaults `out_librpa_reader_version` to `0`, supports only `0/1`, and OML must write `1`.
- LibRPA defaults `version_coul_reader` and `version_lri_reader` to `-1`, but OML production input must write `1`.
- LibRPA 0.7.0 parses `use_symmetry_exx`, `use_symmetry_gw`, and `use_symmetry_rpa`; the old OML `use_input_*_symmetry` keys are not parser aliases.
- `g0w0_band` remains accepted but is documented as a deprecated alias of `g0w0`.
- PyATB supplies the velocity calculation; OML's adapter writes the LibRPA binary payloads.
- `stru_out` contains `n_symops row` followed by 9 integer rotation entries and 3 translations per operation.

- [ ] **Step 5: Run tests and the live source audit**

Run:

```bash
python -m unittest tests.test_profiles -v
python scripts/audit_upstream_contract.py \
  --abacus /private/tmp/oml-upstreams-20260812.3MQ9LU/abacus \
  --librpa /private/tmp/oml-upstreams-20260812.3MQ9LU/librpa-sparse \
  --pyatb /private/tmp/oml-upstreams-20260812.3MQ9LU/pyatb
```

Expected: tests pass and the audit reports all three revisions and all contract checks as accepted.

- [ ] **Step 6: Commit**

Commit message: `Add pinned upstream parameter contract`

### Task 2: Add Input Parsers And Structured Gate Results

**Files:**
- Create: `oml_mcp/__init__.py`
- Create: `oml_mcp/models.py`
- Create: `oml_mcp/parsers.py`
- Create: `tests/test_parsers.py`

- [ ] **Step 1: Write failing parser tests**

Cover ABACUS whitespace syntax, LibRPA `key = value`, inline `#` comments, boolean normalization, duplicate keys, numeric values, missing files, `k_path_info` headers, and the first three `band_out` dimensions.

- [ ] **Step 2: Confirm RED**

Run: `python -m unittest tests.test_parsers -v`

Expected: FAIL because the parser module is absent.

- [ ] **Step 3: Implement minimal parsers and models**

Use immutable dataclasses for `GateResult`, `ValidationReport`, `InputDocument`, `ArtifactInfo`, `IntakeReport`, and `CasePlan`. Gate statuses are exactly `PASS`, `WARN`, `FAIL`, or `SKIP`; each non-pass gate includes evidence and a repair action.

- [ ] **Step 4: Confirm GREEN**

Run: `python -m unittest tests.test_parsers -v`

Expected: all parser tests pass.

- [ ] **Step 5: Commit**

Commit message: `Add deterministic workflow input parsers`

### Task 3: Validate Reader-v1 And Symmetry Artifacts

**Files:**
- Create: `oml_mcp/artifacts.py`
- Create: `tests/test_artifacts.py`
- Create: `tests/fixtures/reader_v1/`

- [ ] **Step 1: Write failing artifact tests**

Generate small fixture files in tests and cover:

- eigenvector marker `-12345679`, kind `28`, positive dimensions, block-table bounds, unique 1-based k indices, and complete payload length;
- velocity marker `-12345680`, kind `29`, `nalpha = 3`, block-table bounds, unique k indices, and complete payload length;
- cross-file dimension agreement with `k_path_info` and `band_out`;
- `stru_out` with no symmetry tail, a valid `row` tail, truncated operations, invalid rotation integers, and trailing tokens;
- explicit rejection of legacy symmetry sidecar requirements.

- [ ] **Step 2: Confirm RED**

Run: `python -m unittest tests.test_artifacts -v`

Expected: FAIL because artifact inspectors are absent.

- [ ] **Step 3: Implement header and small-metadata inspection**

Read only headers, block tables, file sizes, and small text metadata. Do not load matrix payloads into memory. Return dimensions, k-index coverage, format version, and precise failure evidence.

- [ ] **Step 4: Confirm GREEN**

Run: `python -m unittest tests.test_artifacts -v`

Expected: all artifact tests pass.

- [ ] **Step 5: Commit**

Commit message: `Validate LibRPA reader-v1 artifacts`

### Task 4: Implement Intake And Deterministic Route Planning

**Files:**
- Create: `oml_mcp/intake.py`
- Create: `oml_mcp/planner.py`
- Create: `tests/test_intake_planner.py`
- Create: `tests/fixtures/cases/valid_periodic_gw/`

- [ ] **Step 1: Write failing intake and planner tests**

Cover ABACUS ownership markers, mixed ABACUS/FHI-aims rejection, immutable SHA-256 fingerprints, reader-v1 artifact classification, molecular GW short route, periodic GW PyATB route, RPA route, symmetry route, and SOC forcing the no-symmetry lane.

- [ ] **Step 2: Confirm RED**

Run: `python -m unittest tests.test_intake_planner -v`

Expected: FAIL because intake and planner modules are absent.

- [ ] **Step 3: Implement intake and planning**

The initial stage graphs are:

```text
molecular_gw: scf -> librpa
periodic_gw: scf -> pyatb -> nscf -> preprocess -> librpa
periodic_gw_symmetry: scf_symmetry -> pyatb_full_grid -> nscf_full_grid -> preprocess -> librpa
rpa: scf -> librpa
```

Planning never edits files and never infers FHI-aims ownership from weak shared filenames.

- [ ] **Step 4: Confirm GREEN**

Run: `python -m unittest tests.test_intake_planner -v`

Expected: all intake and planner tests pass.

- [ ] **Step 5: Commit**

Commit message: `Add read-only case intake and planning`

### Task 5: Enforce The Pinned Workflow Policy

**Files:**
- Create: `oml_mcp/validators.py`
- Create: `tests/test_validators.py`
- Modify: `tests/fixtures/cases/valid_periodic_gw/`

- [ ] **Step 1: Write failing validator tests**

Cover these gates:

- explicit ABACUS `rpa = 1`, `basis_type = lcao`, and `out_librpa_reader_version = 1`;
- explicit LibRPA reader versions, v1 prefixes, split basis names, and non-overlapping full/shrink prefixes;
- unknown `use_input_*_symmetry` as `FAIL` with canonical replacement;
- deprecated `task = g0w0_band` as `WARN` with `task = g0w0` replacement;
- ABACUS `symmetry = 1` aligned to LibRPA `use_symmetry_exx/gw = t`;
- SOC aligned to ABACUS `symmetry = -1` and LibRPA symmetry switches off;
- producer shrink aligned to `use_shrink_abfs` and shrink artifacts;
- head/wing requiring a valid PyATB full-grid directory and binary-v1 headers;
- mixed legacy/v1 file families rejected;
- absence of legacy symmetry sidecars does not fail.

- [ ] **Step 2: Confirm RED**

Run: `python -m unittest tests.test_validators -v`

Expected: FAIL because policy validators are absent.

- [ ] **Step 3: Implement policy validation**

Return every gate, not only the first error. `ValidationReport.accepted` is true only when no gate has status `FAIL`. Warnings do not permit silent rewriting; they carry a proposed replacement.

- [ ] **Step 4: Confirm GREEN**

Run: `python -m unittest tests.test_validators -v`

Expected: all validator tests pass.

- [ ] **Step 5: Commit**

Commit message: `Enforce ABACUS LibRPA v1 workflow policy`

### Task 6: Expose The Read-Only MCP Tools

**Files:**
- Create: `oml_mcp/server.py`
- Create: `tests/test_server.py`
- Create: `pyproject.toml`
- Create: `.codex-plugin/plugin.json`
- Create: `.mcp.json`
- Create: `bin/oh-my-librpa-mcp`
- Create: `scripts/install_codex_plugin.sh`

- [ ] **Step 1: Write failing server tests**

Test tool registration and structured calls for `inspect_profile`, `ingest_case`, `plan_case`, `validate_case`, and `inspect_reader_v1`. Assert that no submission, shell, SSH, cleanup, or arbitrary-command tool is exposed.

- [ ] **Step 2: Confirm RED**

Run: `python -m unittest tests.test_server -v`

Expected: FAIL because the MCP adapter is absent.

- [ ] **Step 3: Add package and plugin metadata**

Use `mcp>=2.0,<3`, an `oh-my-librpa-mcp` console script, a plugin-relative stdio launcher, and a plugin manifest that points to `./skills/` and `./.mcp.json`.

- [ ] **Step 4: Implement MCP tool adapters**

Each tool accepts typed paths/options, resolves paths without mutation, and returns JSON-compatible dictionaries. The server runs with stdio and writes no diagnostic text to stdout.

- [ ] **Step 5: Install in a temporary environment and run protocol tests**

Run:

```bash
python -m pip install -e .
python -m unittest tests.test_server -v
```

Expected: the MCP client initializes, lists exactly the five read-only tools, and calls each tool successfully.

- [ ] **Step 6: Commit**

Commit message: `Add read-only Oh-My-LibRPA MCP server`

### Task 7: Align Existing OML Defaults With LibRPA 0.7.0

**Files:**
- Modify: `templates/abacus-librpa-gw/**/*.template`
- Modify: `templates/abacus-librpa-gw/template/librpa.in`
- Modify: `scripts/check_consistency.sh`
- Modify: `scripts/self_test.sh`
- Modify: `skills/oh-my-librpa/**`
- Modify: `skills/abacus-librpa-gw/SKILL.md`
- Modify: `rules/cards/*.yml`
- Modify: `tests/`

- [ ] **Step 1: Write regression tests for current 0.7.0 spellings**

Tests must first fail while templates still contain `task = g0w0_band` and `use_input_*_symmetry`.

- [ ] **Step 2: Replace obsolete defaults**

Generate `task = g0w0`, `use_symmetry_exx`, `use_symmetry_gw`, and `use_symmetry_rpa` where applicable. Keep source-backed compatibility notes explaining that `g0w0_band` is accepted only as a deprecated alias. Do not introduce or copy legacy symmetry sidecars.

- [ ] **Step 3: Synchronize the repository skill copy**

Apply the same wording and template changes under `skills/oh-my-librpa/`. The installed `~/.codex/skills/oh-my-librpa` copy is updated only after the branch passes all tests.

- [ ] **Step 4: Run all legacy and new tests**

Run:

```bash
python -m unittest discover -s tests -v
bash scripts/self_test.sh --workspace "$PWD"
```

Expected: all Python tests pass and the shell self-test has zero failures.

- [ ] **Step 5: Commit**

Commit message: `Align OML defaults with LibRPA 0.7.0`

### Task 8: Final Verification And Handoff

**Files:**
- Modify: `README.md`
- Modify: `docs/guide/installation.md`
- Modify: `skills/oh-my-librpa/SKILL.md`

- [ ] **Step 1: Document MCP installation and current read-only scope**

Explain setup, the five tools, the pinned profile, how to refresh the source audit, and that task submission remains on the existing scripts until Phase 2.

- [ ] **Step 2: Validate manifests and package metadata**

Parse `.codex-plugin/plugin.json`, `.mcp.json`, and the profile as JSON; install the package in a clean temporary virtual environment; initialize the MCP server; list and call tools.

- [ ] **Step 3: Run the complete verification suite**

Run:

```bash
python -m unittest discover -s tests -v
bash scripts/self_test.sh --workspace "$PWD"
python scripts/audit_upstream_contract.py \
  --abacus /private/tmp/oml-upstreams-20260812.3MQ9LU/abacus \
  --librpa /private/tmp/oml-upstreams-20260812.3MQ9LU/librpa-sparse \
  --pyatb /private/tmp/oml-upstreams-20260812.3MQ9LU/pyatb
git diff --check
```

Expected: zero failures, source audit accepted, and no whitespace errors.

- [ ] **Step 4: Review diff and attribution**

Confirm only planned files changed. Verify each commit has `Codex <codex@openai.com>` as author and `AroundPeking <gonghuanjing@iphy.ac.cn>` as committer.

- [ ] **Step 5: Sync installed skill after verification**

Mirror the tested `skills/oh-my-librpa/` tree to `~/.codex/skills/oh-my-librpa/`, then run its self-test. Do not install the plugin into a marketplace or push the branch until the user reviews the Phase 1 result.
