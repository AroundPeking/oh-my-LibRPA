# Run Logging

Every compute or debug task should produce two outputs:

1. a short user-facing progress update after each stage
2. a durable Markdown run log saved under `logs/runs/`

## File Naming

Use one file per task:

- `logs/runs/<timestamp>-gw.md`
- `logs/runs/<timestamp>-rpa.md`
- `logs/runs/<timestamp>-debug.md`

Example:

- `logs/runs/2026-03-06-2222-gw.md`

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
