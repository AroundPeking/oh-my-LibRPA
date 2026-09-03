# Periodic 3D GW Current-Stack Benchmark Design

## Goal

Replay the smallest ABACUS-to-LibRPA periodic GW path with the current pinned
stack and freeze enough evidence to distinguish serialization, consumer,
parallel-reproducibility, degenerate-state, and scientific-convergence gates.

## Acceptance Model

The benchmark has independent verdicts:

1. current ABACUS SCF, NSCF, and preprocessing must complete;
2. reader-v1 dimensions and symmetry embedded in `stru_out` must pass without
   legacy sidecars;
3. current LibRPA must reproduce its official frozen input and regular-grid QP
   reference within the declared tolerance;
4. independent MPI/OpenMP layouts must reproduce current end-to-end output;
5. a historical band reference with a different degenerate gauge blocks
   statewise comparison instead of being silently averaged or accepted;
6. the small regression cannot satisfy scientific convergence or promotion.

## Evolution Rule

A later benchmark may clear the degenerate-gauge block only with a controlled
unitary-rotation fixture and a gauge-invariant observable or explicit
degenerate-subspace self-energy treatment. It must then pass frequency,
screening-grid, NAO, and ABFS convergence on one definition-matched candidate.
