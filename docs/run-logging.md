# Run Logging

Every compute or debug task should produce two outputs:

1. a short user-facing progress update after each stage
2. two durable Markdown run logs saved outside the repository:
   - one in the active run directory as `run-report.md`
   - one archived under `~/.openclaw/workspace/librpa/oh-my-librpa/`

The repository should keep only the logging rules and templates. Runtime logs must not be written into the `oh-my-LibRPA` git tree.

## File Naming

Use one report per task in both locations:

- `<run_dir>/run-report.md`
- `~/.openclaw/workspace/librpa/oh-my-librpa/<timestamp>-gw.md`
- `~/.openclaw/workspace/librpa/oh-my-librpa/<timestamp>-rpa.md`
- `~/.openclaw/workspace/librpa/oh-my-librpa/<timestamp>-debug.md`

Example:

- `/path/to/calc/run-report.md`
- `~/.openclaw/workspace/librpa/oh-my-librpa/2026-03-06-2235-gw.md`

## Minimum Required Content

Each Markdown run log should record:

- task type
- compute location
- working directory
- input file bundle
- key parameters
- per-stage timestamps
- per-stage status: `success`, `running`, or `failed`
- key output files
- final result
- next suggested action

## User-Facing Update Format

After each stage update, send the user a short summary with exactly these three parts:

- `what was done`
- `what was observed`
- `what is next`

Do not dump the entire Markdown file into chat unless the user explicitly asks for it.

## Recommended Stage Names

For GW:

- `scf`
- `pyatb`
- `nscf`
- `preprocess`
- `librpa`

For RPA:

- `scf`
- `librpa`

For debug:

- `intake`
- `stage-identification`
- `root-cause`
- `repair-plan`
- `validation`

## Status Convention

Use the same simple convention everywhere:

- `success`: stage reached its completion markers
- `running`: stage has not finished but its output is still progressing
- `failed`: stage is neither complete nor still progressing
