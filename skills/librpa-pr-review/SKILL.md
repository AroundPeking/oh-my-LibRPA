---
name: librpa-pr-review
description: "Use when preparing, reviewing, revising, or comparing LibRPA pull requests against AESM-Group/LibRPA master and AroundPeking/LibRPA master_ghj. Covers approval gates, public PR wording, private validation evidence, and thirdparty exclusions."
agent_created: true
---

# LibRPA PR review

## Scope and approval

- Use this skill for LibRPA upstream-port PR planning, title/body drafts, PR review, and post-merge comparison. Keep the public PR text separate from the private scientific/software verification record.
- Do not automatically commit, push, open, update, close, reopen, or merge a PR. First show the concrete old and new behavior, purpose, source, affected cases, and evidence limits; obtain the user's explicit approval for each specific action. A request to prepare, continue, or catch up is not authorization for a Git action.
- Do not modify anything under `thirdparty/` in LibRPA, including LibComm, GreenX, or LibRI; do not modify thirdparty files even in remote validation scratch trees. Do not revive, repackage, or silently revert a withdrawn LibComm change. Treat excluded thirdparty differences as permitted scope exclusions, not unfinished migrations.
- Preserve unrelated branches, uncommitted changes, and existing upstream behavior. Do not force-push or rewrite history without explicit, action-specific permission.

## Establish the comparison

1. Read the current upstream `master` and remote `master_ghj` tips and the actual PR state. Do not substitute an older local tracking branch for the remote tip. Distinguish open, closed-unmerged, and merged PRs; unmerged content is not part of upstream `master`.
2. Compare behavior at the function, caller, input-contract, and numerical-result levels. A commit count, patch-id, symbol occurrence, or file diff alone does not prove that a function is missing or present. Preserve upstream's own fixes rather than seeking byte-for-byte identity with `master_ghj`.
3. Identify the condition that triggers the old behavior, the new behavior, whose result changes, and what is unchanged. Separate input/output formatting, scientific algorithms, symmetry routes, MPI ownership, and test-only changes. For ABACUS handoffs inspect producer and reader contracts together.
4. Maintain a private evidence record for tests, fixed-input A/B, ranks, assertion effectiveness, references/tolerances, versions and limitations. Do not call a synthetic fixture a physical-material result or a green CI check scientific acceptance. Report untested paths frankly to the user.

## Public title and body

- Keep the title short and behavior-focused. Avoid claiming a broad correctness or performance gain from a narrow test.
- Draft the body in English with `### Problem` and `### Change`. Explain the failure condition, minimal change, preserved behavior, and necessary scope boundary. Avoid a separate `Validation`, `Tests`, or run-receipt section.
- Never include the user's local paths, account names, worktrees, private machine/server names (especially df), hostnames, remote directories, job identifiers, executable paths, build commands, internal resource details, or personal documents in the public title/body. Do not copy private evidence verbatim into the PR.
- Do not cite an unverified future outcome as achieved. Do not treat an open PR as merged.
- Show the exact draft title/body to the user for review before any GitHub update. Keep private verification details in the conversation or a private review artifact, not the public PR description.

## Minimal public body pattern

```markdown
### Problem
Describe the observable old behavior and when it occurs.

### Change
Describe the new behavior, the preserved path, and the relevant boundary.
```

## After review

- If approval is only to draft or review, stop there. If a specific Git action is separately approved, check the exact repository, branch, diff, PR target, and approved scope immediately before that action.
- After a merge, reread upstream `master` and compare the merged behavior with the current remote `master_ghj`. Do not infer functional completion from original commit ancestry or the number of remaining commits.
