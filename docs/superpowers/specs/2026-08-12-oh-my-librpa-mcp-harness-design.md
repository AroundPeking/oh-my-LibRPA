# Oh-My-LibRPA MCP Harness Design

Date: 2026-08-12
Status: approved architecture, implementation pending

## 1. Purpose

Oh-My-LibRPA (OML) will be refactored from a collection of large, partially overlapping Codex skills and shell helpers into a plugin centered on a deterministic MCP service.

The long-term goal is to prepare, execute, validate, diagnose, and compare hundreds of ABACUS + LibRPA GW calculations for material families including perovskites, two-dimensional materials, altermagnets, and transition-metal oxides.

The system must optimize for the following outcomes, in this order:

1. Detect known invalid configurations before consuming compute resources.
2. Preserve enough provenance to reproduce every submitted stage.
3. Prevent a later workflow stage from running before its prerequisites pass.
4. Localize failures to a small, evidence-backed category and propose the cheapest discriminating test.
5. Distinguish program completion, numerical validity, convergence, and physical conclusions.
6. Learn from reviewed failures without allowing one production case to silently change production policy.

OML is not intended to replace ABACUS, PyATB, LibRPA, Slurm, or the AI agent. It is the policy, validation, execution, and evidence layer between the agent and those systems.

## 2. Confirmed Software Baseline

The initial compatibility profile is pinned to exact source revisions, even when a human-facing branch or release name is also recorded.

| Component | Human-facing baseline | Pinned revision on 2026-08-12 | Role |
| --- | --- | --- | --- |
| ABACUS | `AroundPeking/abacus-develop:master_ghj` | `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e` | SCF, NSCF, LRI/Coulomb producer |
| LibRPA | `Srlive1201/LibRPA:v0.7.0` | `dd169fa11fa920d580d4f39dc11e218a7f17f7b5` | GW/RPA consumer and solver |
| PyATB | `AroundPeking/pyatb:enable_head_wing` | `9fb9028c59b1dbaf9cf66965280961fc2225d9eb` | full-grid eigenvectors and head/wing velocity data |

The branch names are update channels, not reproducibility identifiers. Every run records exact revisions and executable fingerprints.

The compatibility profile also records:

- LibRI and LibComm revisions used by both ABACUS and LibRPA;
- compiler, MPI, MKL/BLAS, ELPA, and CMake versions;
- build options and executable paths;
- server and partition profile;
- pseudopotential, NAO, and ABFS asset hashes;
- OML plugin, MCP server, rule-set, and schema versions.

A run is compatible only when its complete profile matches an approved compatibility entry. A branch tip moving after validation does not update an existing entry automatically.

### 2.1 Intermediate data format

Reader v1 is the production default. OML must set it explicitly because the current ABACUS source default for `out_librpa_reader_version` is still legacy.

The v1 contract includes, as applicable:

- ABACUS: `out_librpa_reader_version 1`;
- `stru_out` from the same producer calculation, including atom types and symmetry operations when spatial symmetry is used;
- `bz_sampling_out` as the authoritative Brillouin-zone sampling file;
- `basis_wfc_out` and `basis_aux_out`;
- `basis_aux_shrink_out` when shrink is enabled;
- `v1_coulomb_full_iq_*` and `v1_coulomb_cut_iq_*`;
- `v1_Cs_data_*` and, when applicable, `v1_Cs_shrinked_data_*`;
- `v1_shrink_sinvS_*` when shrink is enabled;
- `version_coul_reader = 1` and `version_lri_reader = 1` in LibRPA;
- PyATB full-grid data accepted by the pinned LibRPA build, including the binary-v1 eigenvector and velocity payloads used by the head/wing path.

Legacy symmetry sidecars such as `irreducible_sector.txt`, `symrot_R.txt`,
`symrot_k.txt`, and `symrot_abf_k.txt` are neither copied nor required.
LibRPA reconstructs the symmetry rotations from `stru_out`.

Legacy remains available only through an explicit compatibility or diagnostic profile. OML must never silently mix legacy and v1 files, auto-promote an old dataset, or discover both formats under overlapping prefixes.

The first implementation phase must turn the PyATB output assumptions above into byte-level fixture tests. The pinned branch is accepted as the initial source baseline, but the files it produces are the executable contract.

## 3. Architectural Decision

