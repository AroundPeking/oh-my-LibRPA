# Oh-My-LibRPA Controlled Execution Phase 2 Implementation Plan

**Goal:** Add a bounded, provenance-preserving control plane for one approved ABACUS periodic GW reader-v1 route, without exposing arbitrary shell, SSH, Slurm, cleanup, RPA, or FHI-aims execution through MCP.

**Architecture:** Keep the Phase 1 parsers and validators authoritative. Derive immutable plan receipts from a filtered source-input manifest, persist plans/runs/stage attempts in SQLite, materialize each run under an explicitly allowed root, and submit one generated stage script at a time through a validated execution profile. Read-only scheduler observation stays separate from parser-backed stage acceptance. A versioned scorecard reports hard gates and component scores without promoting incomplete runs to scientific validity.

**Tech Stack:** Python 3.11+, standard-library `sqlite3`, MCP Python SDK 2.x, JSON execution profiles, Slurm command adapters, `unittest`, and the existing reader-v1 validators.

## Scope

Included:

- deterministic `plan_id`, `plan_digest`, and source-input digest;
- SQLite records for immutable plans, runs, stage attempts, and observations;
- fresh local staging directories and optional bounded SSH/rsync transfer;
- fixed generated scripts for the periodic GW route stages;
- one-stage-at-a-time Slurm submission with stale-plan and duplicate-job rejection;
- read-only scheduler status and parser-backed stage inspection;
- a versioned 100-point benchmark scorecard and state-machine fault injection;
- MCP tools `prepare_run`, `submit_stage`, `get_status`, `inspect_stage`, and `score_case`.

Excluded:

- arbitrary command, shell, SSH, Slurm argument, or cleanup tools;
- automatic retries or repairs;
- RPA, molecular GW, FHI-aims, strict-2D, magnetic, or SOC execution;
- automatic numerical or scientific acceptance;
- a production HPC submission before a concrete execution profile and smoke case are approved.

## Task 1: Immutable Plans

**Files:**

- Modify: `oml_mcp/models.py`
- Modify: `oml_mcp/planner.py`
- Create: `oml_mcp/provenance.py`
- Modify: `tests/test_intake_planner.py`

1. Add failing tests proving identical inputs/options produce the same digest, a changed input changes it, and path ordering does not affect it.
2. Build a filtered execution-input manifest that includes ABACUS/LibRPA inputs, PP/NAO/ABFS assets, and approved helper scripts but excludes producer and solver outputs.
3. Return deterministic `plan_id`, `digest`, `source_digest`, and copied-input metadata from `plan_case`.
4. Keep route selection behavior unchanged.

## Task 2: Configuration And State Store

**Files:**

- Create: `oml_mcp/errors.py`
- Create: `oml_mcp/execution_profiles.py`
- Create: `oml_mcp/state.py`
- Create: `registry/execution-profiles/generic-slurm-example.json`
- Create: `tests/test_state.py`
- Create: `tests/test_execution_profiles.py`

1. Add failing tests for schema creation, immutable plan conflicts, run insertion, allowed transitions, duplicate live attempts, and stable error codes.
2. Validate execution profiles as data, never by sourcing them as shell.
3. Accept profiles only from configured roots and address them by ID, not arbitrary paths.
4. Persist timestamps in UTC and use transactions for submission authorization.

## Task 3: Fresh Run Materialization

**Files:**

- Create: `oml_mcp/materializer.py`
- Create: `oml_mcp/stage_templates.py`
- Create: `tests/test_materializer.py`

1. Add failing tests for fresh-directory creation, source immutability, escaped symlinks, stale plan digests, excluded outputs, manifest completeness, and generated script content.
2. Recompute the plan before writing and reject any stale digest.
3. Require the run directory to be a new child of an allowed root.
4. Copy only the immutable execution-input manifest and write `.oml/plan.json`, `.oml/manifest.json`, `env.sh`, and fixed stage scripts.
5. For SSH profiles, create and synchronize only the generated run directory through a bounded adapter.

## Task 4: State Policy And Bounded Submission

**Files:**

- Create: `oml_mcp/executor.py`
- Create: `oml_mcp/control.py`
- Create: `tests/test_executor.py`
- Create: `tests/test_control.py`

1. Add failing tests for first-stage authorization, prerequisite denial, stale digest denial, duplicate live-job denial, scheduler ID parsing, timeout reconciliation, and no arbitrary command parameter.
2. Submit only the generated script associated with the requested route stage.
3. Recheck plan/source/manifest digests before every submission.
4. Record a pending attempt before the external call and reconcile ambiguous submission outcomes before permitting a retry.
5. Keep local and SSH transports behind one typed adapter.

## Task 5: Status And Stage Inspection

**Files:**

- Modify: `oml_mcp/control.py`
- Create: `oml_mcp/stage_inspection.py`
- Modify: `tests/test_control.py`

1. Add failing tests that scheduler timeout returns `SCHEDULER_UNOBSERVABLE`, not failed or complete.
2. Return the latest reliable observation time and normalized scheduler state.
3. Mark a stage passed only when its fixed parser/artifact checks pass.
4. Never infer a positive state from scheduler completion alone.

## Task 6: Benchmark Scorecard

**Files:**

- Create: `benchmarks/scorecard-v1.json`
- Create: `oml_mcp/evals.py`
- Create: `tests/test_evals.py`

1. Add failing tests for 100-point weight validation, non-compensating hard gates, incomplete-run reporting, provenance completeness, and retry/duplicate penalties.
2. Report the five component scores separately from the aggregate.
3. Keep numerical/scientific validity at `NOT_EVALUATED` until dedicated gates exist.
4. Treat state-machine fault tests as frozen release gates.

## Task 7: MCP And Documentation

**Files:**

- Modify: `oml_mcp/server.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`
- Modify: `docs/guide/installation.md`
- Modify: `skills/oh-my-librpa/SKILL.md`

1. Add MCP integration tests for the five controlled-execution tools.
2. Annotate `prepare_run`, `submit_stage`, and `inspect_stage` as consequential write tools; keep `get_status` and `score_case` read-only.
3. Return structured stable errors with recovery actions.
4. Document required environment variables, execution-profile roots, default-disabled submission behavior, and current route exclusions.
5. Keep installed and repository skills synchronized after tests pass.

## Task 8: Verification And Delivery

1. Run all Python tests in the MCP environment.
2. Run `scripts/self_test.sh --workspace "$PWD"`.
3. Run the pinned upstream source-contract audit.
4. Build and install a clean wheel, then initialize the MCP server outside the repository and inspect all tool annotations.
5. Verify manifests and profiles as JSON and run `git diff --check`.
6. Verify Codex author and AroundPeking committer attribution.
7. Commit and push `codex/oml-mcp-phase2`.

Live HPC execution is a separate acceptance action after the user approves a concrete execution profile, source case, fresh remote run root, and pre-submit summary.
