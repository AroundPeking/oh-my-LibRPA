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

- use `oh-my-librpa/scripts/materialize_server_profile.sh --case-dir <case_dir> --profile <name-or-path>` to write `env.sh`
- if launcher / `python3` / PATH behavior is uncertain on compute nodes, use `oh-my-librpa/scripts/materialize_batch_probe.sh --case-dir <case_dir> --profile <name-or-path>` before the real job

Prefer explicit values for:

- `python3_exec`
- `abacus_work`
- `librpa_work`
- MPI launcher path and flags
- `.bashrc` / conda activation steps when the host depends on them
- scheduler directives that affect node shape or environment loading

For fisherd, the current house rule is:

- source `~/.bashrc`
- use Python from the `ghj_main` environment

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