---
name: abacus-librpa-version-guard
description: Use when preparing, submitting, auditing, debugging, or interpreting ABACUS+LibRPA calculations, especially when a run might execute locally, use stale ABACUS/LibRPA binaries, use old master_ghj parameters, or run on a feature branch instead of the current local master_ghj baseline.
---

# ABACUS+LibRPA Version Guard

Use this as a preflight gate before any ABACUS+LibRPA calculation or before trusting an existing result. The default rule is: real ABACUS+LibRPA compute happens on a server, and the ABACUS/LibRPA executables must be checked against the latest local `master_ghj` baseline before submission or interpretation.

## Hard Gates

1. Do not run full ABACUS+LibRPA physics calculations on the local laptop. Local work is limited to editing, staging, static checks, parsing, plotting, and tiny non-physics smoke commands. If the user explicitly asks for local compute, pause and confirm it as an exception.
2. Before queue submission, restart, or result interpretation, verify both ABACUS and LibRPA commit versions.
3. Treat local `master_ghj` as the normal baseline for broad system tests. A server executable built from an older branch or old commit is not acceptable just because it runs.
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
- local ABACUS `master_ghj` SHA and local LibRPA `master_ghj` SHA
- whether server SHAs match local `master_ghj`, or the explicit exception reason

Prefer source-tree SHAs over binary timestamps. If only `stat` output is available, state that it is weak evidence and do not treat the binary as current.

## Minimal Command Pattern

Adjust paths to the active machine, but keep the same evidence shape.

Local reference:

```bash
git -C /Users/ghj/code/merge/abacus-develop status --short --branch
git -C /Users/ghj/code/merge/abacus-develop rev-parse master_ghj
git -C /Users/ghj/code/merge/abacus-develop log -1 --oneline master_ghj

git -C /Users/ghj/code/LibRPA status --short --branch
git -C /Users/ghj/code/LibRPA rev-parse master_ghj
git -C /Users/ghj/code/LibRPA log -1 --oneline master_ghj
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
| Server ABACUS and LibRPA match local `master_ghj` | Proceed after recording evidence. |
| One side is older or unknown | Stop; rebuild/sync before running. |
| Both sides are older but the user asked to reproduce an old result | Proceed only after labeling it as an old-version reproduction. |
| A named feature branch is under development | Proceed only with branch name, SHA, and reason recorded. |
| Existing result has no source/version evidence | Treat as untrusted for parameter-sensitive conclusions. |

Do not "fix" input parameter errors by guessing compatibility with an old binary. First determine whether the binary is stale; many reader-v1, shrink, symmetry, PyATB, and head/wing parameters depend on current `master_ghj` behavior.

## Output Requirement

Before any real run, include a compact version block:

```text
Execution: server=<host>, local_compute=no
ABACUS local master_ghj: <sha> <subject>
LibRPA local master_ghj: <sha> <subject>
ABACUS server build: <branch> <sha> <path>
LibRPA server build: <branch> <sha> <path>
Version verdict: match | mismatch | feature-branch exception | unknown-blocked
Next action: submit | rebuild | ask for exception | inspect build provenance
```

If reporting a finished calculation, include the same block or explicitly say the result is not version-verified.
