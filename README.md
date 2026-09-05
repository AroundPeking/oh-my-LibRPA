<div align="center">
  <img src="docs/assets/brand/oh-my-librpa-wordmark.svg" alt="oh-my-LibRPA wordmark" width="760" />
  <p>
    Describe the task in natural language. The MCP server inspects the case,
    selects the route, and applies deterministic gates before any calculation is submitted.
  </p>

  <p>
    <a href="https://github.com/AroundPeking/oh-my-LibRPA/releases"><img src="https://img.shields.io/github/v/release/AroundPeking/oh-my-LibRPA?style=flat-square&labelColor=0f172a" alt="GitHub release" /></a>
    <a href="https://github.com/AroundPeking/oh-my-LibRPA/stargazers"><img src="https://img.shields.io/github/stars/AroundPeking/oh-my-LibRPA?style=flat-square&labelColor=0f172a" alt="GitHub stars" /></a>
    <a href="https://github.com/AroundPeking/oh-my-LibRPA/network/members"><img src="https://img.shields.io/github/forks/AroundPeking/oh-my-LibRPA?style=flat-square&labelColor=0f172a" alt="GitHub forks" /></a>
    <a href="https://github.com/AroundPeking/oh-my-LibRPA/issues"><img src="https://img.shields.io/github/issues/AroundPeking/oh-my-LibRPA?style=flat-square&labelColor=0f172a" alt="GitHub issues" /></a>
    <a href="https://github.com/AroundPeking/oh-my-LibRPA/commits/main"><img src="https://img.shields.io/github/last-commit/AroundPeking/oh-my-LibRPA?style=flat-square&labelColor=0f172a" alt="Last commit" /></a>
  </p>

  <p>
    <a href="docs/guide/installation.md"><strong>Installation</strong></a>
    ·
    <a href="docs/guide/chat-guidance.md"><strong>Chat guide</strong></a>
    ·
    <a href="examples/si-k444-gw/README.md"><strong>Si GW example</strong></a>
    ·
    <a href="#what-you-get"><strong>What you get</strong></a>
  </p>
</div>

---

## What this is

<div align="center">
  <img src="docs/assets/oh-my-librpa-workflow-overview.png" alt="oh-my-LibRPA workflow overview: crystal input to GW/RPA calculation to band-structure output" width="620" />
  <br />
  <sub>Crystal/material inputs in, curated GW/RPA workflow, band-structure artifact out.</sub>
</div>

`oh-my-LibRPA` is a Codex plugin and deterministic MCP harness for `ABACUS + LibRPA`.

The idea is simple:

- users should talk in **natural language**, not memorize workflow commands
- the agent should understand whether the case is **molecule / solid / 2D**
- version-sensitive decisions should come from **MCP tools and a pinned source contract**, not prompt recall
- expensive runs should still respect **fresh directories**, **static checks**, and **stage-by-stage validation**

In practice, that means the agent can help with:

- preparing GW / RPA inputs
- auditing uploaded bundles instead of blindly rewriting them
- catching route mismatches before remote execution
- running and reporting each critical stage
- producing a final scientific artifact such as a **paper-style GW band plot**

> [!TIP]
> The current default is admission profile `abacus-librpa-2026-09-06-v5`; it does not authorize unattended production. The old 0.3.1, v2, and v4 profiles remain immutable reproductions, while v3 reproduces the corrected Sternheimer Coulomb handoff that is absent from current ABACUS master.

### Compatibility generations

OML keeps historical profiles
`abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08`,
`abacus-librpa-2026-08-30-v2`, `abacus-librpa-2026-08-30-v3`, and
`abacus-librpa-2026-09-03-v4` unchanged for explicit reproduction. Current
default `abacus-librpa-2026-09-06-v5` pins ABACUS
`1648a8a344427ae1b6394912bf677c4a20e053f2`, LibRPA
`7e40c5bbf735a78aa15fa589ca2468fec2e2427b`, and PyATB
`9fb9028c59b1dbaf9cf66965280961fc2225d9eb` for four admission routes:

