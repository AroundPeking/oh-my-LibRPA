# Installation

## For Humans

Copy this prompt to your AI agent:

```text
Install and configure oh-my-librpa by following:
https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/docs/guide/installation.md
```

Or run one command:

```bash
curl -fsSL https://raw.githubusercontent.com/AroundPeking/oh-my-LibRPA/main/install.sh | bash
```

That is all. After install, users only need natural language chat (no CLI memorization).

## For LLM Agents

Use shell fetch (do not summarize away details):

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

## What installer does

- Detect OpenClaw workspace automatically (no hard-coded path required)
- Install skills into `<workspace>/skills/`
- Install rules/templates/docs/scripts into `<workspace>/oh-my-librpa/`
- Restart gateway

## Validate

After install, test by chat only:

- `帮我做 Si 的 GW，先按稳妥参数跑通。`
- `这是分子体系，按分子路线给我准备输入。`
- `这个报错怎么修，按你经验给最小修复动作。`

Expected behavior:

- AI routes to GW/RPA/debug workflow automatically
- AI applies experience rules and explains why
- AI enforces safe run-dir constraints (new directory, avoid overwrite)
