# SIAB Generation And Validation

## Scope

Use for physical NAO selection, generation and diagnosis. Auxiliary-only
`for_aux` and product-PCA ABFS are separate assets; use
`abacus-librpa-abfs-orbital` for those. Never regenerate a validated matched
library set just to standardize a name, training cutoff or project layout.
Run native generation and physics on an approved remote host only. No local
ABACUS/LibRPA compilation, native probes or physics fallback.

## Before Generating A Missing Set

1. Inspect the actual PP header and reference configuration: XC, scalar/SOC,
   valence charge, occupied shells, NLCC, projector channels and PP hash.
   The family name alone is not a compatibility check.
2. Search the shared asset library, accepted producer manifests and original
   SIAB archives. Prefer exact PP+physical-NAO matches. Existing ABFS must
   also match the physical NAO and its auxiliary-only construction.
3. Compare the archived `SIAB_INPUT` AND every effective `Level*.INPUT`.
   Do not silently equate old `info` JSON with newer
   `element/optimize/radial` JSON or fill historical defaults from today's code.
4. Design the smallest justified starting ladder for the actual shells.
   A semicore s/p shell can justify additional radial functions, but electron
   count alone does not validate giving every shell the same zeta multiplicity.
   Keep this as a candidate until material PBE and EXX tests pass. Neither a
   larger nor a smaller basis is universally safer or more accurate.
5. Keep reference dimers/trimers, distances, spin, XC and training targets
   explicit. Record both computed PW bands and nonzero optimization weights.
   If the desired empty-state window is untested, call it untested; change
   one training variable only if a matched material test demonstrates need.

## Effective SIAB Settings

Record for each level:

| Group | Required evidence |
|---|---|
| Physical orbitals | Actual header counts by l, radial mesh/dr, Rcut, physical AO count |
| PW references | Structures and units, PP hash, Ecut, computed nbands, spin, electronic sigma, PW inputs and outputs |
| Targets | Explicit band range or actual `istate.info` occupations/weights, resolved nonzero-weight count |
| Optimization | Backend/source hash, optimizer, lr/eps, objective/norm, max steps and actual stopping point, seed |
| Restart | Previous coefficients, `fix`/optimization mask, retained and newly optimized radial functions |
| Radial export | Bessel-grid cutoff, endpoint smoothing setting/formula, normalization and any export orthogonalization |
| Results | Level inputs, coefficients, complete spillage history, physical orbital and SHA256 |

In the inspected SIAB implementation, `auto` uses occupations from
`istate.info`, not uniform weights on every calculated PW band. `fix` maps
to `opt_C_read=false` for imported coefficients. Verify both against the
version actually executed. Occupation-weighted spillage is not an empty-state
or RI-product completeness certificate. The final exported basis may also
be orthogonalized; its radial Gram alone does not diagnose training quality.

Do not confuse electronic `sigma=0.01 Ry` with radial
`smearing_sigma=0.1 bohr` in the newer generation archive. The inspected
radial export uses a factor `1-exp(-(r-Rcut)^2/(2*sigma_r^2))`; this is a
radial endpoint operation, not a change to the Coulomb kernel. For an old
archive with only `cal_smooth=true`, do not invent its exact width/backend.

## Validation Ladder

1. **Atomic radial check:** exact l/n counts, mesh, finite values,
   normalization, endpoints, same-l Gram eigenvalues, and plotted radial
   functions including nodes/tails. Record quadrature and normalization.
2. **Material overlap and PBE:** periodic Bloch `S(k)` conditioning where
   available, SCF/charge/occupations, same-PP PW/NAO frontier and the desired
   empty-state window, plus the selected independent PBE reference.
3. **RI/EXX:** keep physical NAO separate from smooth auxiliary-only channels;
   inspect the local metric actually inverted, retained rank if truncating,
   fitting coefficients and fit residual where available. Audit final full
   Coulomb all-q finite/Hermitian/PSD and its scale independently. Neither
   Coulomb PSD nor an atomic identity Gram proves the local fit is stable.
