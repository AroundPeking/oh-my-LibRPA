# Installation

## Codex MCP (Recommended)

Clone the repository and create its isolated Python environment:

```bash
git clone https://github.com/AroundPeking/oh-my-LibRPA.git
cd oh-my-LibRPA
bash scripts/install_codex_plugin.sh
```

Register the MCP server from the repository root:

```bash
codex mcp add oh-my-librpa -- "$PWD/bin/oh-my-librpa-mcp"
codex mcp get oh-my-librpa
```

Start a new Codex task after registration. To replace an existing registration after moving the repository, run:

```bash
codex mcp remove oh-my-librpa
codex mcp add oh-my-librpa -- "$PWD/bin/oh-my-librpa-mcp"
```

The Codex plugin bundle is described by `.codex-plugin/plugin.json` and `.mcp.json`. Direct MCP registration is the development and local-install path; a marketplace entry is not required.

### MCP tools

OML exposes five inspection tools, five execution-control tools, and one scientific-finalization tool:

| Tool | Purpose |
| --- | --- |
| `inspect_profile` | Report pinned source revisions and the exact workflow contract |
| `ingest_case` | Classify case ownership and fingerprint discovered files |
| `plan_case` | Select the deterministic GW/RPA stage graph |
| `validate_case` | Check parameters, symmetry, shrink data, datasets, and PyATB handoff |
| `inspect_reader_v1` | Inspect reader-v1 eigenvector, velocity, or complete head/wing data |
| `prepare_run` | Verify versions and materialize a fresh immutable periodic-GW run |
| `submit_stage` | Submit one fixed stage after provenance, order, and duplicate gates |
| `get_status` | Observe current or historical scheduler state without changing it |
| `inspect_stage` | Validate completed stage artifacts and record an immutable verdict |
| `finalize_case` | Evaluate a passed 3D GW snapshot against registered scientific policy |
| `score_case` | Apply the versioned scorecard and non-compensating hard gates |

The five original tools and `get_status`/`score_case` are read-only. `prepare_run`, `submit_stage`, `inspect_stage`, and idempotent `finalize_case` are consequential but bounded. Controlled execution is disabled until an administrator installs an enabled execution profile. See [`controlled-execution.md`](controlled-execution.md) for the profile schema, fixed sequence, receipts, scorecard, and current exclusions.

`get_status` and `score_case` do not create a missing state database. Preparation is the operation that initializes controlled state.

## Pinned Compatibility Profile

The default profile is `profiles/abacus-librpa-pyatb-2026-08.json`:

| Component | Ref | Audited revision |
| --- | --- | --- |
| ABACUS | `AroundPeking/abacus-develop:master_ghj` | `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e` |
| LibRPA | `Srlive1201/LibRPA:v0.7.0` | `dd169fa11fa920d580d4f39dc11e218a7f17f7b5` |
| PyATB | `AroundPeking/pyatb:enable_head_wing` | `9fb9028c59b1dbaf9cf66965280961fc2225d9eb` |

The OML production policy explicitly uses reader-v1:

- ABACUS: `out_librpa_reader_version 1`
- LibRPA: `version_coul_reader 1` and `version_lri_reader 1`
- mean-field files: `prefix_eigvecs_scf = KS_eigenvector` and `fn_eigocc_scf = band_out`
- GW-only files: `prefix_coul_cut = v1_coulomb_cut_iq_` and `fn_vxc_scf = vxc_out`
- LibRPA GW task: `g0w0`; `g0w0_band` is accepted only as a deprecated compatibility alias
- symmetry keys: `use_symmetry_exx`, `use_symmetry_gw`, and `use_symmetry_rpa`
- symmetry metadata: read from `stru_out`; no legacy symmetry sidecars are copied
- PyATB handoff: `input_dir/pyatb_librpa_df` on the full regular k grid

The ABACUS source default for `out_librpa_reader_version` is still `0`, and the LibRPA reader defaults are still `-1`. These are source facts, not the OML production defaults above.

### Refresh the source audit

Clone or update the three exact refs, then run:

```bash
.venv/bin/python scripts/audit_upstream_contract.py \
  --abacus /path/to/abacus-develop \
  --librpa /path/to/LibRPA \
  --pyatb /path/to/pyatb
```

Do not update the profile SHAs or parameter contract unless this audit and the complete test suite pass against the intended source revisions.

## Legacy Skills Installer

The following path remains for OpenClaw-compatible skills and the existing execution scripts.

### For Humans

Copy this prompt to your AI agent:

```text
Install and configure oh-my-LibRPA by following:
https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/docs/guide/installation.md
```

