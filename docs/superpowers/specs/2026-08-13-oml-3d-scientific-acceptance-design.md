# OML 3D Scientific Acceptance and Deferred 2D Design

## 1. Purpose

This phase turns a completed three-dimensional ABACUS -> PyATB -> LibRPA GW run
into a result that can be evaluated against explicit numerical and scientific
criteria. It also preserves a discoverable strict-2D route while preventing the
pinned LibRPA 0.7.0 profile from executing or accepting that route.

The accepted policy is:

- a definition-matched regression tolerance of 0.001 eV;
- a convergence tolerance of 0.05 eV in the low-energy state window;
- the low-energy window spans `VBM-3` through `CBM+3` at every evaluated
  k-point;
- the first live 3D campaign varies frequency count, empty-state count, and
  screening k-grid separately;
- NAO, ABFS, and shrink convergence is a later independent campaign;
- no strict-2D calculation is run or scientifically evaluated with the pinned
  LibRPA 0.7.0 profile.

## 2. Scope

### 2.1 Included

- nonmagnetic, collinear, non-SOC, insulating 3D periodic GW;
- ABACUS reader-v1 production, PyATB head/wing data, and LibRPA 0.7.0;
- finite and shape validation for KS, EXX, and GW band tables;
- exact physical-definition signatures;
- low-energy state matching and definition-matched regression;
- convergence evaluation across immutable runs;
- immutable scientific-acceptance reports consumed by the scorecard;
- a machine-readable strict-2D capability state and stable execution block.

### 2.2 Excluded

- live strict-2D execution or 2D numerical thresholds;
- magnetic, noncollinear, SOC, metallic, or DFT+U scientific acceptance;
- NAO, ABFS, or shrink convergence in the first live campaign;
- comparison with experiment as the primary numerical acceptance criterion;
- automatic promotion of a newly converged result into an accepted reference;
- automatic changes to active scientific policy.

## 3. Capability Model

The compatibility profile gains a `capabilities` object. Each route has a
status, reason code, affected component, and explicit enablement requirements.

For the pinned profile, the relevant entries are:

```json
{
  "capabilities": {
    "periodic_3d_gw": {
      "status": "ENABLED"
    },
    "strict_2d_gw": {
      "status": "BLOCKED",
      "reason_code": "LIBRPA_070_STRICT_2D_INVALID",
      "component": "librpa",
      "component_revision": "dd169fa11fa920d580d4f39dc11e218a7f17f7b5",
      "enablement_requires": [
        "a replacement pinned LibRPA revision with the strict-2D defect fixed",
        "definition-matched strict-2D regression fixtures",
        "finite-q and Gamma head/wing acceptance tests",
        "vacuum, in-plane k-grid, and final GW convergence gates"
      ]
    }
  }
}
```

`plan_case(system_type="2d")` remains available and returns route
`strict_2d_gw_deferred`. The plan contains no executable stages, carries the
profile capability record, and returns a warning explaining the version block.
`validate_case` returns the stable failing gate `route.strict_2d_capability`.
`prepare_run` returns `CAPABILITY_BLOCKED` before creating a run directory or
state record. This is an interface for later completion, not partial 2D support.

No 2D live job, 2D frozen numerical result, or 2D PASS replay is added in this
phase. Unit tests cover only discovery and enforcement of the block.

## 4. Scientific Evidence Model

Scientific evidence is separate from scheduler completion and stage artifact
acceptance. A run may have all stages passed and still have scientific status
`NOT_EVALUATED`, `INCOMPLETE`, or `FAIL`.

### 4.1 Definition signature

Every candidate and reference carries a canonical definition signature. The
signature contains:

- compatibility profile ID and ABACUS, LibRPA, and PyATB revisions;
- task, dimensionality, spin, SOC, and symmetry route;
- structure, pseudopotential, NAO, and ABFS file SHA-256 values;
- lattice and atomic-position identity through the immutable `STRU` hash;
- SCF screening k-grid and band-path k-point coordinates;
- `ecutwfc`, `nbands`, smearing method, and smearing width;
- `nfreq`, dielectric option, analytic-continuation settings, and head/wing
  policy;
- full/cut Coulomb selection, `use_fullcoul_exx`, shrink selectors, and shrink
  thresholds;
- reader version and relevant LibRPA numerical thresholds.

The canonical JSON is hashed with SHA-256. Regression comparison is permitted
only when both signatures are identical. A mismatch returns
`DEFINITION_MISMATCH`, lists the differing fields, and leaves regression
validity `NOT_EVALUATED`. It is never converted into a loose numerical PASS.

For a convergence series, exactly one declared axis may differ between adjacent
levels. All other definition fields must match. This prevents a k-grid test
from silently changing frequency count, basis, Coulomb convention, or software
revision.

### 4.2 Band-table representation

The parser reads `KS_band_spin_*.dat`, `EXX_band_spin_*.dat`, and
`GW_band_spin_*.dat`. Each nonempty row contains:

1. k-point index;
2. three fractional k-point coordinates;
3. repeated occupation and energy pairs, one pair per band.

The parser rejects inconsistent row widths, duplicate k-point identities,
non-finite values, mismatched spin sets, or mismatched k-point/band dimensions
between KS, EXX, and GW tables. Energies are stored in eV. State identity is
`(spin, periodic k-point coordinate, one-based band index)`; row order alone is
not an identity.

### 4.3 Insulator and state-window gate

The first implementation accepts only `nspin=1` insulating occupation patterns.
At every k-point, occupied bands must precede unoccupied bands, and the occupied
band count must be constant over the band path. Partial occupations or changing
occupied-band count return `UNSUPPORTED_OCCUPATION_PATTERN` and leave numerical
validity unevaluated.

