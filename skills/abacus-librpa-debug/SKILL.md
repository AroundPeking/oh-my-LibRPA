---
name: abacus-librpa-debug
description: Diagnose ABACUS + LibRPA RPA/GW failures from logs and inputs. Use when runs fail, outputs are inconsistent, or there are parser/read errors such as stod issues.
---

# ABACUS + LibRPA Debug

Before treating an ABACUS+LibRPA failure as a physics/input issue, apply `skills/abacus-librpa-version-guard/` when execution provenance matters. Mismatched binaries can reject or misread pinned parameters, so check server source revisions against the MCP profile before redesigning inputs.

Locate the failing stage first, then provide targeted fixes. Avoid broad blind modifications.

## Diagnosis Order

1. Identify failure stage: SCF / DF / NSCF / LibRPA.
2. Check whether the run used current, version-verified ABACUS/LibRPA executables or an explicit branch/reproduction exception.
3. Check whether inputs are mixed from different workflow chains.
4. Check stale-output contamination from previous runs.
5. Check missing or conflicting threshold parameters.

## Common Issues

- `stod` parse/read failure: check input formatting and stale files first.
- abnormal result jumps: check `nbands` against basis-size conventions.

## Output Format

- `symptom`
- `most_likely_root_cause`
- `minimal_fix_action`
- `validation_action`
- call the installed `report_stage.sh` helper to update both task Markdown logs and send the user a short stage summary
