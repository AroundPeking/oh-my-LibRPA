---
name: abacus-librpa-version-guard
description: Use when preparing, submitting, auditing, debugging, or interpreting ABACUS+LibRPA calculations against an immutable OML compatibility profile.
---

# ABACUS+LibRPA Version Guard

Use this preflight gate before any ABACUS+LibRPA calculation and before trusting
an existing result. Real compute runs on a server. Call the OML MCP
`inspect_profile` tool with the intended profile ID, then compare the source
revisions and executable hashes on the server with that exact profile.

## Profiles

OML currently keeps two generations. They are not interchangeable.

### Production 0.3.1

Profile `abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08`:

- ABACUS `master_ghj`: `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e`
- LibRPA `v0.7.0`: `dd169fa11fa920d580d4f39dc11e218a7f17f7b5`
- PyATB `enable_head_wing`: `9fb9028c59b1dbaf9cf66965280961fc2225d9eb`
- approved write scope: non-SOC periodic 3D GW only
- `strict_2d_gw`: blocked by `LIBRPA_070_STRICT_2D_INVALID`

### V2 Admission

Profile `abacus-librpa-2026-08-30-v2`:

- ABACUS `master_ghj`: `641caa554b44c4db2743603e9c75c96379901d7c`
- LibRPA `master_ghj` (0.7.0 line): `7e40c5bbf735a78aa15fa589ca2468fec2e2427b`
- PyATB `enable_head_wing`: `9fb9028c59b1dbaf9cf66965280961fc2225d9eb`
- registered `TESTABLE` routes: `periodic_3d_gw`, `strict_2d_gw`,
  `molecular_delta_st_rpa`, and `solid_delta_st_rpa`
- write scope: admission harness only; these routes are not production-enabled

Do not carry the old strict-2D block into the v2 profile. Conversely, do not
treat `TESTABLE` as `ENABLED`: L3 evidence permits only a reviewed move to
`EXPERIMENTAL`, and L4 scientific acceptance plus review is required for
production enablement.

## Hard Gates

1. Record the profile ID before comparing any SHA. A matching branch name is
   insufficient.
2. Verify ABACUS and LibRPA source revisions before submission, restart, or
   interpretation. Verify PyATB whenever head/wing data is used.
3. Hash the actual ABACUS and LibRPA executables. Source identity alone does not
   prove which binary was run.
4. Require clean pinned source trees, or record a feature-branch exception with
   branch, commit, reason, and parameter contract.
5. A mismatch or unknown revision blocks normal execution. Old results may be
   inspected only as explicitly labelled reproductions.
6. Keep process completion, numerical validity, and scientific acceptance as
   separate statuses.

## Data Contract

- OML production output explicitly sets ABACUS
  `out_librpa_reader_version 1` and LibRPA `version_coul_reader 1` plus
  `version_lri_reader 1`.
- Legacy is available only through an explicit compatibility profile; never
  infer it from LibRPA's source default `-1`.
- Symmetry operations come from `stru_out`, and LibRPA reconstructs rotations.
  Do not copy or require `irreducible_sector.txt`, `symrot_R.txt`,
  `symrot_k.txt`, or `symrot_abf_k.txt`.
- Strict-2D production uses full Ewald Coulomb with analytic Gamma head/wing.
  `direct_mixed_fourier` remains a diagnostic control, not a production route.

## Evidence

For every run, record:

- host, run directory, and scheduler job ID when applicable
- profile ID and pinned component revisions returned by `inspect_profile`
- absolute executable paths, SHA-256 hashes, sizes, and timestamps
- source paths, branches, HEAD revisions, tree hashes, and clean-tree status
- PyATB source and extension hashes when used
- reader format, `stru_out` presence, and absence of legacy symmetry sidecars
- input-manifest digest and immutable stage receipt

Prefer source-tree SHAs and executable hashes over timestamps. If only a
timestamp is available, label the binary identity as unknown.

## Decision Table

| Situation | Action |
|---|---|
| Source and executable evidence match the selected profile | Continue to route-specific gates. |
| PyATB head/wing route also matches | Continue to state and symmetry-dimension gates. |
| One component is older, dirty, or unknown | Block normal execution and rebuild or sync. |
| An old result is intentionally reproduced | Keep it isolated and label the profile exception. |
| A feature branch is tested | Record branch, SHA, reason, and contract before execution. |
| Existing output lacks version evidence | Do not use it for parameter-sensitive conclusions. |

## Output Block

Before a real run or when reporting a finished calculation, include:

```text
Execution: server=<host>, local_compute=no
Profile: <profile-id>
ABACUS pinned: <ref> <sha>
LibRPA pinned: <ref> <sha>
PyATB pinned: <ref> <sha-or-not-used>
ABACUS build: <sha256> <path>
LibRPA build: <sha256> <path>
PyATB extension: <sha256-or-not-used> <path-or-not-used>
Reader contract: v1 | explicit-legacy
Symmetry source: stru_out
Version verdict: match | mismatch-blocked | feature-branch-exception | unknown-blocked
Route status: BLOCKED | TESTABLE | EXPERIMENTAL | ENABLED
```
