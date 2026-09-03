# Degenerate-Gauge Regression Guard Plan

**Goal:** Make the current periodic-3D benchmark's degenerate-gauge caveat an
executable, non-promoting OML scientific-evaluation rule.

### Task 1: Freeze the classifier behavior

- [x] Add a synthetic two-state unitary-rotation example that must receive the
  dedicated blocked reason.
- [x] Prove that KS drift, changed degeneracy groups, nondegenerate drift, and
  changed group means retain the ordinary regression failure.

### Task 2: Implement and expose the evidence

- [x] Build deterministic KS-degenerate groups per spin and k point.
- [x] Report affected groups, statewise errors, group means, and the required
  subspace verification without changing the hard-fail status.
- [x] Increment the scientific evaluator and package versions so old reports
  cannot be inherited silently.

### Task 3: Document and publish

- [x] Update controlled-execution and GW route documentation.
- [x] Run focused tests, the full suite, skill self-test, and package build.
- [x] Mirror the installed skill, commit with required attribution, and push.
