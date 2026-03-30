# PR #1 Merge Review

This note is for the author of PR #1.

Goal: keep the new `FHI-aims -> LibRPA` support additive, without changing the current `ABACUS -> LibRPA` behavior unless the user clearly provides stronger FHI-aims ownership signals.

## Summary

The PR is close to merge-safe from an installation and script-execution perspective:

- it does not change the existing workflow shell scripts
- it does not change the template execution chain
- the current self-test still passes on the PR branch

The remaining merge blockers are prompt and routing regressions. These live in the new stack-layer skills and their supporting docs.

## Blocking Issues

### 1. `geometry.in` is treated as an FHI-aims ownership marker

This is too broad.

In the current repository:

- `geometry.in` is already grouped with general structure files in `scripts/intake_preflight.sh`
- `geometry.in` already appears in the ABACUS GW skill as part of a canonical example bundle
- `templates/abacus-librpa-gw/template/plot_compare.py` reads `geometry.in` for postprocessing

That means `geometry.in` is not an FHI-aims-only signal.

If the router treats `geometry.in` alone as enough to switch into the new FHI-aims layer, existing ABACUS-side bundles can be misrouted.

Required change:

- keep `geometry.in` as a supporting marker only
- require stronger FHI-aims ownership markers before routing into `skills/oh-my-librpa-fhi-aims-qsgw/`

Strong FHI-aims markers should be things like:

- `control.in`
- `run_librpa_gw_aims_iophr.sh`
- explicit task names such as `qsgw_band`, `qsgw_band0`, `qsgw`, `qsgwa`
- explicit user intent that the case is an FHI-aims workflow

Supporting markers that should not claim ownership on their own:

- `geometry.in`
- `librpa.d/`
- `self_energy/`

Files to update:

- `skills/oh-my-librpa/SKILL.md`
- `skills/oh-my-librpa-fhi-aims-qsgw/SKILL.md`
- `docs/guide/fhi-aims-librpa-qsgw.md`

### 2. The top-level router still routes by `GW/RPA/Debug` before stack ownership

The new PR introduces a stack-layer split:

- `ABACUS -> LibRPA`
- `FHI-aims -> LibRPA`

But the top-level `skills/oh-my-librpa/SKILL.md` still instructs the agent to:

1. classify `GW/RPA/Debug`
2. route into `references/gw-route.md`, `references/rpa-route.md`, `references/debug-route.md`
3. only later route through stack-layer skills

This is internally inconsistent.

Required change:

- decide upstream stack ownership first
- if the case belongs to `ABACUS -> LibRPA`, then continue into the existing `GW/RPA/Debug` references
- if the case belongs to `FHI-aims -> LibRPA`, keep it in the FHI-aims layer and do not reuse ABACUS input assumptions

Files to update:

- `skills/oh-my-librpa/SKILL.md`
- `docs/guide/installation.md`
- `docs/guide/fhi-aims-librpa-qsgw.md`

### 3. The FHI-aims fallback trigger is too vague

The current PR includes wording such as:

- `existing non-ABACUS case`

This is not a safe routing condition.

It can catch partially copied bundles, mixed bundles, or audit/debug cases that still belong to the ABACUS path.

Required change:

- remove vague catch-all ownership phrases
- replace them with explicit ownership rules
- if ownership is mixed or unclear, stop and ask which upstream stack owns the source of truth

Files to update:

- `skills/oh-my-librpa/SKILL.md`
- `skills/oh-my-librpa-abacus-librpa/SKILL.md`
- `skills/oh-my-librpa-fhi-aims-qsgw/SKILL.md`

### 4. The self-test does not cover the new stack-layer assets

The PR adds:

- `skills/oh-my-librpa-abacus-librpa/SKILL.md`
- `skills/oh-my-librpa-fhi-aims-qsgw/SKILL.md`
- `docs/guide/fhi-aims-librpa-qsgw.md`

But the current `scripts/self_test.sh` still validates only the original skill set.

Required change:

- add existence checks for the two new skills and the new guide
- add at least one simple content regression check proving that weak markers such as `geometry.in` do not claim FHI-aims ownership on their own

File to update:

- `scripts/self_test.sh`

## Suggested Ownership Contract

The safest contract is:

1. Top-level router asks for files first.
2. Top-level router decides upstream stack ownership first.
3. `ABACUS -> LibRPA` markers win when ABACUS canonical inputs are present:
   - `INPUT*`
   - `KPT*`
   - `STRU`
   - `.orb`
   - `.abfs`
   - `.upf`
   - `OUT.ABACUS/`
   - ABACUS logs
4. `FHI-aims -> LibRPA` activates only when stronger FHI-aims signals are present:
   - `control.in`
   - `run_librpa_gw_aims_iophr.sh`
   - explicit FHI-aims user intent
   - explicit `qsgw_band` / `qsgw_band0` / `qsgw` / `qsgwa`
5. `geometry.in`, `librpa.d/`, and `self_energy/` are supporting markers only.
6. Mixed bundles must stop and ask which upstream stack owns the source of truth.
7. Only after `ABACUS -> LibRPA` ownership is established should the workflow continue into `GW`, `RPA`, or `Debug`.

## Acceptance Criteria

The PR is merge-safe when all of the following are true:

- `geometry.in` alone does not route a case into the FHI-aims skill
- the top-level router decides stack ownership before deeper `GW/RPA/Debug` routing
- vague routing language like `existing non-ABACUS case` is removed
- mixed bundles explicitly stop for clarification
- the new skills and new guide are covered by `scripts/self_test.sh`
- the existing self-test still passes without changing the current script execution flow

## Verification

Run:

```bash
bash scripts/self_test.sh --workspace "$PWD" --installed-root "$PWD"
```

Expected result:

- all checks pass
- no new failures in the existing ABACUS workflow checks
- added checks confirm that weak markers do not steal ABACUS-owned cases

## Scope Reminder

This review is only about merge safety and preserving existing behavior.

It does not block the addition of FHI-aims support itself. The FHI-aims layer is welcome, but its routing must be explicit enough that current ABACUS users do not get sent into the wrong skill tree.