- periodic 3D GW;
- strict-2D GW with full Ewald Coulomb and analytic Gamma head/wing;
- molecular Delta-Sternheimer RPA;
- solid Delta-Sternheimer RPA.

Periodic 3D GW is `EXPERIMENTAL` at L3. The fixed-continuation
`nfreq=24 -> 32` pair and BN screening `12x12x12 -> 14x14x14` pair pass their
declared `0.05 eV` gates, but symmetry/full-q, basis, transfer, and physical
reference gates still prevent L4 acceptance. The other v5 routes remain
`TESTABLE`. Current Delta-Sternheimer remains blocked at the
dedicated response-Coulomb handoff. Routes become `EXPERIMENTAL` only after reviewed
L0-L3 receipts, and `ENABLED` only after L4 scientific acceptance and a reviewed
profile commit. OML explicitly selects reader v1. Symmetry comes from `stru_out`,
LibRPA reconstructs rotations, and legacy symmetry sidecars are never copied.
Automatic evolution changes one registered parameter at a time and produces a
`PROPOSAL_ONLY` record; it cannot submit a job or promote policy.

The production benchmark scorecard is `oml-production-benchmark-v3`. It keeps
material identity, scientific reference, convergence claim boundaries, and
known false-pass fixtures as non-compensating hard gates; performance points
cannot override a failed scientific gate.

The separate profile `abacus-librpa-2026-09-02-strict2d-sos-rpa-v1` and
manifest `df-dcu-strict2d-sos-rpa-2026-09-02-v1` register the
`strict_2d_sos_rpa` LibRPA-only replay as `TESTABLE`. It fixes reader-v1,
full 2D Ewald, `nfreq=16`, and qavg head/wing, forbids ABACUS/PyATB reruns, and
records N=8/10/12/16 as functional and numerical validation only. The four
meshes do not establish a stable asymptotic k-point convergence law.

The reviewed profile `abacus-librpa-2026-09-03-strict2d-sos-rpa-v2` promotes
that exact replay to `ENABLED` using benchmark
`strict2d-sos-rpa-mos2-qavg-v1`. Its reference-bounded criterion accepts the
documented four-mesh trend, Gamma area scaling, endpoint change, fit residual,
extrapolation span, and finite-q control. It makes no asymptotic exponent claim
and is not strict-2D GW acceptance.

---

## Quick start

### 1. Install the MCP environment

```bash
git clone https://github.com/AroundPeking/oh-my-LibRPA.git
cd oh-my-LibRPA
bash scripts/install_codex_plugin.sh
```

### 2. Register the MCP server in Codex

Run this from the repository root so Codex stores the absolute launcher path:

```bash
codex mcp add oh-my-librpa -- "$PWD/bin/oh-my-librpa-mcp"
codex mcp get oh-my-librpa
```

Start a new Codex task after registration. The repository also contains a Codex plugin manifest at `.codex-plugin/plugin.json`; marketplace packaging can use the same MCP definition in `.mcp.json`.

### 3. Start chatting

Example prompts:

- `Inspect this ABACUS + LibRPA GW case and tell me which gates fail.`
- `Plan a symmetry-enabled periodic GW calculation, but do not submit it.`
- `Check whether these PyATB head/wing files match reader-v1.`
- `Explain the minimal repair for this LibRPA input.`

The MCP-first skill uses `inspect_profile`, `inspect_admission_manifest`,
`ingest_case`, `plan_case`, `validate_case`, `inspect_reader_v1`,
`inspect_grid_coulomb_consistency`, `inspect_sternheimer_comparison`,
`inspect_route_benchmark`, `evaluate_route_benchmark`,
`evaluate_route_benchmark_suite`, `evaluate_admission`, and
`propose_evolution_candidate` before the controlled
write tools `prepare_run`, `submit_stage`, `get_status`, `inspect_stage`,
`finalize_case`, and `score_case`. Evolution candidates are proposal-only.
Execution requires a reviewed profile ID and immutable plan digest; no tool
accepts arbitrary command text.

