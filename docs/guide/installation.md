# Installation

## Recommended: Project-Local Install

Run from the repository root:

```bash
bash install.sh --target all --layout project
```

This installs `oh-my-LibRPA` into three repo-local agent homes at once.

Boundary rule:

- install core domain skills from `skills-core/`
- keep platform-specific notes and adapters under `platform/`

Supported targets:

- `OpenClaw` -> `.openclaw/workspace/`
- `OpenCode` -> `.opencode/`
- `Codex` -> `.codex-home/`

Default behavior for project installs:

- `--target all`
- `--layout project`
- `--mode auto`
- `--mode auto` resolves to `link` when the source repository is local
- `--mode auto` resolves to `copy` when the installer has to clone a temporary source

If you want a pure copy install instead of symlinks:

```bash
bash install.sh --target all --layout project --mode copy
```

## Install Specific Targets

```bash
bash install.sh --target openclaw --layout project
bash install.sh --target opencode --layout project
bash install.sh --target codex --layout project
```

You can also combine targets:

```bash
bash install.sh --target openclaw,codex --layout project
```

## Legacy User-Level Install

The previous OpenClaw-style install still works:

```bash
bash install.sh --target openclaw --layout user
```

User-level homes can also be overridden explicitly:

```bash
OH_MY_LIBRPA_OPENCLAW_WORKSPACE="$HOME/.openclaw/workspace" bash install.sh --target openclaw --layout user
OH_MY_LIBRPA_OPENCODE_HOME="$HOME/.opencode" bash install.sh --target opencode --layout user
OH_MY_LIBRPA_CODEX_HOME="$HOME/.codex" bash install.sh --target codex --layout user
```

## Install via AI Agent

Copy one of these prompts to your AI agent:

```text
Install and configure oh-my-LibRPA by following:
https://raw.githubusercontent.com/bhjia-phys/oh-my-LibRPA/main/docs/guide/installation.md
```

```text
Bootstrap a fresh Ubuntu/WSL ABACUS + PYATB + LibRPA stack for oh-my-LibRPA by following:
https://raw.githubusercontent.com/bhjia-phys/oh-my-LibRPA/main/docs/guide/abacus-pyatb-librpa-stack.md
Then run the stack doctor and a local smoke test.
```

## What the Installer Does

For each selected target, the installer:

- installs core skills from `skills-core/` into `<target-root>/skills/`
- installs rules/templates/docs/scripts into `<target-root>/oh-my-librpa/`
- prefers symlinks for project-local installs from a local repo checkout
- falls back to copy mode when the source is temporary or remote
- makes shipped shell scripts executable
- runs a local post-install self-test for the installed skills, scripts, stack helpers, and default archive-root behavior

Target roots:

- `OpenClaw` project root: `<project>/.openclaw/workspace`
- `OpenCode` project root: `<project>/.opencode`
- `Codex` project root: `<project>/.codex-home`

## Restart Behavior

OpenClaw gateway restart is only relevant for `--target openclaw --layout user`.

Control it explicitly with:

```bash
bash install.sh --target openclaw --layout user --restart-mode immediate
bash install.sh --target openclaw --layout user --restart-mode defer
bash install.sh --target openclaw --layout user --restart-mode skip
```

For project-local installs, the installer skips restart and prints the target paths instead.

## Validation

You can rerun validation manually for any installed target:

```bash
<target-root>/oh-my-librpa/scripts/self_test.sh \
  --skills-root <target-root>/skills \
  --installed-root <target-root>/oh-my-librpa
```

Examples:

```bash
./.openclaw/workspace/oh-my-librpa/scripts/self_test.sh \
  --skills-root ./.openclaw/workspace/skills \
  --installed-root ./.openclaw/workspace/oh-my-librpa

./.opencode/oh-my-librpa/scripts/self_test.sh \
  --skills-root ./.opencode/skills \
  --installed-root ./.opencode/oh-my-librpa

./.codex-home/oh-my-librpa/scripts/self_test.sh \
  --skills-root ./.codex-home/skills \
  --installed-root ./.codex-home/oh-my-librpa
```

For stack-level environment checks after installation:

```bash
<target-root>/oh-my-librpa/scripts/stack_env_doctor.sh --env-script <your-env.sh>
<target-root>/oh-my-librpa/scripts/stack_smoke_test.sh --case-dir <case_dir> --env-script <your-env.sh>
```

The detailed Ubuntu/WSL stack recipe lives in:

- `docs/guide/abacus-pyatb-librpa-stack.md`

## Runtime Hints

After installation, test by chat only:

- `Help me run GW for Si with a conservative setup first.`
- `This is a molecular system. Prepare inputs with the molecular route.`
- `How do we fix this error? Give me the minimal repair action based on experience.`

Platform hints:

- `OpenClaw`: launch with `OPENCLAW_WORKSPACE=<repo>/.openclaw/workspace`
- `Codex`: launch with `CODEX_HOME=<repo>/.codex-home`
- `OpenCode`: use the repo-local `.opencode/skills/` install or point your launcher/home override at `<repo>/.opencode`

Expected behavior:

- AI routes to GW/RPA/debug workflow automatically
- AI routes install/repair requests for `ABACUS + PYATB + LibRPA` to the stack-bootstrap/doctor skill first
- AI starts with intake/preflight and tells the user what is missing before execution
- AI applies curated experience rules and explains why
- AI enforces run-safety constraints (new directory, no overwrite)
