---
name: abacus-librpa-version-guard
description: Use when preparing, submitting, auditing, debugging, or interpreting ABACUS+LibRPA calculations against an immutable OML compatibility profile.
---

# ABACUS+LibRPA Version Guard

Use this gate before remote execution or interpretation. Call OML MCP
`inspect_profile` with the intended profile ID, then compare exact source
revisions and executable hashes on the server.

## Profiles

| Profile | ABACUS | LibRPA | Scope |
|---|---|---|---|
| `abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08` | `3efad9ed5ca066aee1d1b2214e43f92a2d2a567e` | `dd169fa11fa920d580d4f39dc11e218a7f17f7b5` | enabled non-SOC 3D GW; strict-2D blocked |
| `abacus-librpa-2026-08-30-v2` | `641caa554b44c4db2743603e9c75c96379901d7c` | `7e40c5bbf735a78aa15fa589ca2468fec2e2427b` | immutable historical admission |
| `abacus-librpa-2026-08-30-v3` | `81ff5f33995e7a545c2b9cb4f1a74490a74ecb4a` | `7e40c5bbf735a78aa15fa589ca2468fec2e2427b` | corrected Sternheimer admission |

All use PyATB `9fb9028c59b1dbaf9cf66965280961fc2225d9eb` where required. V2/v3 register
`periodic_3d_gw`, `strict_2d_gw`, `molecular_delta_st_rpa`, and
`solid_delta_st_rpa` as `TESTABLE`, not `ENABLED`. Keep v2 historical; use v3
for new Sternheimer work. Promotion requires reviewed L3 evidence for
`EXPERIMENTAL` and L4 scientific acceptance for production.

## Hard Gates

1. Record the profile ID; branch names are insufficient.
2. Verify ABACUS/LibRPA revisions and PyATB for head/wing work.
3. Hash actual executables; source identity alone is insufficient.
4. Require clean pinned trees, or record a feature-branch exception with reason and contract.
5. Block mismatched or unknown identities. Label old outputs as reproductions.
6. Separate process, numerical, and scientific status.

## Data Contract

- Explicitly use reader v1: ABACUS `out_librpa_reader_version 1`; LibRPA
  `version_coul_reader 1` and `version_lri_reader 1`.
- For v3 `task = sternheimer_rpa`, set
  `prefix_coul_full = v1_sternheimer_coulomb_iq_`. Ordinary
  `v1_coulomb_full_iq_` is diagnostic only and cannot replace it.
- Legacy requires an explicit profile. Never infer it from source default `-1`.
- Symmetry comes from `stru_out`; LibRPA rebuilds rotations. Copy no legacy sidecars.
- Strict-2D uses full Ewald plus analytic Gamma head/wing;
  `direct_mixed_fourier` is diagnostic only.

## Evidence

Record host/run/job, profile and revisions, absolute executable paths and
SHA-256, source HEAD/clean status, PyATB hash when used, reader/symmetry
contract, input-manifest digest, and immutable receipt. Prefer hashes over
timestamps. Unknown or dirty identity blocks new parameter-sensitive claims.

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
Sternheimer Coulomb: dedicated-v1 | not-used
Symmetry source: stru_out
Version verdict: match | mismatch-blocked | feature-branch-exception | unknown-blocked
Route status: BLOCKED | TESTABLE | EXPERIMENTAL | ENABLED
```