Or run one command:

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/install.sh | bash
```

To update later without repeating workspace setup, run:

```bash
~/.openclaw/workspace/oh-my-librpa/update.sh
```

If you want an AI to handle the update on Windows, give it this one-line prompt:

```text
On Windows, use Git Bash instead of WSL, and follow: https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/docs/guide/windows-git-bash.md
```

Or fetch the latest updater directly:

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/update.sh | bash
```

After installation, users only need natural-language chat (no CLI memorization).

If installation is triggered from inside an active OpenClaw chat, the installer now keeps the conversation alive by deferring the gateway restart and printing the manual restart command.

### For LLM Agents

Fetch this guide via shell (do not summarize away actionable details):

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/docs/guide/installation.md
```

Then run installer:

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/install.sh | bash
```

If repository is local (development mode), run:

```bash
cd ~/code/oh-my-librpa
bash install.sh
```

On Windows / Git Bash, prefer setting the workspace explicitly if OpenClaw workspace detection is uncertain:

```bash
OH_MY_LIBRPA_WORKSPACE="$HOME/.openclaw/workspace" bash install.sh
```

### What the Legacy Installer Does

- Detect OpenClaw workspace from `OH_MY_LIBRPA_WORKSPACE`, then `OPENCLAW_WORKSPACE`, then `~/.openclaw/openclaw.json`, and finally fall back to `~/.openclaw/workspace`
- Install skills into `<workspace>/skills/`
- Install rules/templates/docs/scripts into `<workspace>/oh-my-librpa/`
- Copy `install.sh` and `update.sh` into `<workspace>/oh-my-librpa/` for future maintenance
- Prefer `rsync` for copying, but fall back to `cp -R` when `rsync` is unavailable
- Write `install-state.env` so future updates know the last source, repo, branch, and workspace
- Make shipped shell scripts executable
- Run a local post-install self-test for the installed skills, scripts, metadata, and log-writing path
- Restart gateway in a normal shell install
- Defer gateway restart automatically when installation is launched from an active OpenClaw conversation, so the current chat is not interrupted

If you want to control restart behavior explicitly:

```bash
OH_MY_LIBRPA_RESTART_MODE=immediate bash install.sh
OH_MY_LIBRPA_RESTART_MODE=defer bash install.sh
OH_MY_LIBRPA_RESTART_MODE=skip bash install.sh
```

You can rerun the validation manually after installation:

```bash
~/.openclaw/workspace/oh-my-librpa/scripts/self_test.sh
```

The updater reuses `~/.openclaw/workspace/oh-my-librpa/install-state.env` when available. If that file is missing, it falls back to the default repository URL and workspace detection.

## Validation

Validate the MCP implementation from the repository root:

```bash
.venv/bin/python -m unittest discover -s tests -v
bash scripts/self_test.sh --workspace "$PWD"
```

Then test from a new Codex task:

- `Inspect the pinned OML profile.`
- `Ingest this calculation directory and report mixed ownership or missing inputs.`
- `Validate this periodic GW case at the pre-LibRPA gate.`
- `Inspect this PyATB head/wing directory as reader-v1.`

For the legacy skills installation, read these first:

- `docs/guide/chat-guidance.md`
- `examples/si-k444-gw/README.md`

After that, test by chat only:

- `Help me run GW for Si with a conservative setup first.`
- `This is a molecular system. Prepare inputs with the molecular route.`
- `How do we fix this error? Give me the minimal repair action based on experience.`
- `Mirror an existing FHI-aims + LibRPA QSGW case and stage a new k-point sweep first.`

Expected behavior:

- AI routes to GW/RPA/debug workflow automatically
- AI routes first into one of two stack-layer skills: `ABACUS -> LibRPA` or `FHI-aims -> LibRPA`
- AI then routes ABACUS cases into GW/RPA/debug workflow automatically
- AI routes `FHI-aims + LibRPA` QSGW/G0W0 requests to the supplemental workflow only when strong FHI-aims markers are present, such as `control.in`, `run_librpa_gw_aims_iophr.sh`, or explicit tasks such as `qsgw_band`
- AI does not treat `geometry.in` by itself as an FHI-aims-only marker; ambiguous bundles keep the existing ABACUS-first behavior until stronger ownership evidence appears
- AI starts with intake/preflight and tells the user what is missing before execution
- AI applies curated experience rules and explains why
- AI enforces run-safety constraints (new directory, no overwrite)
- Future refreshes can use `~/.openclaw/workspace/oh-my-librpa/update.sh` instead of repeating the initial install flow