Let `v` be the highest occupied band index and `c=v+1` the lowest unoccupied
band index. The evaluated band interval is

```text
[max(1, v-3), min(nbands, c+3)]
```

at every evaluated k-point. The report records `v`, `c`, the actual bounded
interval, and every included state identity. The fundamental gap is

```text
min_k E_GW(c,k) - max_k E_GW(v,k).
```

## 5. Definition-Matched Regression

A versioned reference bundle contains the definition signature, accepted state
window, reference KS/EXX/GW energies, tolerances, provenance, and approval
record. References are repository-managed data addressed by benchmark ID; MCP
tools do not accept an arbitrary user-provided reference path.

For every state in the window, OML computes candidate-minus-reference errors
for KS, EXX, and GW energies. Regression passes only when:

- the definition signatures match exactly;
- state sets match exactly after periodic-coordinate matching;
- all required values are finite;
- no required state has a QPE failure, invalid analytic continuation, or
  unstable-root marker;
- the maximum absolute KS, EXX, and GW state errors are each at most 0.001 eV.

The report includes maximum absolute error, RMS error, the worst state, and the
candidate/reference values. A reference derived from a newly converged campaign
has status `CANDIDATE_REFERENCE` until explicitly reviewed and promoted in a
normal repository commit. OML cannot promote it automatically.

## 6. Convergence Acceptance

A convergence bundle names one benchmark family and supplies ordered immutable
runs for one axis. Adjacent levels must differ only in that declared axis.

The first BN campaign evaluates these axes independently:

1. `nfreq`;
2. `nbands` or, equivalently for a fixed occupied count, the empty-state count;
3. the SCF screening k-grid.

For each axis, OML compares the final two levels over the common state window.
An axis passes when all of the following hold:

- both runs passed all execution and finite-output gates;
- all non-axis definition fields match;
- the maximum absolute change in GW energy over the window is at most 0.05 eV;
- the absolute change in the fundamental GW gap is at most 0.05 eV;
- no state in the window has a QPE, non-finite, analytic-continuation, or
  unstable-root failure.

KS and EXX changes are reported but do not substitute for the GW criterion.
The complete first-stage convergence verdict passes only when all three axes
pass. Missing axes remain `NOT_EVALUATED`; one passing axis cannot compensate
for another missing or failing axis.

The final accepted level from this campaign is a candidate baseline, not an
accepted regression reference. NAO, ABFS, and shrink convergence is conducted
later with the first three axes fixed at their accepted values.

## 7. MCP and Persistence

Phase 3 adds one bounded MCP tool:

```text
finalize_case(run_id, plan_digest, benchmark_id, convergence_bundle_id?)
```

The tool accepts identifiers only. Benchmark and convergence definitions come
from versioned repository-managed JSON. It verifies immutable run lineage,
reads the accepted LibRPA snapshot, evaluates scientific gates, and stores an
immutable report under `.oml/science/`. Repeating the exact request returns the
same report; changing evidence under the same report identity is rejected.

`score_case` consumes only a persisted scientific report whose run ID, plan
digest, manifest digest, profile ID, and final LibRPA attempt match the current
run. Otherwise numerical/scientific validity stays `NOT_EVALUATED`.

The numerical/scientific score is:

- `1.0` only when required regression and convergence evidence pass;
- `0.0` when complete required evidence was evaluated and failed;
- `null` when definitions mismatch or required evidence is missing.

This preserves the non-compensating distinction between a failed scientific
test and a test that has not been validly performed.

## 8. Error and Safety Behavior

- A blocked 2D route never creates run state or submits Slurm work.
- A scheduler PASS never creates scientific evidence.
- A definition mismatch never falls back to comparing only convenient states.
- Missing QPE diagnostics are reported as missing evidence when the benchmark
  requires them; explicit failure markers fail the affected state window.
- A convergence comparison with more than one changed axis is rejected.
- Results and logs are retained. This phase adds no cleanup operation.
- Failed or incomplete scientific reports are immutable and remain available
  for diagnosis.

## 9. Test Strategy

Unit and frozen-replay tests cover:

- strict-2D route discovery and LibRPA 0.7.0 execution blocking;
- profile capability schema validation;
- band-table parsing, periodic k-point identity, shape, and finite checks;
- insulating occupation detection and bounded `VBM-3:CBM+3` selection;
- exact definition matching and field-level mismatch reports;
- a 0.001 eV boundary regression PASS and just-over-boundary FAIL;
- a 0.05 eV boundary convergence PASS and just-over-boundary FAIL;
- rejection of convergence pairs with multiple changed axes;
- QPE, NaN, missing-state, and state-reordering failures;
- immutable scientific report persistence and scorecard consumption;
- the existing finite-but-unvalidated BN replay remaining `INCOMPLETE`.

The live DF campaign runs only after the software suite passes. It uses the
pinned revisions and fresh immutable run directories. Each axis is varied
separately, only one formal run exists for each plan, and results are reported
as measured value, threshold, and remaining decision. No 2D job is submitted.

## 10. Acceptance Criteria

This phase is complete when:

1. the pinned profile exposes strict 2D as blocked with a stable reason code;
2. no current MCP path can materialize or submit a strict-2D run;
3. OML can parse and identify the accepted low-energy state window;
4. OML enforces exact definition matching before 0.001 eV regression;
5. OML enforces single-axis 0.05 eV GW energy and gap convergence;
6. scientific reports are immutable and traceable to the final LibRPA attempt;
7. `score_case` cannot convert missing scientific evidence into PASS;
8. the existing test suite and new frozen replays pass;
9. the 3D BN DF campaign is documented without claiming scientific acceptance
   until every required axis has passed;
10. repository and installed OML skill surfaces remain synchronized when the
    skill text changes.