The selected architecture is a hybrid OML plugin:

```text
OML plugin
|-- minimal routing skill
|-- local MCP service
|-- optional enforcement hooks
|-- schemas and compatibility profiles
|-- validators and diagnostic rules
`-- benchmark/evaluation harness
```

### 3.1 Why not pure skills

The current skills encode valuable experience, but they mix intent routing, software-version rules, command construction, validation, diagnosis, and reporting. Rules are duplicated between installed and repository copies, and compliance depends too much on whether the model loads and follows the correct text.

Skills will be retained only for concise user-facing intent routing, supported scope, and instructions to use the OML tools. Detailed workflow policy moves to executable server code and versioned data.

### 3.2 Why not pure MCP

MCP tools expose deterministic actions but do not by themselves explain the scientific workflow or guarantee that the model selects a tool. A small skill still improves discovery and user interaction. Enforcement comes from server-side state checks and, where supported, hooks that block bypass commands.

### 3.3 Enforcement boundary

Strict compliance is guaranteed only inside the following boundary:

- OML is the only component allowed to submit the managed run directory, or
- the host enables an OML hook that rejects direct managed-run invocations of `sbatch`, ABACUS, PyATB, and LibRPA.

If an unrestricted agent retains an unguarded SSH or shell path, no MCP design can provide an absolute guarantee that it will not bypass MCP. OML will still detect unregistered artifacts, but that is audit rather than prevention.

## 4. Runtime Shape

The first implementation uses a local Python 3.11+ MCP server distributed with the plugin and connected over stdio. This keeps the initial system private, reuses the user's existing SSH configuration, and avoids introducing a network service before the workflow is stable.

The MCP server owns:

- structured input parsing;
- compatibility resolution;
- deterministic run planning;
- state transitions and gate evaluation;
- server profile and Slurm script materialization;
- SSH/Slurm execution through bounded adapters;
- output parsing and failure classification;
- provenance, reports, and benchmark records.

Large logs, matrices, and scientific artifacts remain on disk or on the compute server. Tool responses return concise structured summaries, stable identifiers, hashes, relevant excerpts, and artifact paths. This prevents complete logs and long workflow instructions from consuming model context.

Persistent metadata is stored in SQLite. Calculation artifacts remain in immutable filesystem run directories. SQLite transactions protect state transitions and duplicate-submission checks; the filesystem remains the source of truth for scientific artifacts.

## 5. Core Components

### 5.1 Tool API

The initial tool surface is intentionally focused:

| Tool | Effect | Main output |
| --- | --- | --- |
| `create_case` | create local OML metadata | `case_id` |
| `ingest_case` | classify and fingerprint source files without modifying them | intake manifest |
| `plan_case` | choose route, required stages, compatibility profile, and estimated resources | immutable `plan_id` and digest |
| `validate_case` | execute static and compatibility gates | structured gate report |
| `prepare_run` | create a fresh run directory and materialize reviewed inputs/scripts | `run_id` and manifest |
| `submit_stage` | submit exactly one allowed stage after rechecking its prerequisites | stage attempt and scheduler ID |
| `get_status` | read scheduler and stage state without changing it | normalized state and observation time |
| `inspect_stage` | parse logs and artifacts for one stage | evidence and gate results |
| `diagnose_case` | rank root-cause categories and select the cheapest discriminating test | diagnosis record |
| `finalize_case` | run numerical and scientific acceptance checks | final validity verdict |
| `score_case` | evaluate a run or replay against the harness | hard gates and score breakdown |

Read and write tools stay separate. Tools do not accept arbitrary shell commands. The server selects commands from versioned stage templates and accepts only typed scientific/runtime parameters.

`submit_stage` must receive the current `run_id`, stage name, and plan digest. The server recalculates the digest, reruns mandatory cheap gates, checks for an equivalent live job, and rejects stale or duplicate submissions.

### 5.2 Domain services

The server is divided into independently testable modules:

- `profiles`: approved software and server compatibility profiles;
- `intake`: ABACUS/PyATB/LibRPA file classification and fingerprints;
- `planner`: route graph and required stage selection;
- `policy`: invariants and state-transition authorization;
- `materializer`: fresh directories, inputs, and Slurm scripts;
- `executor`: bounded local, SSH, and Slurm operations;
- `parsers`: ABACUS, PyATB, LibRPA, Slurm, and postprocessing outputs;
- `validators`: static, artifact, numerical, and scientific gates;
- `diagnostics`: evidence-backed root-cause ranking and discriminating tests;
- `provenance`: manifests, observations, and immutable receipts;
- `evals`: fixture replay, fault injection, scoring, and regression comparison.

No parser changes scheduler state. No diagnostic rule submits a job. No executor decides scientific validity. These ownership boundaries keep failure behavior inspectable.

## 6. Data Model

The persistent model contains the following primary records:

- `Campaign`: a collection of related cases and shared policy/budget;
- `Case`: a material, scientific intent, source bundle, and route classification;
- `Plan`: immutable stage graph, parameters, compatibility profile, and resource estimate;
- `Run`: one fresh realization of a plan;
- `StageAttempt`: one submission or local execution of one stage;
- `Artifact`: path, size, checksum, producer stage, and format metadata;
- `GateResult`: validator version, status, measurements, threshold, and evidence;
- `Diagnosis`: symptom, ranked causes, evidence, confidence, and proposed test;
- `Observation`: scheduler/log state with timestamp and source;
- `BenchmarkResult`: fixture version, rule-set version, metrics, and verdict.

Input source directories are never run directories. OML records their fingerprints but does not overwrite them.

Every artifact consumed by a downstream stage must point to one successful upstream `StageAttempt`. A file merely existing is insufficient provenance.

## 7. Workflow State Machine

The case workflow uses explicit positive states:

```text
DRAFT
  -> STACK_PINNED
  -> INPUT_VALIDATED
  -> RUN_PREPARED
  -> SMOKE_PASSED
  -> SCF_PASSED
  -> PRODUCER_PASSED
  -> PYATB_PASSED
  -> NSCF_PASSED
  -> PREPROCESS_PASSED
  -> LIBRPA_PASSED
  -> NUMERICALLY_VALID
  -> SCIENTIFICALLY_VALID
