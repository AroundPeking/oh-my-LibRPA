# Direct mixed-Fourier strict-2D Coulomb reference

## Numerical construction

For auxiliary functions `P,Q` at in-plane momentum `q`, the direct route forms a quadrature Gram matrix

```text
V_PQ(q) ~= sum_n w_n F_P(q+G_parallel,kz_n) F_Q(q+G_parallel,kz_n)^*
```

where all quadrature weights are non-negative. The regular in-plane reciprocal lines use a transformed Gauss-Legendre `k_z` integration. The Gamma zero line is replaced by a positive in-plane cell quadrature constrained to reproduce the Massidda `1/q` cell average, and each Gamma-plane node receives the same transformed `k_z` treatment.

Because the result is a sum of positive outer products, it is Hermitian positive semidefinite up to floating-point roundoff. No negative eigenvalues are removed after construction.

## Difference from split Ewald

The established route combines real-space, reciprocal-space, Gaussian compensation and tail terms. It is efficient and accurate when all terms and meshes are well balanced. For diffuse or high-angular-momentum W auxiliary functions, individual contributions can be much larger than their final difference. Imperfect cancellation, radial interpolation, `ccp_rmesh_times`, cutoff or tail errors can then yield a strongly indefinite matrix.

The direct route evaluates one positive representation of the full operator and avoids that large-number subtraction. Its costs are more reciprocal samples, explicit `k_z` quadrature, dense Gram accumulation, and a new convergence burden in cutoff and two quadrature orders. It is not automatically superior for every material and remains default-off.

## Evidence hierarchy

Use, in order:

1. deterministic kernel and INPUT fail-closed tests;
2. exact reader-v1 headers, counts, dimensions and provenance;
3. Hermiticity and relative eigenvalue spectrum at every q;
4. cutoff and quadrature convergence of matrix norms and exchange;
5. fixed-index near-Fermi EXX bands versus an independent reference;
6. strict-2D head/wing GW with a fixed occupied/unoccupied manifold.

Positive matrices alone are not a physical acceptance result. The WS2 recovery required stable external ABFS/shrink, correct symmetry/BZ ordering, a producer-derived band, full-grid PyATB, and a finite near-Fermi GW comparison in addition to the direct matrix.
