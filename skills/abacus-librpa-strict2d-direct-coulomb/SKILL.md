---
name: abacus-librpa-strict2d-direct-coulomb
description: Use when a strict-2D ABACUS+LibRPA full-Ewald auxiliary Coulomb matrix is strongly indefinite, cutoff-sensitive, or gives abnormal EXX/GW bands, and the opt-in direct_mixed_fourier positive-Gram output must be prepared, converged, validated, or compared with the established Ewald route. Covers input switches, convergence order, reader-v1 and PSD gates, WS2 starting values, and the boundary that cut Coulomb is diagnostic-only.
---

# ABACUS + LibRPA strict-2D direct Coulomb

Use this skill together with `abacus-librpa-strict2d-ewald-headwing`. It changes only how ABACUS writes the **full** strict-2D auxiliary Coulomb matrix; it does not replace the PyATB head/wing or LibRPA GW gates.

## Decide whether to use it

Keep the default `ewald` route when the same-definition full matrix is Hermitian to roundoff, has only harmless relative roundoff-scale negative eigenvalues, is stable against `ccp_rmesh_times` and cutoff controls, and gives continuous physical EXX bands.

Use `direct_mixed_fourier` as an explicit opt-in when all of the following hold:

1. The calculation is an isolated 2D material using full Coulomb and `exx_ewald_dimension 2`.
2. The legacy Ewald matrix is strongly indefinite or unstable, or the full-Coulomb EXX band is abnormal while a cut-Coulomb diagnostic is ordinary.
3. PP, NAO, ABFS, geometry, k/q mesh, symmetry and reader-v1 ordering are frozen so that the Coulomb construction is the only causal variable.

Do not use eigenvalue clipping, smooth inverse, or cut Coulomb to turn a failed production result into a pass. Direct output cannot repair bad ABFS, large Cs, wrong q-star labels, an inconsistent band payload, or a broken head/wing definition.

## Prepare the ABACUS input

Require a verified `master_ghj` executable containing the direct switch. Record its commit and SHA256. Add:

```text
rpa                                  1
out_librpa_reader_version            1
exx_ewald_dimension                  2
out_librpa_2d_coulomb_method         direct_mixed_fourier
out_librpa_2d_direct_ecut            110
out_librpa_2d_direct_kz_order        64
out_librpa_2d_direct_gamma_order     8
```

`110 Ry`, `64`, and `8` are the accepted no-SOC WS2 starting point, not universal converged values. The Gamma order must be positive and even. Unset old experimental `ABACUS_DIRECT_GSUM_*` environment variables; the INPUT must be the sole route selector.

The implementation returns before the legacy split-Ewald full-matrix assembly. It writes `v1_coulomb_full_iq_*`, `direct_2d_coulomb_iq*.json`, `librpa_2d_coulomb_method.dat`, and `librpa_2d_coulomb_head.dat`.

## Converge one variable at a time

Keep the physical definition and auxiliary basis fixed. Converge in this order:

1. `out_librpa_2d_direct_ecut`: raise the reciprocal cutoff by at least 20%. For WS2, use 90, 110, then 130 Ry when a final confirmation is needed.
2. `out_librpa_2d_direct_kz_order`: use a monotone sequence such as 32, 48, 64, 96 at the selected cutoff.
3. `out_librpa_2d_direct_gamma_order`: use positive even orders such as 4, 8, 12 or 16. This controls the Gamma-cell average, not the regular-q `k_z` integral.
4. Confirm the chosen point jointly with a materially larger point, for example 110/64/8 against 130/96/12 for a publication result.
5. Only afterward test ABFS/PCA/shrink, k mesh, vacuum and the LibRPA frequency grid. Do not mix these convergence claims.

For every point compare the matrix metadata and PSD audit, total exchange, fixed-index frontier EXX/GW energies and gap. A practical publication target is no more than 20 meV change in each frontier level and gap, with exchange stable to the tighter of 5e-4 Ha or the project-specific target. Report the actual differences; do not call a short plateau converged without the larger confirmation point.

## Apply hard gates

Require all of the following before LibRPA:

- `librpa_2d_coulomb_method.dat` says version 1, method `direct_mixed_fourier`, and the intended cutoff/orders, q count and active auxiliary size.
- Exactly one complete reader-v1 full matrix per IBZ q representative, with the exact atom/block headers and sizes.
- Finite matrix entries; Hermitian residual at roundoff scale; no materially negative eigenvalues. Judge the minimum eigenvalue relative to the largest eigenvalue and numerical norm, and never clip it silently.
- Exact q-star/BZ labels and basis ordering; complete regular/shrunk Cs and inverse-overlap files.
- Pairwise regular and shrunk `max|Cs| <= 2`, unless the material has a separately justified tighter gate.
- Finite negative exchange consistent with a same-definition reference; no NaN/Inf or fatal messages.
- Producer-derived band continuity and near-Fermi EXX agreement with an independent reference before GW.

Then use the strict-2D head/wing skill for full-grid PyATB and LibRPA GW. Keep high-empty QPE failures separate from the fixed near-Fermi manifold.

Read [method-and-convergence.md](references/method-and-convergence.md) when explaining the formula, the Ewald/direct tradeoff, or why direct output removes the large-number cancellation.
