# Server Profiles

Read this reference whenever `oh-my-librpa` routes a case to server execution.

The goal is to make runtime assumptions explicit before submission.

## Required questions

Before batch submission, confirm:

- which host/profile should be used
- whether VPN is required and already enabled
- whether connectivity/login should be tested now
- whether this is only a smoke run or a longer production run
- whether both ABACUS and LibRPA were built against current `abacusmodeling/LibRI` and `abacusmodeling/LibComm` branch `fix_status`, and whether the host has site-specific dependency roots that should be recorded

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
- `libri_root` when the host has a known site-specific LibRI tree
- MPI launcher path and flags
- `.bashrc` / conda activation steps when the host depends on them
- scheduler directives that affect node shape or environment loading
- target partition resources discovered from the current server, not copied from another host or older queue

If a site depends on shell init or conda activation, keep the tracked profile generic and prefer one of these patterns:

- use placeholders inside `registry/host-profiles/*.env`
- or keep the real host profile outside the repository and pass it via `--profile /absolute/path/to/private.env`

A common pattern is:

- source `$HOME/.bashrc`
- activate the required conda environment
- point `OH_MY_LIBRPA_PYTHON3_EXEC` at that environment's Python explicitly

## DF batch guardrails

- On `df_iopcas_ghj`, do not assume the interactive SSH rule (`source ~/.bashrc`) is safe inside Slurm batch jobs.
- On `df_iopcas_ghj`, ask the user which current LibRI root their ABACUS/LibRPA builds use instead of assuming one fixed path.
- If a batch job exits before the first workload log line, classify it as a bootstrap failure first; suspect `.bashrc`, conda hooks, or site init scripts before blaming ABACUS or LibRPA.
- For a new `df` batch workflow, start with a minimal payload:
  - `set -euxo pipefail`
  - `pwd`
  - `ls -1A`
  - the direct workload command
- Only add `.bashrc`, `conda`, `setvars.sh`, or MPI launcher wrappers after each one is justified by a successful probe on the compute node.
- Before sourcing site init scripts, run `ldd` on the target executable. If runtime libraries already resolve, skip extra init.
- For single-rank ABACUS smoke runs, prefer direct binary execution over `mpirun -np 1`.
- Before submitting to a specific Slurm partition, query the live node shape and use those values in the script and preflight checks. Useful probes include:
  - `sinfo -p <partition> -o "%P %D %c %m %N"`
  - `scontrol show node <node> | grep -E "CPUTot|RealMemory|Partitions"`
- For `1 MPI rank/node` ABACUS jobs, set `--cpus-per-task` and `OMP_NUM_THREADS` to the discovered per-node core count unless the user explicitly requests an underfilled layout.
- Set `--mem` to the discovered per-node `RealMemory` value in MB. Do not use `--mem=0`.
- Example, not a global default: if the target `df` partition is `9242` and the live probe shows 96 cores plus `RealMemory=380000`, then use `--cpus-per-task=96`, `OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK`, and `--mem=380000` for that partition.

Run the resource preflight with the discovered facts before submission:

```bash
scripts/intake_preflight.sh <case_dir> --compute-location server --ssh-target df_iopcas_ghj \
  --target-partition <partition> --target-nodes <nodes> \
  --expected-ntasks-per-node 1 --node-cores <CPUTot> --node-memory-mb <RealMemory>
```

## Submission discipline

- always use a fresh isolated run directory
- never overwrite the user's original data directory
- test connectivity first if the profile or VPN state is unclear
- for expensive jobs, confirm server and resource choice before submission
- for any server where the LibRI provenance is unclear, stop and ask before submission; do not assume the df path applies elsewhere
- if login fails, report the exact failure class: `timeout`, `auth`, `host resolution`, or equivalent

## Minimal status update format

When reporting server-side progress, keep it operational:

- what profile/host was selected
- what was validated successfully
- what failed, if anything
- what the next low-risk action is
