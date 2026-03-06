# oh-my-LibRPA

`oh-my-LibRPA` is a **chat-first** AI experience layer for `ABACUS + LibRPA` (and can be extended to other DFT stacks).

Goal: users describe tasks in natural language, and AI applies proven workflows and experience to prepare, validate, troubleshoot, and iterate GW/RPA calculations.

## Install via AI (Recommended)

Send this to your AI assistant:

```text
Install and configure oh-my-LibRPA by following:
https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/docs/guide/installation.md
```

## One-Command Install (Human)

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/install.sh | bash
```

Local development install:

```bash
cd ~/code/oh-my-librpa
bash install.sh
```

After installation, users can interact only through chat, for example:

- `Help me run GW for GaAs with a conservative setup first.`
- `This is a molecular system. Prepare inputs using the molecular route.`
- `How do we fix this error? Give me the minimal repair action.`

## Current MVP Scope

- Chat orchestrator skill: `oh-my-librpa` (single entry point)
- Core workflow skills: `abacus-librpa-gw`, `abacus-librpa-rpa`, `abacus-librpa-debug`
- Rule cards (structured experience): scene, symptom, root cause, fix, verify
- Templates: minimal `INPUT_scf`, `INPUT_nscf`, `librpa.in`
- Static checker scripts: consistency and run-safety constraints

## Repository Layout

```text
oh-my-librpa/
|-- skills/
|   |-- oh-my-librpa/
|   |-- abacus-librpa-gw/
|   |-- abacus-librpa-rpa/
|   `-- abacus-librpa-debug/
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

## Safety Constraints

- Prefer static checks before any remote execution
- Every run chain must use a new isolated directory
- Never overwrite original data directories