4. **Band check:** complete raw-index EXX spectrum, fixed occupied/empty
   manifolds, near-gap and high-state scales/nonfinites/intrusions. Preserve
   steps and anomalies; do not smooth or sort across occupations to pass.
5. **GW readiness:** a numerical EXX pass makes a controlled GW candidate,
   not a quantitatively converged/publishable result. Preserve the exact
   matched producer, band and vxc data. Prepare same-producer full-grid
   PyATB for head/wing and validate dimensions before any authorized GW.
   Independent reference, empty-state/NAO/ABFS and numerical convergence
   remain separate claims. A readiness question is not job authorization.

An unresolved periodic/local-metric spectrum must be marked unmeasured, not
inferred from another matrix. Keep this distinction even if the user elects
to proceed with a bounded diagnostic after a successful EXX test.

For a no-`exx_cs_inv_thr` control, preserve omission, record the binary's
effective default and factorization route, and do not silently add a positive
truncation threshold. No threshold change substitutes for a failed basis
or product-fit validation. Generation PCA, explicit-ABFS producer PCA,
local inverse thresholds, material shrink and LibRPA screening are different
settings; archive them separately.

## Verified GeTe Example (Not Universal Defaults)

Source: ABACUS-orbitals `Dojo-NC-SR/Orbitals_v2.0/{Ge,Te}_TZDP/info/10`,
subtree verified at commit `3b634f1618f5c56baa97084a41ae17e801d46ab9`.
Compare with the 2026-09-06 stringent generation archive.

| Setting | Library control | Earlier stringent candidate |
|---|---|---|
| Ge/Te valence | 14 / 16 | 22 / 24 |
| Ladder, both elements | 1s1p1d -> 2s2p2d1f -> 3s3p3d2f | 2s2p1d -> 4s4p2d1f -> 6s6p3d2f |
| Physical AO/atom | 41 | 53 |
| Four-atom AO / electrons / occupied | 164 / 60 / 30 | 212 / 92 / 46 |
| Training Ecut | 100 Ry | 150 Ry |
| Ge PW dimer/trimer bands | 22 / 29 | 30 / 41 |
| Te PW dimer/trimer bands | 20 / 28 | 28 / 40 |
| Level1 reference bands, Ge/Te | 18 / 16 | 26 / 24 |
| Shared | Rcut10; electronic sigma0.01; max_steps9000; Level2/3 auto+fix | Same |

Ge references use dimers at 1.8,2.0,2.4,3.0,4.0 Angstrom and trimers at
1.9,2.2,2.8; Te uses dimers2.2,2.6,3.1,3.6,4.5 and trimers2.4,2.8,3.4.
These geometries were unchanged. Both effective archives specify dr0.01,
lr0.03 and cal_T=false; the older library optimizer version, seed and
spillage history are not supplied by those info directories.

The stringent Ge includes 3s/3p and Te includes 4s/4p as valence, explaining
the extra eight electrons per atom and the larger starting ladder. This does
not prove that the expanded candidate was well optimized for periodic RI.
Both sets have same-center radial Gram close to identity; there is no
evidence of severe same-center linear dependence from that test.

Library EXX job3295114 has finite201x164 bands, gap3.90577eV, PBE0.86874eV
and zero high-state intrusions, without a positive local-inverse threshold.
It is a numerical diagnostic, not an independent EXX accuracy benchmark.
PP+NAO+ABFS and the inverse setting differ from earlier positive-threshold
controls; this is NOT an orbital-only causal experiment. Do not promote
q14/q16, 100Ry, 3s3p3d2f or no-inverse-threshold to universal defaults.

Case evidence:
`/Users/ghj/同步空间/AITP_project/2d_gw/applications_20260905/production_20260908/gete_library_tzdp10_noinv_20260908/generation_audit_20260909/`
