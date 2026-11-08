# Periodic-Solid Runtime Lane

## Production Input

Use FD8 and analytic q-average head/wing for formal solid results. For a solid with `nfreq = F` and `G` k-point groups, prefer:

```text
sternheimer_fd_order              8
sternheimer_nfreq                 F
sternheimer_frequency_mpi         1
sternheimer_channel_mpi           0
sternheimer_mpi_layout            frequency_grouped
kpar                              G
```

Submit exactly `NPROC = F * G`. The code requires this equality for nested frequency/k-point MPI. Keep every rank in the same real-space pool. Start with `G=1` only for cheap coarse grids; use a measured `G=4` or `G=8` lane for fine grids when memory and node cores allow it.

Example for `nfreq=12`, `G=4`: 48 MPI ranks. On the selected available host, probe the actual cores, memory and allocation limits before choosing ranks per node and OpenMP width. Compare a full-width one-rank-per-node layout with a node-saving layout only when both fit the allocation and memory limits. Default new work to DF and run `sbatch --test-only`; do not transfer node shapes between servers. Server 66 remains limited to 10 nodes per job.

If k-point grouping is unavailable, use channel MPI with a rank count that is an integer multiple of `nfreq`:

```text
sternheimer_frequency_mpi         1
sternheimer_channel_mpi           1
sternheimer_mpi_layout            frequency_grouped
```

Use `global_equation` for a solid only after a one-q physical A/B gate.

## Pilot And Gate

Use the finest planned grid and a historically slow canonical q. Wait until every rank completes at least one k pair, then run:

```bash
estimate_sternheimer_runtime.py RUN_DIR \
  --global-kpoints 64 \
  --kpoint-groups G \
  --startup-minutes SCF_MINUTES \
  --safety-factor 1.25
```

The estimator infers equations per k pair from progress records. Use its conservative maximum, not the mean. Require at most 18 hours before releasing the complete canonical-q array. Also measure SCF/Coulomb setup, response-file writing, manifest assembly, and shutdown; equation completion alone is not the whole-job wall time.

Keep these physical settings unchanged while tuning resources: explicit actual grid, Ecut, FD8, k/q mesh, GreenX file, PCA, rmesh, full Coulomb, q=0, solver tolerance, and analytic head/wing. MPI layout changes performance, not the energy definition, but still requires the A/B gate.