`inspect_grid_coulomb_consistency` is the pre-response gate. It requires the
dedicated `v1_sternheimer_coulomb_iq_*` metric, checks its reader-v1 structure,
Hermiticity, and positive spectrum, and compares `STERNHEIMER_GRID_COULOMB.dat`
when that diagnostic is present. The ordinary `v1_coulomb_full_iq_*` RI/Ewald
matrix is reported only as a diagnostic and cannot replace the metric used to
generate the Sternheimer perturbations. The default response/grid relative-norm
tolerance is `1e-6`.

`inspect_sternheimer_comparison` checks one immutable single-rank diagnostic
family and reports Delta-ST versus same-state LCAO-SOS spectra, trace-log
integrands, reconstructed Delta components, and isolated generalized-eigenvalue
outliers. All trace-log values use the dedicated Sternheimer metric. A passing
numerical comparison still does not become scientific acceptance automatically.

The current production write scope is deliberately narrower than inspection: nonmagnetic, non-SOC, three-dimensional periodic GW only. The v2 and v3 routes remain blocked from the production materializer.

### Legacy skills installation

The OpenClaw-compatible skills and execution scripts are still available during the migration:

```text
Install and configure oh-my-LibRPA by following:
https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/docs/guide/installation.md
```

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/install.sh | bash
```

### Update an existing install

After the first install, use the in-place updater instead of repeating the full install flow:

```bash
~/.openclaw/workspace/oh-my-librpa/update.sh
```

If the local updater is missing:

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/update.sh | bash
```

For Windows + Git Bash agent updates, see:

- [`docs/guide/windows-git-bash.md`](docs/guide/windows-git-bash.md)

---

## What you get

### Chat-first orchestration

- MCP-first entry point with deterministic structured results
- thin `oh-my-librpa` skill that routes into MCP before detailed references
- stack-layer skill: `oh-my-librpa-abacus-librpa`
- stack-layer skill: `oh-my-librpa-fhi-aims-qsgw`
- file-first intake for structures, inputs, logs, and archives
- compute-location handshake before expensive work starts
- route selection by `molecule`, `solid`, or `2D`

### Route-aware workflow logic

- **molecular GW** short route
- **periodic GW** full route
- **periodic GW symmetry** lane with ABACUS symmetry metadata carried by `stru_out`
- **RPA** split from GW-only preprocessing
- **FHI-aims + LibRPA QSGW/G0W0** supplement for case mirroring and staged campaigns
- spin / SOC consistency checks across helper scripts and `librpa.in`

### Safety + reproducibility

- accurate read/write MCP annotations and default-disabled controlled execution
- pinned revisions for ABACUS, LibRPA, and PyATB
- SHA-256 fingerprints for discovered case files
- new isolated run directory per run chain
- when reusing an old case, copy only source inputs and helper scripts into the new run directory; never carry over generated outputs such as `OUT.ABACUS`, `band_out`, `coulomb_*`, `LibRPA*.out`, `librpa.d`, `time.json`, or old GW data
- static preflight before remote execution
- source-backed LibRPA frequency-grid checks: production RPA/GW uses minimax,
  with a GreenX-supported even `nfreq` from 6 through 34