```

`FAILED`, `BLOCKED`, `RUNNING`, `PENDING`, and `UNKNOWN` are attempt or observation statuses, not evidence that a positive workflow state has been reached.

A positive state is monotonic for one immutable run. Repairing an input after failure creates a new plan revision or stage attempt; it does not rewrite the historical receipt.

### 7.1 Route graphs

The state machine is a route graph rather than one universal linear script:

- molecular GW may skip PyATB, NSCF band-path, and periodic preprocessing when the approved profile says they are unnecessary;
- periodic GW with head/wing requires full-grid PyATB output;
- periodic symmetry requires the symmetry-enabled producer `stru_out`, while the later NSCF path follows the approved symmetry policy;
- SOC disables the periodic spatial-symmetry lane until a separate compatible route is validated;
- strict 2D adds Coulomb metadata, area, vacuum, q-grid, head/wing, and postprocessing gates;
- RPA and FHI-aims routes remain outside the first MCP execution milestone and continue as existing workflows until separately specified.

Skipped stages are explicit `NOT_REQUIRED` route decisions, never inferred from missing files.

## 8. Mandatory Gates

### 8.1 Stack and build gate

Before submission or result interpretation, OML verifies:

- exact source SHAs or approved release IDs;
- executable path, file metadata, and build fingerprint;
- ABACUS and LibRPA dependency compatibility;
- PyATB branch/SHA and Python/runtime environment;
- MPI, compiler, MKL/BLAS, ELPA, and server profile;
- OML compatibility profile and rule-set version.

Unknown versions are rejected unless the user explicitly creates a named experimental profile. Experimental results cannot update production references.

### 8.2 Input-contract gate

The gate checks at least:

- one upstream stack owns the case;
- structure, species order, atom types, units, and lattice are consistent;
- PP, NAO, ABFS, and element coverage match;
- spin, magnetism, noncollinearity, SOC, occupations, and electron counts align;
- k-grid, q-grid, path-grid, and full-grid/IBZ conventions align;
- symmetry settings are compatible and `stru_out` belongs to the producer stage;
- shrink settings and full/shrink basis families align;
- reader v1 files and prefixes are complete and non-overlapping;
- deprecated or ignored ABACUS/LibRPA keywords are rejected;
- fresh run location and compute profile are valid.

### 8.3 Stage gates

Each stage has parser-backed success criteria. Literal log strings can support a result but cannot be the only evidence when structured outputs are available.

Examples:

- SCF: process completion, convergence marker, final `drho`, occupations, Fermi level/gap, magnetic moments, and required restart/output artifacts;
- producer: nonempty v1 file families, counts and dimensions, basis consistency, finite values, and provenance from the accepted SCF;
- PyATB: expected full-grid count, eigenvector dimensions, velocity tensor dimensions, finite values, Hermiticity checks where applicable, and accepted binary format markers;
- NSCF/preprocess: band/path counts, spin layout, index mappings, and required files;
- LibRPA: completion plus finite core outputs, expected q/frequency/state coverage, no reader fallback to an unintended format, and no unresolved rank-specific failure;
- postprocessing: valid continuation/root-finding, no NaN/Inf, valid band identity, and consistent energy units/reference.

A shell script returning zero is not sufficient to pass a stage. Conversely, a brittle optional `grep` failing after all authoritative artifacts pass must not invalidate the producer or trigger an expensive rerun.

### 8.4 Numerical validity gate

Numerical validity is separate from program completion. It includes applicable checks for:

- NaN/Inf and malformed complex data;
- Hermiticity, dimensions, normalization, and sum rules;
- q-star/full-grid reconstruction consistency;
- head/wing/body and q-resolved self-energy consistency;
- analytic-continuation validity and quasiparticle root selection;
- fixed-protocol MPI/rank reproducibility;
- convergence of Ecut/FFT grid, k/q mesh, empty bands, frequency grid, ABFS/shrink, and vacuum for 2D systems.

### 8.5 Scientific validity gate

Scientific validity records a measured value, an acceptance threshold, and the remaining decision. It cannot be inferred from a completed pipeline.

Examples include:

- correct insulating/metallic/magnetic classification;
- plausible and continuous near-gap band identity;
- separate convergence of component energies before a cancellation-based derived quantity;
- material-family-specific references or controlled internal limits;
- final GW gap/band changes under the required convergence variables;
- explicit labeling of exploratory, diagnostic, converged, and publication-ready results.

## 9. Diagnosis Model

The first diagnostic taxonomy is intentionally small and operational:

1. `version_or_build_mismatch`
2. `dataset_format_or_provenance`
3. `structure_kgrid_symmetry_spin_soc`
4. `pp_nao_abfs_shrink_or_empty_bands`
5. `scf_occupations_or_magnetism`
6. `pyatb_headwing_or_mapping`
7. `resource_mpi_libcomm_scalapack`
8. `coulomb_chi0_epsilon_wc_sigma_or_continuation`
9. `not_numerically_converged`
10. `completed_but_not_scientifically_valid`

`diagnose_case` returns:

- normalized symptom;
- current observation time and evidence sources;
- ranked root-cause categories;
- evidence for and against each leading cause;
- confidence calibrated from benchmark history;
- the cheapest discriminating test;
- whether reuse of existing artifacts is safe;
- whether resubmission is allowed, blocked, or unnecessary.

The diagnostic engine does not claim a root cause from one stalled job, one screenshot, one log phrase, or one visually normal band plot. It favors controlled comparisons that hold code, inputs, provider, rank/OpenMP layout, and stopping criteria fixed.

## 10. Benchmark and Evaluation Harness

The harness is a first-class part of OML, not a later reporting feature.

### 10.1 Benchmark layers

The benchmark suite has four layers:

1. **Contract fixtures**: small valid and invalid input bundles for parsers, schemas, v1/legacy detection, symmetry, spin, shrink, and PyATB format checks.
2. **Failure replays**: frozen logs and manifests representing known SCF, parser, scheduler, MPI, PyATB, LibRPA, NaN, continuation, and convergence failures.
3. **Executable smoke cases**: small end-to-end cases that test the actual pinned binaries and handoff formats.
4. **Scientific reference cases**: controlled systems with accepted numerical quantities, convergence protocols, tolerances, and provenance.

Synthetic fault injection is used for deterministic coverage: missing file, altered SHA, wrong atom count, overlapping v1 prefixes, spin mismatch, stale `stru_out`, wrong k count, truncated binary, NaN, scheduler dependency failure, false-negative log wording, and duplicate submission.

### 10.2 Initial material matrix

The benchmark grows by route difficulty rather than immediately mirroring the final hundreds-material campaign:

| Class | Initial purpose |
| --- | --- |
| molecule such as H2 | shortest ABACUS-reader-v1-LibRPA handoff |
| Si | nonmagnetic 3D periodic smoke and convergence |
| BN regression case | reader-v1, shrink, symmetry, PyATB head/wing handoff |
| MoS2 or phosphorene | strict-2D, vacuum, k-grid, and final GW checks |
| MnF2-class antiferromagnet | spin/magnetism and distributed-data stress |
| ZnO-class transition-metal oxide | SCF, basis/resource, and near-gap validation |
| SrTiO3-class perovskite | campaign templating and convergence policy |

hBN cases with unresolved finite-q self-energy behavior may be diagnostic fixtures but are not accepted as scientific-reference fixtures until resolved.

### 10.3 Hard gates

The following are non-compensating failures:

- unpinned or incompatible software/data provenance;
- an unauthorized workflow transition or duplicate submission;
- missing mandatory stage or artifact lineage;
- NaN/Inf or invalid postprocessing in required outputs;
- spin, SOC, symmetry, shrink, or reader-format inconsistency;
- unmet required convergence criterion;
- reported result not traceable to the inspected run.

A hard-gate failure produces `FAIL` regardless of the weighted score.

### 10.4 Weighted score

For cases passing hard gates, the harness reports a 100-point breakdown:

| Dimension | Weight | Question |
| --- | ---: | --- |
| pre-compute prevention | 25 | Did OML find known fatal issues before expensive submission? |
| stage execution and state | 20 | Were transitions, scheduler states, artifacts, and reuse decisions correct? |
| diagnosis | 20 | Was the cause category ranked correctly and was the proposed test efficient? |
| numerical and scientific validity | 25 | Were measurements, thresholds, convergence, and conclusions correct? |
| efficiency and reproducibility | 10 | Were node-hours, retries, human interventions, and provenance controlled? |

The aggregate is never reported without the five component scores and hard-gate verdict.

### 10.5 Operational metrics

Campaign and release reports include:

- first-pass valid-run rate;
- known-fatal preflight recall and false-positive rate;
- invalid-submission count;
- diagnostic Top-1 and Top-3 accuracy;
- repair success after the first diagnosis;
- unnecessary rerun count;
- wasted node-hours;
- median human-intervention count;
- fraction reaching `LIBRPA_PASSED`, `NUMERICALLY_VALID`, and `SCIENTIFICALLY_VALID` separately;
- provenance completeness and deterministic replay rate.

### 10.6 Initial release thresholds

The first MCP execution release must satisfy:

- 100% detection of fatal conditions represented in the frozen contract fixtures;
- zero transition or duplicate-submission violations in fault-injection tests;
- 100% provenance completeness for submitted smoke stages;
- no case promoted past `LIBRPA_PASSED` when required outputs contain NaN/Inf or invalid continuation;
- diagnostic Top-3 accuracy of at least 95% on frozen failure replays;
- successful end-to-end execution of the selected small v1 periodic GW smoke case on the pinned stack.

These are release thresholds for OML behavior, not claims that arbitrary new materials will succeed on the first attempt.

## 11. Guarded Improvement Loop

OML uses a controlled improvement loop:

```text
reviewed failure
  -> immutable replay fixture
  -> candidate parser/rule/check
  -> training benchmark
  -> frozen regression and hidden holdout
  -> cost and false-positive review
  -> human approval
  -> versioned production rule set
