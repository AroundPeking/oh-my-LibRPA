# oh-my-LibRPA

Chat-first guidance, workflow rules, and execution helpers for **ABACUS + LibRPA** tasks inside OpenClaw.

The goal is simple:

- users talk in **natural language**
- the agent decides whether the task is **GW / RPA / debug**
- the agent asks only the **missing questions that matter**
- the workflow runs in a **fresh directory** with durable stage logs
- output review and plotting are part of the workflow, not an afterthought

---

## What this repository provides

- **Guidance for humans**: what to say, what information to provide, and what to expect from the plugin
- **Guidance for agents**: rules, cards, templates, and shell helpers for stable execution
- **Execution helpers**: preflight checks, consistency checks, workflow runners, run logging
- **Examples**: realistic end-to-end cases, not just toy prompts

Repository layout:

- `docs/guide/` — human-facing guides
- `examples/` — realistic example cases
- `references/` — living playbooks / terms / conventions
- `rules/cards/` — structured experience cards that agents can follow
- `scripts/` — execution and reporting helpers
- `templates/` — report templates and future workflow templates

---

## Install / Update

Start here:

- Installation guide: `docs/guide/installation.md`
- Windows + Git Bash guide: `docs/guide/windows-git-bash.md`

Quick install:

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/install.sh | bash
```

Quick update:

```bash
~/.openclaw/workspace/oh-my-librpa/update.sh
```

## Update

After the first install, do not repeat the full install flow unless you are repairing a broken setup.

If you want to ask an AI to update on Windows, give it this one-line prompt:

```text
On Windows, use Git Bash instead of WSL, and follow: https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/docs/guide/windows-git-bash.md
```

Use the in-place updater instead:

```bash
~/.openclaw/workspace/oh-my-librpa/update.sh
```

This reuses the recorded workspace/source information and refreshes the existing install.

If the local updater is missing, fetch the latest updater directly:

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/update.sh | bash
```

---

## How to use it in chat

If you are a user, the most important document is:

- `docs/guide/chat-guidance.md`

That guide explains:

- how to ask for a GW / RPA / debug task in natural language
- what minimum information the agent should ask back for
- how stage-by-stage progress should look
- how to continue from a successful run into plotting / postprocessing

If you want one realistic example instead of abstract rules, read:

- `examples/si-k444-gw/README.md`

That example is based on a real periodic Si GW workflow and includes:

- the initial user request
- the clarifying questions that were actually needed
- the failure / repair loop on a real HPC server
- the final plotting request and paper-style output

---

## Design principles

### 1. Chat first

Users should not need to memorize CLI flags or internal workflow names.

Good:

- “在 `ks_ghj_3` 服务器上做一个 Si 的 `k444` GW 计算，目录用 `~/gw/Si/AI/`。”
- “继续盯，直到成功。”
- “根据 `GW_band_spin_*` 画一个论文风格的能带图。”

Bad:

- requiring users to manually remember every stage script
- requiring users to pre-assemble internal helper commands

### 2. Ask only the missing questions

For periodic GW, the agent should normally clarify only the pieces that are still missing, for example:

- remote server / VPN status
- fresh run directory policy
- `KPT` mesh
- whether `KPT_nscf` already exists
- executable paths / environment profile if not already known

### 3. Prefer stable defaults, but do not guess hidden infrastructure

Scientific defaults can be opinionated.
Infrastructure defaults must be verified.

Examples:

- `nfreq = 16` is a good smoke default
- but `python3` path, MPI launcher, and batch environment **must not** be guessed blindly

### 4. Fresh directory always

Never overwrite an old calculation directory in place.
Every run, rerun, and repair should happen in a fresh directory.

### 5. Logging is part of the product

Each stage should produce:

- a short user-facing update
- a durable `run-report.md`

---

## What should improve next

This repository should keep improving in two directions at once:

1. **workflow reliability**
   - host profiles
   - batch-node probes
   - launcher selection
   - Python environment resolution
2. **user guidance quality**
   - clearer chat examples
   - better README onboarding
   - first-class plotting/postprocessing guidance

The Si `k=4x4x4` GW case in `examples/si-k444-gw/README.md` is the current best reference for both.

---

## Recommended reading order

For a new human user:

1. `docs/guide/installation.md`
2. `docs/guide/chat-guidance.md`
3. `examples/si-k444-gw/README.md`

For an agent / developer improving the workflow:

1. `references/playbook.md`
2. `rules/cards/*.yml`
3. `docs/run-logging.md`
4. `examples/si-k444-gw/README.md`

---

## One-line summary

**oh-my-LibRPA is not just a template pack. It should feel like a chat-native operator for ABACUS + LibRPA workflows.**
