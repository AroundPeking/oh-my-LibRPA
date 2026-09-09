# OML Benchmark Matrix v1

## Purpose

This matrix defines the evidence required before an OML route or material class
is used for unattended calculations. A completed process is not a scientific
pass. Hard-gate failures cannot be compensated by a high score, and missing
references remain `REFERENCE_PENDING`.

## Route Benchmarks

| Benchmark row | Reference system | Primary observables | Required controls | Status |
| --- | --- | --- | --- | --- |
| `periodic_3d_gw` | BN followed by Si/MgO | KS/EXX/GW state window, fundamental gap, QPE status | symmetry/full-q, nfreq, empty states, screening k-grid, basis | `PARTIAL_REFERENCE` |
| `strict_2d_sos_rpa` | monolayer MoS2, Lz=25 | N=8/10/12/16 Gamma and total RPA energies | qavg/no-head-wing finite-q match, Gamma area scaling | `PASS_REFERENCE_BOUNDED` |
| `strict_2d_gw` | MoS2 or WSe2, then graphene diagnostic | first-PBE-indexed frontier, gap, band topology, finite high states | symmetry/full-q, PyATB full grid, vacuum, k-grid, basis | `REFERENCE_PENDING` |
| `molecular_delta_st_rpa` | H2 followed by H2O and atomic fragments | absolute Ec, binding contribution, solved equations, residuals | SOS match, box, real-space Ecut, nfreq, PCA/ABFS | `REFERENCE_PENDING` |
| `solid_delta_st_rpa` | Si followed by MgO | full-q Ec, per-q trace-log, solved equations, residuals | SOS match, real-space Ecut, nfreq, PCA/ABFS, q-grid | `REFERENCE_PENDING` |

The accepted strict-2D row uses benchmark
`strict2d-sos-rpa-mos2-qavg-v1` and profile
`abacus-librpa-2026-09-03-strict2d-sos-rpa-v2`. It is `ENABLED` by a
reference-bounded four-mesh criterion. It establishes no asymptotic exponent
and is not strict-2D GW acceptance.

The 2026-09-03 Fisherd current-stack replay leaves
`molecular_delta_st_rpa` at `REFERENCE_PENDING`. ABACUS
`1648a8a344427ae1b6394912bf677c4a20e053f2` passed its focused tests and H2
solver gate, but the L3 handoff is `BLOCKED_MISSING_RESPONSE_COULOMB` because
the dedicated `v1_sternheimer_coulomb_iq_*` artifact is absent. The available
ordinary reader-v1 Coulomb matrix is a diagnostic and cannot satisfy this
gate.

The 2026-09-03 Fisherd current-stack BN replay keeps `periodic_3d_gw` at
`PARTIAL_REFERENCE`. Current ABACUS completes SCF, NSCF, reader-v1, embedded
symmetry, shrink, and band preprocessing; current LibRPA matches the official
frozen dataset exactly and reproduces current results across `1x48` and `4x1`
layouts. The historical end-to-end band comparison is
`BLOCKED_DEGENERATE_GAUGE_MISMATCH`: KS eigenvalues match exactly, but EXX/GW
members of degenerate manifolds are not statewise comparable across the old
and current producer gauges. A subsequent current-stack `4x4x4` ladder fixes
`n_params_anacon=6`: `nfreq 24 -> 32` passes the low-energy state and gap gates
at `0.04440/0.00021 eV`, while `16 -> 24` fails at `0.51179 eV`. The matched
`2x2x2 -> 4x4x4` screening-grid pair fails at `139.78139 eV`. The current
ladder now extends through `14x14x14`: successive low-energy GW maxima are
`0.53403`, `0.05378`, `0.05357`, `0.06091 eV`, and `0.03279 eV`.
`10x10x10 -> 12x12x12` remains a recorded FAIL at the fixed `0.05 eV`
statewise gate, while `12x12x12 -> 14x14x14` is the first adjacent screening
PASS with a `0.02590 eV` gap change. Immutable profile
`abacus-librpa-2026-09-06-v5` records that BN-specific pair. The subsequent
MCP-controlled `8-q symmetry -> 64-q full-q` comparison at BN `4x4x4` and no
head/wing is `PASS_REFERENCE_BOUNDED`: all 24 low-energy KS/EXX/GW states and
the gap agree exactly, while the complete 78-state audit differs by at most
`1e-5 eV`. Profile `abacus-librpa-2026-09-06-v6` records this additional
bounded result but remains L3 `EXPERIMENTAL`. Missing empty-state, NAO, ABFS,
transfer, and physical-reference gates keep the row `PARTIAL_REFERENCE`; the
aggregate scientific verdict remains `NOT_EVALUATED`.

## Material-Class Benchmarks

| Benchmark row | Initial reference | Distinguishing physics | Minimum result checks | Status |
| --- | --- | --- | --- | --- |
| `perovskite_gw` | cubic SrTiO3 | d-character conduction bands and multiple near-edge states | state identity, gap, semicore/basis and k-grid convergence | `REFERENCE_PENDING` |
| `transition_metal_oxide_gw` | AFM NiO | spin, DFT+U starting point, localized d states | magnetic moments, occupations, state-resolved QPE, U definition | `REFERENCE_PENDING` |
| `altermagnet_gw` | alpha-MnTe | magnetic symmetry and spin-split bands | magnetic ground state, symmetry/full-q, spin-resolved state identity | `REFERENCE_AVAILABLE` |
| `soc_2d_gw` | WSe2 | scalar-relativistic (no-SOC) strict-2D screening and states | PyATB full grid, strict-2D Coulomb, state identity and gap | `REFERENCE_PENDING` |

