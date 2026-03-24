# Server Profiles

Read this reference whenever `oh-my-librpa` routes a case to server execution.

The goal is to make runtime assumptions explicit before submission.

## Required questions

Before batch submission, confirm:

- which host/profile should be used
- whether VPN is required and already enabled
- whether connectivity/login should be tested now
- whether this is only a smoke run or a longer production run

## Runtime materialization rule

Do not rely on implicit login-shell luck.
If a host expects `~/.bashrc`, conda activation, or site init scripts, materialize those steps explicitly in `env.sh`.

Materialize explicit runtime configuration before submission:

- use `scripts/materialize_server_profile.sh --case-dir <case_dir> --profile <name-or-path>` to write `env.sh`
- if launcher / `python3` / PATH behavior is uncertain on compute nodes, use `scripts/materialize_batch_probe.sh --case-dir <case_dir> --profile <name-or-path>` before the real job

Prefer explicit values for:

- `python3_exec`
- `abacus_work`
- `librpa_work`
- MPI launcher path and flags
- `.bashrc` / conda activation steps when the host depends on them
- scheduler directives that affect node shape or environment loading

If a site depends on shell init or conda activation, keep the tracked profile generic and prefer one of these patterns:

- use placeholders inside `registry/host-profiles/*.env`
- or keep the real host profile outside the repository and pass it via `--profile /absolute/path/to/private.env`

A common pattern is:

- source `$HOME/.bashrc`
- activate the required conda environment
- point `OH_MY_LIBRPA_PYTHON3_EXEC` at that environment's Python explicitly

## DF batch guardrails

- On `df_iopcas_ghj`, do not assume the interactive SSH rule (`source ~/.bashrc`) is safe inside Slurm batch jobs.
- If a batch job exits before the first workload log line, classify it as a bootstrap failure first; suspect `.bashrc`, conda hooks, or site init scripts before blaming ABACUS or LibRPA.
- For a new `df` batch workflow, start with a minimal payload:
  - `set -euxo pipefail`
  - `pwd`
  - `ls -1A`
  - the direct workload command
- Only add `.bashrc`, `conda`, `setvars.sh`, or MPI launcher wrappers after each one is justified by a successful probe on the compute node.
- Before sourcing site init scripts, run `ldd` on the target executable. If runtime libraries already resolve, skip extra init.
- For single-rank ABACUS smoke runs, prefer direct binary execution over `mpirun -np 1`.

## Submission discipline

- always use a fresh isolated run directory
- never overwrite the user's original data directory
- test connectivity first if the profile or VPN state is unclear
- for expensive jobs, confirm server and resource choice before submission
- if login fails, report the exact failure class: `timeout`, `auth`, `host resolution`, or equivalent

## Minimal status update format

When reporting server-side progress, keep it operational:

- what profile/host was selected
- what was validated successfully
- what failed, if anything
- what the next low-risk action is
