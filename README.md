# oh-my-LibRPA

`oh-my-LibRPA` is a **chat-first** AI experience layer for `ABACUS + LibRPA` (and can be extended to other DFT stacks).

Goal: users describe tasks in natural language, and AI applies proven workflows and experience to prepare, validate, troubleshoot, and iterate GW/RPA calculations.

## Project-Local Install (Recommended)

This repository now supports **project-level installation** for three agent homes at once.

Boundary rule:

- `skills-core/` is the only source of truth for project LibRPA skills
- `platform/` is reserved for platform-specific adapters and notes

Supported targets:

- `OpenClaw` -> `.openclaw/workspace/`
- `OpenCode` -> `.opencode/`
- `Codex` -> `.codex-home/`

From the repository root:

```bash
bash install.sh --target all --layout project
```

Default behavior for project installs:

- installs all three targets
- prefers **symlinks** when the source repository is local
- keeps future updates easy: edit tracked files once, and linked installs see the changes immediately
- skips OpenClaw gateway restart unless you explicitly choose a user-level install

If you want copy mode instead of symlinks:

```bash
bash install.sh --target all --layout project --mode copy
```

## Per-Platform Install

Only OpenClaw:

```bash
bash install.sh --target openclaw --layout project
```

Only OpenCode:

```bash
bash install.sh --target opencode --layout project
```

Only Codex:

```bash
bash install.sh --target codex --layout project
```

## Legacy User-Level Install

The previous OpenClaw-style user install is still available:

```bash
bash install.sh --target openclaw --layout user
```

You can still control restart behavior explicitly:

```bash
bash install.sh --target openclaw --layout user --restart-mode immediate
bash install.sh --target openclaw --layout user --restart-mode defer
bash install.sh --target openclaw --layout user --restart-mode skip
```

## Install via AI

Send one of these prompts to your AI assistant:

```text
Install and configure oh-my-LibRPA by following:
https://raw.githubusercontent.com/bhjia-phys/oh-my-LibRPA/main/docs/guide/installation.md
```

```text
Bootstrap a fresh Ubuntu/WSL ABACUS + PYATB + LibRPA stack for oh-my-LibRPA by following:
https://raw.githubusercontent.com/bhjia-phys/oh-my-LibRPA/main/docs/guide/abacus-pyatb-librpa-stack.md
Then run the stack doctor and a local smoke test.
```

## After Installation

After installation, users can interact only through chat, for example:

- `Help me run GW for GaAs with a conservative setup first.`
- `This is a molecular system. Prepare inputs using the molecular route.`
- `How do we fix this error? Give me the minimal repair action.`
- `Bootstrap a fresh Ubuntu WSL stack for ABACUS + PYATB + LibRPA, then run a local smoke test.`
- `Mirror an existing FHI-aims + LibRPA QSGW case and stage a new k-point sweep first.`

Platform-local runtime hints:

- `OpenClaw`: launch with `OPENCLAW_WORKSPACE=<repo>/.openclaw/workspace`
- `Codex`: launch with `CODEX_HOME=<repo>/.codex-home`
- `OpenCode`: use the repo-local `.opencode/skills/` install or point your launcher/home override at `<repo>/.opencode`

## Current MVP Scope

- Chat orchestrator skill: `oh-my-librpa` (single entry point)
- Core workflow skills: `abacus-librpa-gw`, `abacus-librpa-rpa`, `abacus-librpa-debug`
- Supplemental workflow skill: `oh-my-librpa-fhi-aims-qsgw`
- Core stack/bootstrap skill: `abacus-pyatb-librpa-stack`
- Rule cards (structured experience): workflow defaults plus environment/install repair rules
- Templates: minimal `INPUT_scf`, `INPUT_nscf`, `librpa.in`, and a reusable stack env template
- Static checker scripts and runners: intake/preflight, route-aware consistency checks, run-safety constraints, stage reporting, GW/RPA workflow execution, environment doctor, and stack smoke tests
- Run logging: one Markdown report in the run directory, one archived copy under the active platform root, plus short stage summaries for users
- Installer self-test: validate skills, scripts, stack helpers, and default archive-root behavior right after installation

## Repository Layout

```text
oh-my-librpa/
|-- skills-core/
|   |-- oh-my-librpa/
|   |-- abacus-librpa-gw/
|   |-- abacus-librpa-rpa/
|   |-- abacus-librpa-debug/
|   |-- abacus-pyatb-librpa-stack/
|   `-- oh-my-librpa-fhi-aims-qsgw/
|-- platform/
|   |-- openclaw/
|   |-- opencode/
|   `-- codex/
|-- references/
|-- rules/cards/
|-- templates/
|-- scripts/
|-- examples/
|-- registry/
`-- docs/
```

## Design Principles

- Chat-first: users should not memorize custom commands
- Routed execution: auto-route by `molecule`, `solid`, or `2D`
- Experience-driven: curated rules over ad-hoc guessing
- Safety-first: always use new run directories and avoid overwriting source data
- Project-local first: keep agent state close to the repository and easy to update
- Extension-friendly: keep the ABACUS mainline intact while adding supplemental routes for other DFT stacks such as FHI-aims

## Safety Constraints

- Prefer static checks before any remote execution
- Every run chain must use a new isolated directory
- Never overwrite original data directories
