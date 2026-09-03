# Molecular Delta-ST Current-Stack Gate Design

## Goal

Replay the smallest molecular Delta-Sternheimer handoff against the current
ABACUS `master_ghj` and LibRPA 0.7.0 stack, then freeze both successful and
blocking evidence so OML cannot confuse solver completion with a valid LibRPA
handoff.

## Scope Boundary

The H2 replay is an L3 interface checkpoint. It tests the explicit FD8,
`ks_bands`, reader-v1 producer path and the dedicated response-Coulomb
contract. It does not establish box, response-grid, frequency, auxiliary-basis,
or binding-energy convergence and cannot promote `molecular_delta_st_rpa` to a
scientific reference.

The ordinary `v1_coulomb_full_iq_*` family is diagnostic only. A finite LibRPA
energy obtained by pairing it with a Sternheimer response does not repair a
missing `v1_sternheimer_coulomb_iq_*` artifact.

## Evidence Model

The immutable live receipt records:

- exact ABACUS, LibRPA, and PyATB revisions and executable hashes;
- the clean source checkout, source-tree hash, build result, and focused tests;
- hashes for all physical inputs and current reader-v1 outputs;
- producer exit, grid, frequency count, equation count, residuals, wall time,
  and MaxRSS;
- presence of the ordinary metric and absence of the dedicated metric;
- a binary matrix comparison against the previously validated v3 artifacts;
- the diagnostic ordinary-metric LibRPA energy and its difference from the v3
  dedicated-metric energy;
- independent producer, handoff, LibRPA-production, scientific, and promotion
  statuses.

## Gate Semantics

The replay is classified as follows:

1. source identity, build, focused tests, and producer solver may pass;
2. the handoff must block when the dedicated response Coulomb artifact is
   absent, even when the ordinary metric is present;
3. the ordinary-metric LibRPA run is `DIAGNOSTIC_ONLY`, never a production pass;
4. scientific status remains `NOT_EVALUATED` and promotion remains `BLOCKED`;
5. the benchmark-matrix row remains `REFERENCE_PENDING` until the interface is
   restored and the declared convergence axes are completed.

This negative benchmark is expected behavior from OML. It catches a current
stack incompatibility before an expensive production LibRPA campaign.

## Evolution Rule

When a later ABACUS revision restores the dedicated metric, add a new immutable
receipt instead of rewriting this one. The new receipt must first pass this L3
handoff gate, then proceed through molecule and atom absolute-energy plus
binding-contribution convergence. Historical failures remain regression
fixtures for the false-pass audit.
