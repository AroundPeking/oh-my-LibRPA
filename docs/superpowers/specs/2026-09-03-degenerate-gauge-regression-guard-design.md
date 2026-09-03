# Degenerate-Gauge Regression Guard Design

## Goal

Teach the OML scientific evaluator to distinguish an ordinary statewise band
regression failure from a failure pattern that is consistent with a changed
basis inside the same KS-degenerate manifolds. The latter remains a hard
failure until wavefunction-subspace or another gauge-invariant check is
available.

## Detection Rule

Run the ordinary statewise KS, EXX, and GW comparison first. A failed result is
classified as `BLOCKED_DEGENERATE_GAUGE_MISMATCH` only when all of the following
conditions hold:

1. state identities and scientific definitions match;
2. every KS state passes the normal regression tolerance and occupations match;
3. candidate and reference form identical KS-degenerate groups at every spin
   and k point, using a fixed `1e-5 eV` degeneracy tolerance;
4. every failing EXX or GW state belongs to a matched group containing at least
   two states;
5. every affected group's EXX or GW arithmetic mean remains within the normal
   regression tolerance.

The group-mean condition represents the trace invariant of a projected
operator. It prevents a uniform physical shift of a degenerate manifold from
being mislabeled as a basis rotation. It does not prove that candidate and
reference wavefunctions span the same subspace.

## Verdict Contract

The classifier returns `status = FAIL`, sets
`subspace_verification_required = true`, and includes the affected state groups
and group-mean errors. `finalize_case` therefore remains failed and `score_case`
cannot promote the run.

KS mismatch, changed group membership, a nondegenerate EXX/GW mismatch, or a
changed group mean retains `REGRESSION_TOLERANCE_EXCEEDED`.

## Evolution Boundary

This change adds diagnosis, not acceptance. A future pass rule needs explicit
overlap evidence proving that candidate and reference wavefunctions span the
same protected subspace, followed by a gauge-invariant self-energy observable
or diagonalization of the self-energy inside that subspace.
