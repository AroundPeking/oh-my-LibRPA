# Installation

## For Humans

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

## For LLM Agents

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

## What the Installer Does

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

After install, read these first:

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
