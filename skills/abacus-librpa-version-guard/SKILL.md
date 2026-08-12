---
name: abacus-librpa-version-guard
description: Use when preparing, submitting, auditing, debugging, or interpreting ABACUS+LibRPA calculations against the pinned OML ABACUS master_ghj, LibRPA v0.7.0, and PyATB enable_head_wing profile.
---

# ABACUS+LibRPA Version Guard

Use this as a preflight gate before any ABACUS+LibRPA calculation or before trusting an existing result. Real compute happens on a server. Resolve the active revisions with the OML MCP `inspect_profile` tool, then compare server source revisions with that profile before submission or interpretation.

The pinned profile is:

- ABACUS `master_ghj`: `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e`
- LibRPA `v0.7.0`: `dd169fa11fa920d580d4f39dc11e218a7f17f7b5`
- PyATB `enable_head_wing`: `9fb9028c59b1dbaf9cf66965280961fc2225d9eb`

## Hard Gates

1. Do not run full ABACUS+LibRPA physics calculations on the local laptop. Local work is limited to editing, staging, static checks, parsing, plotting, and tiny non-physics smoke commands. If the user explicitly asks for local compute, pause and confirm it as an exception.
2. Before queue submission, restart, or result interpretation, verify ABACUS and LibRPA revisions. For head/wing workflows, verify PyATB as well.
3. Treat the MCP profile as the normal baseline. A server executable built from a different branch or commit is not acceptable just because it runs.
4. If a feature branch is intentionally being tested, record the branch name, commit SHA, reason, and which parameter conventions belong to that branch.
5. If versions cannot be proven, do not silently continue. Either rebuild/sync on the server, or ask whether the user wants an explicit old-version exception.

## What To Check

For each run, record:

- server host, run directory, and scheduler job id if submitted
- absolute `ABACUS` and `LIBRPA` executable paths
- `stat` timestamp/size for both executables
- source repository path used to build each executable, if available
- ABACUS branch and `HEAD` SHA on the server
- LibRPA branch and `HEAD` SHA on the server
- pinned ABACUS, LibRPA, and PyATB SHAs returned by `inspect_profile`
- PyATB source revision and adapter revision when head/wing data is used
- whether server SHAs match the pinned profile, or the explicit exception reason

Prefer source-tree SHAs over binary timestamps. If only `stat` output is available, state that it is weak evidence and do not treat the binary as current.

## Minimal Command Pattern

Adjust paths to the active machine, but keep the same evidence shape.

Local reference:

```bash
git -C /Users/ghj/code/merge/abacus-develop status --short --branch
git -C /Users/ghj/code/merge/abacus-develop rev-parse master_ghj
git -C /Users/ghj/code/merge/abacus-develop log -1 --oneline master_ghj

git -C /Users/ghj/code/LibRPA status --short --branch
git -C /Users/ghj/code/LibRPA rev-parse 'v0.7.0^{commit}'
git -C /Users/ghj/code/LibRPA log -1 --oneline 'v0.7.0^{commit}'

git -C "$PYATB_SRC" status --short --branch
git -C "$PYATB_SRC" rev-parse enable_head_wing
git -C "$PYATB_SRC" log -1 --oneline enable_head_wing
```

Server executable and source evidence:

```bash
readlink -f "$ABACUS" "$LIBRPA"
stat -c '%y %s %n' "$ABACUS" "$LIBRPA"
git -C "$ABACUS_SRC" status --short --branch
git -C "$ABACUS_SRC" rev-parse HEAD
git -C "$ABACUS_SRC" log -1 --oneline
git -C "$LIBRPA_SRC" status --short --branch
git -C "$LIBRPA_SRC" rev-parse HEAD
git -C "$LIBRPA_SRC" log -1 --oneline
```

If the executable path does not reveal the source directory, search nearby build metadata and scripts, then report uncertainty instead of guessing:

```bash
dirname "$(readlink -f "$ABACUS")"
dirname "$(readlink -f "$LIBRPA")"
find "$(dirname "$(readlink -f "$ABACUS")")" -maxdepth 4 -name .git -type d 2>/dev/null
find "$(dirname "$(readlink -f "$LIBRPA")")" -maxdepth 4 -name .git -type d 2>/dev/null
```

## Version Decision Rules

Use this table before submitting or trusting a run:

| Situation | Action |
|---|---|
| Server ABACUS and LibRPA match the pinned profile | Proceed after recording evidence. |
| Head/wing route also matches pinned PyATB | Proceed after validating the adapter output. |
| One side is older or unknown | Stop; rebuild/sync before running. |
| Both sides are older but the user asked to reproduce an old result | Proceed only after labeling it as an old-version reproduction. |
| A named feature branch is under development | Proceed only with branch name, SHA, and reason recorded. |
| Existing result has no source/version evidence | Treat as untrusted for parameter-sensitive conclusions. |

Do not "fix" input parameter errors by guessing compatibility with another binary. First determine whether the binary differs from the pinned profile; reader-v1, shrink, symmetry, PyATB, and head/wing behavior is version-sensitive.

## Output Requirement

Before any real run, include a compact version block:

```text
Execution: server=<host>, local_compute=no
Profile: abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08
ABACUS pinned master_ghj: 3efad9ed5ca066aee1d1b2214e43f92a2d2a567e
LibRPA pinned v0.7.0: dd169fa11fa920d580d4f39dc11e218a7f17f7b5
PyATB pinned enable_head_wing: 9fb9028c59b1dbaf9cf66965280961fc2225d9eb
ABACUS server build: <branch> <sha> <path>
LibRPA server build: <branch> <sha> <path>
PyATB server source: <branch> <sha> <path-or-not-used>
Version verdict: match | mismatch | feature-branch exception | unknown-blocked
Next action: submit | rebuild | ask for exception | inspect build provenance
```

If reporting a finished calculation, include the same block or explicitly say the result is not version-verified.
