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

After installation, users only need natural-language chat (no CLI memorization).

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

## What the Installer Does

- Detect OpenClaw workspace automatically (no hard-coded path required)
- Install skills into `<workspace>/skills/`
- Install rules/templates/docs/scripts into `<workspace>/oh-my-librpa/`
- Restart gateway

## Validation

After install, test by chat only:

- `Help me run GW for Si with a conservative setup first.`
- `This is a molecular system. Prepare inputs with the molecular route.`
- `How do we fix this error? Give me the minimal repair action based on experience.`

Expected behavior:

- AI routes to GW/RPA/debug workflow automatically
- AI applies curated experience rules and explains why
- AI enforces run-safety constraints (new directory, no overwrite)
