# Server Profiles

Read this reference whenever `oh-my-librpa` routes a case to server execution.

The goal is to make runtime assumptions explicit before submission.

## Required questions

Before batch submission, confirm:

- which host/profile should be used
- whether VPN is required and already enabled
- whether connectivity/login should be tested now
- whether this is only a smoke run or a longer production run
- whether both ABACUS and LibRPA were built against the same latest LibRI with the nearest-fix bugfix, and whether the host has a site-specific LibRI root that should be recorded

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
- if the batch layout is `1 MPI rank/node`, the full node-core count for `--cpus-per-task` and `OMP_NUM_THREADS` unless the user explicitly requests an underfilled OpenMP layout
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

## 60.245 Slurm guardrails

- Keep large ABACUS/LibRPA work under `/work1/ghj/...`; `/public/home/ghj` has a small quota and should only hold source/build trees.
- Before blaming a rerun failure on memory, verify the exact ABACUS and LibRPA executable mtimes against the patched source files. A stale ABACUS binary can reproduce already-fixed RI/Coulomb map errors.
- For LibRPA GW Wc-heavy jobs on the Intel MPI + Intel MKL stack, do not set `MKL_NUM_THREADS=1` by default. The Wc stage uses MKL/ScaLAPACK/PBLAS heavily, so a 1-rank-per-node job should normally use `MKL_NUM_THREADS=$SLURM_CPUS_PER_TASK`, `MKL_DYNAMIC=FALSE`, `OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK`, `OMP_PLACES=cores`, and explicit rank binding. If testing thread behavior, enable `MKL_VERBOSE=1` on a short C256/C512 run and confirm `NThr` is not 1.
- If the user explicitly asks to avoid `srun`, do not rely on Intel MPI's Slurm bootstrap default. Use explicit SSH bootstrap, for example:

```bash
mpirun -bootstrap ssh -f "$HOSTFILE" -ppn "$RANKS_PER_NODE" -np "$NRANKS" "$EXEC"
```

- On the current 60.245 Intel MPI 2021.3 environment, an `mpirun -bootstrap ssh` job may fail during `MPI_Init` with `ib_iface.c:674 Assertion gid->global.interface_id != 0`. First run a two-node MPI smoke test; if the default provider fails and TCP succeeds, set:

```bash
export I_MPI_HYDRA_BOOTSTRAP=ssh
export I_MPI_HYDRA_BOOTSTRAP_EXEC=ssh
export I_MPI_JOB_RESPECT_PROCESS_PLACEMENT=0
export FI_PROVIDER=tcp
export I_MPI_OFI_PROVIDER=tcp
export UCX_TLS=tcp,self
```

- Treat the TCP provider setting as a 60.245 runtime workaround, not as a universal cluster default.

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
