---
name: abacus-librpa-debug
description: Diagnose ABACUS + LibRPA RPA/GW failures from logs and inputs. Use when runs fail, outputs are inconsistent, or there are parser/read errors such as stod issues.
---

# ABACUS + LibRPA Debug

Locate the failing stage first, then provide targeted fixes. Avoid broad blind modifications.

## Diagnosis Order

1. Identify failure stage: SCF / DF / NSCF / LibRPA.
2. Check whether inputs are mixed from different workflow chains.
3. Check stale-output contamination from previous runs.
4. Check missing or conflicting threshold parameters.

## Common Issues

- `stod` parse/read failure: check input formatting and stale files first.
- abnormal result jumps: check `nbands` against basis-size conventions.

## Output Format

- `symptom`
- `most_likely_root_cause`
- `minimal_fix_action`
- `validation_action`
