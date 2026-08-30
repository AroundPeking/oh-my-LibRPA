# Fisherd v3 Sternheimer handoff checkpoint (2026-08-30)

This focused checkpoint validates profile `abacus-librpa-2026-08-30-v3` and
ABACUS revision `81ff5f33995e7a545c2b9cb4f1a74490a74ecb4a`. The complete
machine-readable evidence is
[`benchmarks/live/fisherd-v3-sternheimer-handoff-2026-08-30.json`](../../benchmarks/live/fisherd-v3-sternheimer-handoff-2026-08-30.json).

## Contract

ABACUS now writes the Coulomb metric that generated each Sternheimer
perturbation as `v1_sternheimer_coulomb_iq_<iq>_rank0.dat`. LibRPA uses
`prefix_coul_full = v1_sternheimer_coulomb_iq_` for `task = sternheimer_rpa`.
The ordinary `v1_coulomb_full_iq_*` RI/Ewald matrix remains available as a
diagnostic, but it is not a response whitening fallback.

The patched ABACUS production target built on Fisherd. Its focused source test
passed 27/27 cases. The executable SHA-256 is
`61eb3b764bee73bd2dd91678782d82c0ba5b523b31b7322b985e03d0ae34a720`.

## Si Solid

The same 4x4x4 Si2, q=21, single-frequency case solved all 62,464 equations with
zero failures. The maximum solver relative residual was `9.99997e-9`; ABACUS
finished in 2,083.53 seconds.

The dedicated 244x244 metric is Hermitian and positive. Its eigenvalues span
`9.17360e-6` to `971.10354`. It reproduces the separately emitted grid
diagnostic to `1.13e-16` relative error and differs from the ordinary reader metric by
`0.813325` in relative Frobenius norm, confirming that the two definitions must
not be mixed.

OML reconstructed the Delta response components to `9.09e-16` relative error.
The dedicated-metric trace-log is `-3.104148571476`; the same-state LCAO-SOS
value is `-2.605925910823`. LibRPA read the dedicated prefix and independently
reported `-3.104148571459`, with a weighted single-q contribution of
`-0.007719384206866 Ha`. The historical ordinary-reader trace-log was about
`-1.74e5`; that numerical catastrophe is absent.

An independent conventional LibRPA SOS calculation at the nearest available
frequency gives `-2.583137112930`. It differs from the same-state LCAO-SOS value
by 0.87%, while the frequencies differ by 2.19%. This is a magnitude and
interface check, not a full scientific equivalence test.

## H2 Molecule

The H2 producer solved all 30 equations with zero failures. Its dedicated 30x30
metric is Hermitian and positive, with eigenvalues from `0.00516462` to
`206.64975`. The ordinary reader matrix differs by `0.00370114` in relative
norm.

LibRPA finished successfully with `EcRPA = -0.01100066029904 Ha`. The historical
ordinary-reader value was `-0.0110925901502 Ha`, a relative change of 0.83%.
This checkpoint validates the molecular file format, channel mapping, and
finite result; it does not establish box, frequency, grid, NAO, or ABFS
convergence.

## Decision

The ABACUS to LibRPA Coulomb-representation root cause is fixed for the tested
solid and molecular states. The v3 handoff gate is `PASS`, but scientific status
remains `NOT_EVALUATED` and promotion remains `BLOCKED`.

The next required work is complete q/frequency integration, solid and molecular
convergence ladders, strict-2D route replay, periodic GW route replay, and L4
comparison with accepted references. Automatic evolution may choose one of
these registered axes, but it must not promote a route from this focused test.
