# Molecular And Atomic Runtime Lane

## Production Input

Use the molecule/atom convergence skill for boxes, occupations, PCA, frequencies, and Coulomb settings. The efficient response layout is:

```text
sternheimer_fd_order              8
sternheimer_frequency_mpi         1
sternheimer_channel_mpi           1
sternheimer_mpi_layout            global_equation
exx_ccp_rmesh_times               1
rpa_ccp_rmesh_times               1
```

Do not enable periodic analytic head/wing for a Gamma-only molecule or atom.

## Resource Choice

- `global_equation` distributes occupied-state/frequency/auxiliary-channel equations over all ranks and avoids open-shell atom tail imbalance.
- Start with one MPI rank per node when one response equation is memory-heavy. Fill that rank with physical OpenMP cores.
- Increase MPI ranks from measured equation throughput; ranks need not equal `nfreq` in `global_equation` mode.
- Use multiple ranks per node only after measuring per-rank peak memory and respecting the node core count. Set `ranks_per_node * cpus_per_task` no larger than available physical cores.
- Keep the molecule and atoms as separate resource estimates. A small atom may need fewer nodes but can have worse load imbalance.

## Pilot And Gate

Pilot the largest accepted box and finest planned grid with the actual `naux`, spin, occupations, FD8, and frequency file. Use the total expected equation count from the producer/report with the runtime estimator:

```bash
estimate_sternheimer_runtime.py RUN_DIR \
  --total-equations EXPECTED_TOTAL \
  --startup-minutes SCF_MINUTES \
  --safety-factor 1.25
```

If the projection exceeds 18 hours, add ranks while retaining `global_equation`; do not enlarge the wall time and hope the tail completes.

