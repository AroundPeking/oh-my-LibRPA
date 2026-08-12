# Controlled Execution

OML 0.2 adds bounded MCP execution for one route: **non-SOC periodic GW** with ABACUS reader-v1, PyATB head/wing, and LibRPA 0.7.0. It does not expose arbitrary shell, SSH, Slurm options, cleanup, repair, or retry commands.

## Scope

The fixed order is:

```text
scf -> pyatb -> nscf -> preprocess -> librpa
```

RPA, atomic or molecular GW, strict 2D, magnetic or SOC calculations, FHI-aims, and Delta-Sternheimer are not executable through these MCP write tools yet. They retain their existing reviewed workflows.

Symmetry operations are read from `stru_out`. Legacy symmetry sidecars such as `irreducible_sector.txt` and `symrot_*.txt` are not copied or required; LibRPA reconstructs rotations from `stru_out`.

## Execution Profiles

Execution profiles are administrator-managed JSON files addressed by ID. OML searches the roots listed in `OML_EXECUTION_PROFILE_ROOTS` (separated by the operating system path separator), followed by the packaged example registry. The packaged `generic-slurm-example` is disabled and contains placeholders; copy it into a private profile root, replace every value, review it, and set `enabled` to `true`.

Required sections include:

- allowed source and fresh-run roots plus the SQLite state path;
- Slurm `submit_program`, `status_program`, and historical `history_program`;
- fixed resources and runtime executable paths;
- `sources` with `git_program` and absolute ABACUS, LibRPA, and PyATB source directories;
- optional fixed `environment` values such as `PATH`, `LD_LIBRARY_PATH`, and `PYTHONPATH`;
- for SSH, a registered host, bounded remote run root, and fixed SSH/rsync programs.

`mpi_ranks` must equal `nodes * ntasks_per_node`; `omp_threads` must equal `cpus_per_task`; PyATB ranks cannot exceed the allocation. Environment names and values are validated, shell-quoted, and included in the execution-profile digest. Do not store passwords, OTPs, tokens, private keys, or other secrets in a profile; secret-like field names are rejected.

At preparation and before every submission, OML checks the pinned source SHAs and hashes the configured ABACUS and LibRPA binaries. It also requires `perform.sh`, `get_diel.py`, `output_librpa.py`, and `preprocess_abacus_for_librpa_band.py` to match the approved hashes in the compatibility profile. A changed source, helper, profile, binary, local manifest, or remote run bundle blocks submission. Remote bundle integrity is checked again before stage inspection.

## MCP Sequence

1. Use `inspect_profile`, `ingest_case`, `plan_case`, and input-stage `validate_case`.
2. Review the immutable plan digest and call `prepare_run(source_path, plan_digest, execution_profile_id)`.
3. Call `submit_stage` for exactly one stage. It transactionally rejects stale plans, wrong order, passed stages, and equivalent active or unobservable jobs.
4. Call read-only `get_status`. It observes `squeue` and falls back to `sacct`; it does not mark scientific success or change SQLite state.
5. When the scheduler reports completion, call `inspect_stage`. It records the observation, creates a bounded remote snapshot where needed, applies fixed artifact gates, and writes an immutable PASS/FAIL receipt.
6. Repeat in order. Before `librpa`, OML runs the complete `pre_librpa` cross-dataset validation.
7. Call `score_case` at any point to inspect hard gates, component scores, retries, and remaining work.

If `sbatch` times out after a submission may have reached Slurm, the attempt remains `UNKNOWN`. A later explicit `submit_stage` call queries both `squeue` and `sacct` using the unique full `run_id + stage` job name. One matching job is attached to the original attempt and multiple matches remain blocked. Absence is accepted only after two complete `squeue+sacct` observations at least five minutes apart. The attempt then becomes `FAILED`, but OML still preserves that run directory: a retry requires a new `prepare_run` receipt and fresh run directory.

OML 0.2 never reruns a terminal stage in the same run directory. Failed logs and artifacts remain available for diagnosis; no controlled retry cleans or silently reuses them.

An interrupted controller process can leave an attempt in `SUBMITTING`. After the process lock is released, the same bounded reconciliation loop moves it to `UNKNOWN`, attaches a discovered scheduler ID, or eventually establishes separated absence evidence. It never submits a second job during reconciliation.

`submit_stage` accepts only `scf`, `pyatb`, `nscf`, `preprocess`, or `librpa`. No MCP tool accepts command text, scheduler arguments, remote paths, deletion targets, or retry counts.

## Receipts

Each new run contains:

- `.oml/plan.json`: route, options, source manifest, and reviewed digest;
- `.oml/execution.json`: normalized execution profile, its digest, pinned source evidence, and binary fingerprints;
- `.oml/manifest.json`: hashes of copied inputs, runtime environment, execution receipt, and generated stage scripts;
- `.oml/stages/*.slurm`: fixed stage scripts;
- SQLite records for runs, attempts, scheduler observations, preflight evidence, and immutable stage inspections.

When `INPUT_scf`/`INPUT_nscf` or `KPT_scf`/`KPT_nscf` exist, stale generic `INPUT` and `KPT` work copies are excluded from the source manifest. Producer outputs and old run data are never copied into a fresh run.

The fixed executor requires explicit `input_dir = .`, because ABACUS, PyATB, preprocessing, and LibRPA all produce or consume the same run root. Controlled `pseudo_dir` and `orbital_dir` values must stay inside that immutable run bundle. PP, NAO, and ABFS paths referenced by `STRU` must be regular in-bundle files; absolute paths, parent traversal, links, and missing assets are rejected.

## Scorecard

`score_case` uses `benchmarks/scorecard-v1.json`, with 100 points across pre-compute validation, stage state, diagnosis, numerical/scientific validity, and efficiency/reproducibility. Hard gates are non-compensating: provenance damage, version mismatch, invalid lineage, duplicate active work, unresolved failure, or non-finite final output makes the run ineligible regardless of raw points.

Diagnosis and numerical/scientific validity remain `NOT_EVALUATED` until dedicated evidence exists. A successful scheduler exit or `LIBRPA_PASSED` is not a convergence or scientific-validity claim. Frozen replays under `benchmarks/replays/` protect these semantics during harness evolution.

## Live Acceptance

The default example profile is disabled, so installation alone cannot submit. The first live HPC smoke requires separate approval of the concrete profile, source case, local/remote fresh-run roots, and pre-submit summary. No live job is part of the software test suite.

Run software regression tests with `.venv/bin/python -m unittest discover -s tests -p 'test_*.py'`. Using an unrelated system Python may report missing optional test dependencies rather than a code regression.
