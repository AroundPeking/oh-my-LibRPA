# Playbook (Living Document)

## Core Principles

- Change in small steps: modify one major parameter at a time.
- Close the chain first: get a minimal case running before scaling up.
- Prevent contamination: always use a fresh run directory.

## Quick Smoke Guidance

- Start with `nfreq = 16` to validate workflow closure.
- Increase frequency points and accuracy settings only after smoke success.

## How to Capture New Experience

Every new lesson should be converted into `rules/cards/*.yml` with fields:

- scene
- symptom
- root_cause
- fix
- verify
- applies_to