```

Production runs may append evidence and propose candidate rules. They may not automatically modify production thresholds, compatibility profiles, templates, or diagnosis precedence.

A candidate is promoted only when it:

- fixes its target fixture;
- does not regress frozen passing cases;
- does not increase fatal false negatives;
- stays within the accepted false-positive and runtime budgets;
- includes an explanation and evidence links;
- receives explicit human approval.

This is harness-driven improvement, not autonomous mutation of scientific policy.

## 12. Error Handling and Recovery

All tool failures use stable error codes with structured recovery fields. Examples include:

- `STACK_UNAPPROVED`
- `FORMAT_MIXED`
- `GATE_FAILED`
- `STATE_TRANSITION_DENIED`
- `STALE_PLAN`
- `DUPLICATE_JOB`
- `SCHEDULER_UNOBSERVABLE`
- `ARTIFACT_PROVENANCE_MISSING`
- `OUTPUT_NUMERICALLY_INVALID`
- `CONVERGENCE_INCOMPLETE`

An SSH timeout or unavailable scheduler becomes `SCHEDULER_UNOBSERVABLE`; it is not converted into success or failure. OML preserves the last reliable observation time.

Retries are idempotent where possible. A submission timeout triggers scheduler reconciliation by run/stage identifiers before OML considers another submission. Expensive stages are never automatically rerun solely because a non-authoritative postcheck string changed.

## 13. Security and Safety

- Source directories are read-only to OML execution logic.
- Every run uses a fresh, explicit directory under an allowed root.
- Paths are resolved and checked against the configured roots; broad or unresolved deletion targets are rejected.
- The MCP API does not expose arbitrary shell, SSH, or Slurm arguments.
- OTPs, passwords, private keys, and access tokens are not stored in SQLite, manifests, logs, or tool results.
- Consequential tools are annotated accurately and require the host's normal confirmation behavior.
- The server performs its own authorization, validation, and state checks regardless of model behavior.
- Cleanup is a separate future capability and is not part of the initial MCP execution scope.

## 14. Implementation Phases

### Phase 0: specification and baseline fixtures

- freeze the three source revisions above;
- define schemas, compatibility profile, artifact contracts, and fixture layout;
- capture representative v1 ABACUS and PyATB outputs accepted by LibRPA 0.7.0;
- convert selected existing rules and failures into tests before replacing skills.

### Phase 1: read-only MCP

- implement `create_case`, `ingest_case`, `plan_case`, `validate_case`, `get_status`, `inspect_stage`, `diagnose_case`, and `score_case` for fixture replay;
- keep existing execution scripts as the production path;
- compare MCP decisions with reviewed historical cases.

### Phase 2: single-case controlled execution

- implement `prepare_run` and one-stage-at-a-time `submit_stage`;
- support one approved ABACUS periodic GW v1 route on one server profile;
- enforce state transitions, provenance, idempotency, and duplicate-job prevention;
- validate one complete smoke case.

### Phase 3: diagnostic and scientific gates

- add PyATB/head-wing, strict-2D, magnetic, continuation, and convergence validators;
- reach the initial release thresholds;
- migrate the long skill rules into tested policy modules and concise references.

### Phase 4: campaigns

- add `Campaign`, shared assets, bounded concurrency, resource budgets, retry budgets, and family-specific templates;
- pilot 20-50 reviewed cases before hundreds-material operation;
- add campaign dashboards or UI only if structured reports are no longer sufficient.

### Phase 5: guarded rule promotion

- implement candidate-rule generation, frozen/hidden evaluations, comparison reports, and explicit promotion workflow;
- never allow a production failure to edit active policy directly.

## 15. Initial Scope and Non-Goals

The first implementation milestone supports one ABACUS -> PyATB -> LibRPA periodic GW route with reader v1. It focuses on local orchestration plus an existing SSH/Slurm server profile.

The following are deliberately outside the first milestone:

- hundreds-material campaign scheduling;
- FHI-aims execution through MCP;
- RPA and Delta-Sternheimer execution through MCP;
- automatic PP/NAO/ABFS generation;
- automatic cleanup of compute results;
- autonomous production-rule modification;
- a graphical dashboard;
- public MCP hosting or plugin publication.

Existing skills and scripts remain available during migration. They are removed or reduced only after equivalent MCP behavior passes the frozen harness.

## 16. Acceptance Criteria for the Design

The implementation is faithful to this design only if:

1. Reader v1 is explicit and legacy requires an explicit profile.
2. ABACUS, PyATB, LibRPA, dependencies, assets, runtime, and OML itself are attributable.
3. The server, not the model, enforces workflow transitions and input contracts.
4. Every downstream artifact has accepted upstream provenance.
5. Scheduler state, program completion, numerical validity, convergence, and scientific validity remain separate.
6. Tool results are structured and concise while complete evidence remains accessible.
7. The harness includes hard gates, component scores, operational cost metrics, and frozen replays.
8. Candidate improvements cannot enter production without regression evidence and human approval.
9. The first controlled execution is a small single case, not a broad materials campaign.
10. Existing user data is never overwritten or silently reused as a fresh run.