- Markdown run reports written both in-run and to archive
- stage-by-stage reporting for SCF / pyatb / NSCF / preprocess / LibRPA
- **absolute reproducibility**: all conversations, intermediate specs, and code versions are archived with structured naming — enabling quantitative evaluation of AI-assisted physics workflows (inspired by [DMRG-LLM, arXiv:2604.04089](https://arxiv.org/abs/2604.04089))

### Reusable assets

- machine-readable compatibility profile and upstream source-audit script
- curated rule cards
- route-aware templates
- workflow helpers for preflight, checks, execution, and reporting
- bundled plotting helper for periodic GW results
- example server-profile conventions for reproducible runtime setup

---

## Workflow lanes

```text
Molecule GW:      SCF -> LibRPA
Periodic GW:      SCF -> pyatb -> NSCF -> preprocess -> LibRPA
Periodic GW sym:  SCF(symmetry=1,rpa=1,no SOC, stru_out metadata) -> pyatb -> NSCF(symmetry=-1) -> preprocess -> LibRPA(symmetry flags)
RPA:              SCF -> LibRPA
Strict-2D SOS-RPA: validated ABACUS/PyATB producer -> LibRPA only (qavg, reference-bounded ENABLED)
Strict-2D GW v2:  SCF -> pyatb -> NSCF -> preprocess -> LibRPA
Molecular Delta:  ground state -> Sternheimer response -> LibRPA
Solid Delta:      ground state -> Sternheimer response -> LibRPA
```

OML explicitly selects reader-v1 even though the inspected ABACUS and LibRPA source defaults are legacy/auto values. It also writes the main mean-field names explicitly: `prefix_eigvecs_scf = KS_eigenvector`, `fn_eigocc_scf = band_out`, and, for GW, `fn_vxc_scf = vxc_out`. Symmetry operations are read from `stru_out`; the old symmetry sidecar files are not required. For SOC cases, do not use the periodic symmetry lane. Keep the ABACUS side on `symmetry = -1` and do not enable the LibRPA symmetry flags.

The agent should decide the lane from the user's files, intent, and system type — then explain what it is doing and why.

---

## Documentation map

If you only open three pages, open these:

| Page | What it is for |
| --- | --- |
| [`docs/guide/installation.md`](docs/guide/installation.md) | Full install flow for agents and humans |
| [`docs/guide/chat-guidance.md`](docs/guide/chat-guidance.md) | What the user should say, what the agent should ask, and how the interaction should feel |
| [`examples/si-k444-gw/README.md`](examples/si-k444-gw/README.md) | A realistic periodic GW walkthrough with final output expectations |

Useful supporting material:

| Path | Purpose |
| --- | --- |
| `skills/` | Chat-facing skills |
| `docs/guide/fhi-aims-librpa-qsgw.md` | Supplemental route for `FHI-aims + LibRPA` QSGW/G0W0 cases |
| `docs/research-siab-first-order-wavefunction-plan.md` | Uniform-grid SH/delta-SH and SIAB first-order-wavefunction research plan |
| `docs/live-benchmarks/2026-08-13-df-bn-reader-v1-shrink.md` | Live DF reader-v1, symmetry, shrink, and frozen-consumer evidence |
| `docs/live-benchmarks/2026-08-30-fisherd-v2-admission.md` | Current-stack Fisherd admission evidence for four v2 routes and the evolution scorecard |
| `docs/live-benchmarks/2026-08-30-fisherd-v3-sternheimer-handoff.md` | Corrected solid and molecular Sternheimer Coulomb handoff evidence |
| `docs/live-benchmarks/2026-09-02-df-dcu-strict2d-sos-rpa.md` | df_dcu strict-2D SOS-RPA N=8/10/12/16 validation and remaining asymptotic k-convergence boundary |
| `docs/benchmarks/benchmark-matrix-v1.md` | Route and material-class benchmark coverage, hard evidence, and pending references |
| `rules/cards/` | Structured experience: scene → symptom → root cause → fix → verify |
| `templates/` | Workflow templates and plotting helpers |
| `scripts/` | Preflight, consistency checks, stage reporting, and workflow runners |
| `references/` | Shared notes such as server-profile conventions |
| `registry/` | Example runtime profiles and registry-style assets |

---

## Example final result

<div align="center">
  <img src="docs/assets/si-gw-band-paper.png" alt="Si GW band figure" width="860" />
  <br />
  <sub>Paper-style GW band figure generated from a chat-driven periodic GW workflow.</sub>
</div>

### Result pipeline

```text
chat request
  -> route selection
  -> intake / consistency checks
  -> stage-by-stage execution
  -> archived run report
  -> final scientific artifact
```

This is the shape the project is aiming for: not just “some scripts,” but a workflow that is **explainable**, **checkable**, and **pleasant to drive from chat**.

---

## Current MVP scope

- MCP inspection plus bounded one-stage-at-a-time execution for non-SOC periodic GW
- immutable plan, execution, manifest, attempt, observation, and stage-inspection receipts
- versioned 100-point benchmark scorecard with non-compensating hard gates and frozen replays
- route-specific reference benchmarks with machine-evaluated non-compensating scientific gates
- frozen positive/negative regression suites that report false-pass and false-block counts
- approved helper-script hashes, executable fingerprints, and safe ambiguous-submission reconciliation
- pinned compatibility profile: ABACUS `master_ghj`, LibRPA `v0.7.0`, PyATB `enable_head_wing`
- separate v2 admission profile for current ABACUS/LibRPA/PyATB revisions and four testable routes
- explicit reader-v1 policy and `stru_out` symmetry validation without legacy sidecars
- PyATB head/wing validation under `input_dir/pyatb_librpa_df`
- chat orchestrator skill: `oh-my-librpa`
- stack-layer routing skill: `oh-my-librpa-abacus-librpa`
- stack-layer routing skill: `oh-my-librpa-fhi-aims-qsgw`
- core workflow skills: `abacus-librpa-gw`, `abacus-librpa-rpa`, `abacus-librpa-debug`
- rule cards for workflow defaults and repair patterns
- route materialization for molecular GW and generic periodic lanes
- intake / preflight / consistency helper scripts
- stage-aware GW and RPA runners
- Markdown run logging in both run directory and archive
- self-test after install/update
- periodic GW plotting helper for compact paper-style figures

---

## Repository layout

```text
oh-my-librpa/
|-- .codex-plugin/plugin.json
|-- .mcp.json
|-- bin/oh-my-librpa-mcp
|-- oml_mcp/
|-- profiles/
|-- skills/
|   |-- oh-my-librpa/
|   |-- oh-my-librpa-abacus-librpa/
|   |-- abacus-librpa-gw/
|   |-- abacus-librpa-rpa/
|   |-- oh-my-librpa-fhi-aims-qsgw/
|   `-- abacus-librpa-debug/
|-- references/
|-- rules/cards/
|-- templates/
|-- scripts/
|-- tests/
|-- examples/
|-- registry/
`-- docs/
```

---

## Design principles

- **Chat-first** — users should not memorize custom workflow commands
- **Contract-first** — source-derived parameters and artifacts are represented as structured data
- **Bounded execution** — validation, scheduler observation, stage acceptance, and scientific validity remain separate
- **Experience-driven** — curated rules are preferred over ad-hoc prompting
- **Route-aware** — molecule, solid, and 2D cases should not be treated as the same workflow
- **Extension-friendly** — keep the ABACUS mainline intact while adding supplemental routes for other DFT stacks such as FHI-aims
- **Safety-first** — fresh run directories, static checks first, no silent overwrite of source data
- **Report what happened** — every important stage should say what was done, what was observed, and what is next
- **Reproducible by default** — every conversation, spec, and code version is preserved for post-hoc analysis and quantitative evaluation

---

## Safety constraints

- prefer static checks before remote execution
- every run chain must use a new isolated directory
- never overwrite original data directories
- for expensive or long jobs, confirm compute location and resource choice first

---

## AITP integration

oh-my-LibRPA is the **domain skill** for the [AITP Research Protocol](https://github.com/bhjia-phys/AITP-Research-Protocol) — a protocol-first research runtime that turns AI agents into disciplined physics collaborators.

- **AITP manages the research lifecycle** (projects, layers, gates, human interaction).
- **oh-my-LibRPA provides the domain knowledge** (contracts, operations, invariants, routing).
- They communicate through structured contract files on disk.

Both projects share a commitment to externalized specifications and absolute reproducibility, formalized in the AITP [Externalized Spec Protocol](https://github.com/bhjia-phys/AITP-Research-Protocol/blob/main/research/knowledge-hub/EXTERNALIZED_SPEC_PROTOCOL.md).

For the full integration guide, see [`docs/aitp-integration.md`](docs/aitp-integration.md).

The domain manifest is at [`registry/domain-manifest.abacus-librpa.json`](registry/domain-manifest.abacus-librpa.json).

---

## One-line pitch

> **oh-my-LibRPA turns ABACUS + LibRPA workflow knowledge into a chat-native, route-aware, safety-conscious agent layer.**
