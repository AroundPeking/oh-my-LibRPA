---
name: librpa-openmp-mkl-threading
description: Use when preparing, submitting, or diagnosing LibRPA jobs whose performance depends on OpenMP and threaded MKL, especially one-MPI-rank-per-node jobs, dense ScaLAPACK/BLAS stages, Wc symmetry restoration, q-to-R transforms, or unexpectedly low CPU utilization.
---

# LibRPA OpenMP and MKL Threading

Keep the MPI layout, OpenMP team, and MKL team explicit. Do not inherit FHI-aims or ABACUS producer settings without checking the LibRPA stage.

This guard applies to LibRPA regardless of whether the producer is ABACUS or FHI-aims. Treat producer and LibRPA resource environments as separate stages.

## One Rank per Node

For a LibRPA production job with one MPI rank per node and all node cores assigned to that rank, use:

```bash
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:?}"
export MKL_NUM_THREADS="$OMP_NUM_THREADS"
export MKL_DYNAMIC=FALSE
export OMP_MAX_ACTIVE_LEVELS=1
export OMP_PLACES=cores
export OMP_PROC_BIND=close
```

Use `OMP_MAX_ACTIVE_LEVELS=1` unless a source-backed test requires nested teams. This allows explicit OpenMP regions and threaded MKL kernels to use the node without permitting a 96 by 96 nested oversubscription.

## Hard Guards

Before submission:

1. Verify `--ntasks-per-node=1` and `--cpus-per-task` equals the physical cores intended for the rank.
2. Require `OMP_NUM_THREADS == MKL_NUM_THREADS == SLURM_CPUS_PER_TASK` for the one-rank-per-node layout.
3. Record MPI ranks, OpenMP threads, MKL threads, `MKL_DYNAMIC`, and `OMP_MAX_ACTIVE_LEVELS` in the immutable submission receipt and runtime provenance.
4. Run the case's numerical/static validator and `sbatch --test-only` before the single real submission.
5. Preserve an existing run and its receipts. Use a new sibling run directory for an authorized resource correction.

Do not set `MKL_NUM_THREADS=1` by default for a one-rank-per-node LibRPA job. It serializes dense BLAS and ScaLAPACK kernels used by stages such as Wc symmetry restoration and q-to-R transforms.

## When MKL May Be Smaller

Use fewer MKL threads only when the rank layout or a measured source path justifies it. Examples include several MPI ranks sharing one node or MKL calls made inside an already active OpenMP team. Record the reason and show a same-input timing or utilization measurement. Never carry `MKL_NUM_THREADS=1` forward as an unexplained template default.

## Runtime Gate

After the job enters a dense BLAS/MKL-heavy stage, sample a representative rank and the whole allocation. Treat persistently low utilization as a resource-layout failure, not proof that the job is merely slow. Stop and diagnose before another production submission if the requested cores are not being used.