These systems are registered material-class benchmark identities with a frozen
asset basis, recorded in `benchmarks/materials/*.json` (packaged copy in
`oml_mcp/material_classes/*.json`). Each identity freezes the PP, NAO and ABFS
asset hashes, the structure prototype and space group, the magnetic order and
nspin, and the reference status. They are proposed benchmark identities, not
accepted numerical references.

Asset and software identity is frozen now; the input-file hash tree, software
revisions and executable hashes are frozen only when a reference run is
produced (they are `REFERENCE_PENDING` until then):

- `perovskite_gw` (SrTiO3, non-magnetic, Dojo-NC-SR + TZDP) and
  `transition_metal_oxide_gw` (AFM NiO, Dojo-NC-SR + TZDP) freeze only the PP
  and NAO assets. Their ABFS auxiliary bases must be generated on the remote
  host before a GW reference can be produced.
- `altermagnet_gw` (alpha-MnTe, collinear, GTH + TZDP) and `soc_2d_gw` (WSe2,
  scalar-relativistic/no-SOC, CP2K-GTH + SIAB) freeze PP, NAO and ABFS assets.
  `altermagnet_gw` now has
  a frozen numerical reference from the completed 2026-08-02 G0W0 band run (see
  the `reference` block and the sibling `altermagnet_gw_reference.json` artifact);
  its input-file hash tree and software stack are frozen as `REFERENCE_AVAILABLE`.
  `soc_2d_gw`'s run set is still diagnostic only — no converged reference exists
  yet, so it remains `REFERENCE_PENDING`. (A separate SOC lane would need nspin=4
  with noncolin/lspinorb and matched SOC UPFs, which are not yet available on the
  probe host.)

### Material-Class Evaluator

A produced run is validated against a frozen identity by
`evaluate_material_class` (MCP tool `evaluate_material_class`). It computes
non-compensating gates and never submits or promotes:

- `identity.assets.{pseudopotentials,orbitals,auxiliary_bases}` — every frozen
  asset must be present in the run with a matching SHA-256; extra run assets are
  allowed (e.g. a freshly generated ABFS).
- `identity.assets.present` — at least one asset group must be frozen.
- `identity.software` — enforced only once a reference is frozen
  (`REFERENCE_AVAILABLE`); for a pending identity it is auto-PASS.
- `contract.spin` — run nspin/SOC must match the identity magnetic order. The
  default occupation value is derived from the identity (2.0 for nspin=1, 1.0
  for nspin>=2) so a run cannot relabel a metallic state as an insulator.
- `window.valid` — the spin-resolved insulating window is re-derived from the
  raw states by `select_spin_resolved_window`, which supports nspin>=1 and SOC.
- `reference.status` — for `REFERENCE_PENDING` the gate FAILs and the verdict is
  `REFERENCE_PENDING`/`BLOCKED`; for `REFERENCE_AVAILABLE` it runs the statewise
  regression against the frozen reference.

`select_spin_resolved_window` extends `select_insulating_window` (which remains
nspin=1 only) to magnetic and SOC materials. It validates each spin channel
independently (constant occupied-band count along the k path), builds a per-spin
window, and takes the fundamental GW gap across the whole spin manifold (max VBM
minus min CBM over all spins) — the correct definition for a spin-split
insulator.

## Evidence Per Case

Every case records:

- exact source revisions, executable hashes and dependency trees;
- structure, PP, NAO, ABFS, input and helper hashes;
- route, reader version, symmetry source, spin/SOC/U and k/q-grid definition;
- scheduler state, application exit, artifact completeness and parser results;
- numerical residuals, finite/Hermitian checks and route-specific invariants;
- scientific observables, reference deltas and convergence-axis receipts;
- source frequency-grid, Padé/resampling, and QP-solver settings as part of the
  definition for every GW convergence pair;
- wall time, node-hour, MaxRSS and retained-disk cost.

## Harness Quality

The benchmark suite must include known-good, incomplete, non-finite,
mixed-reader, mixed-symmetry, stale-plan, duplicate-job and wrong-state
fixtures. It reports false-pass and false-block counts separately. A new rule
cannot be promoted when it turns a known bad fixture into a pass, even if its
aggregate score improves.

Registered suite `strict2d-sos-rpa-regression-v1` currently supplies one
known-good strict-2D SOS-RPA replay and ten blocked fixtures. It covers source
and route drift, mixed reader contract, missing mesh, non-finite energy, failed
process status, reference-energy drift, finite-q disagreement, an asymptotic
overclaim, and a stale fit receipt. Project-wide mixed-symmetry, stale-plan,
duplicate-job, and wrong-state fixtures remain required for the corresponding
route evaluators; this route-specific suite does not claim that broader
coverage.

Frozen replay `periodic-gw-degenerate-gauge-v1` adds one exact statewise pass,
one trace-preserving two-state rotation that must remain blocked, and four
counterexamples for nondegenerate drift, changed KS group membership, and a
changed degenerate-group mean or occupation manifold. It tests diagnostic
specificity; it does not provide wavefunction overlaps or scientific
acceptance.
