# ABFS_ORBITAL Recipe

Status: partially captured from the user's current teaching notes. Keep exact wording and fill the remaining `TODO:` items only from later user-approved instructions.

## Scope

- workflow family: `ABACUS -> LibRPA`
- code branch / version: `https://github.com/AroundPeking/abacus_abf_gen/tree/develop`
- host or environment: reference input lives on `66` server
- applies to: generating `.abfs` auxiliary-basis files for later GW / EXX runs that use `ABFS_ORBITAL`

## Prerequisites

- This is a **missing-asset generation recipe**, not a step to run for every
  material. First query the LibRPA materials database through its MCP server:
  `list_basis_sets(element=...)` for every recorded PP/NAO/ABFS/for_aux set and
  its payload hashes, `search_materials(...)` for a related material that
  already binds one, `get_material(record_id)` for the exact `set_id`. Reuse a
  hash-matched element bundle instead of regenerating. An absent catalog link
  or a missing original for_aux log is not proof that the asset does not
  exist, so re-query by element before starting a run.
- The retired local trees `2d_gw_pp_basis_library` and
  `2d_gw/pp_basis_library` must not be referenced: all 263 of their
  PP/NAO/ABFS payloads were confirmed present in the database by hash and the
  directories were deleted on 2026-11-05.
- A wrapper failure must be distinguished from a native export failure before
  any retry, and a completed export is archived into the database with
  `librpa-database-intake` rather than left in the material run folder.

- Use `abacus_abf_gen` from branch `develop`.
- Use the input under `/home/ghj/basis_abacus/SIAB/abfs/abacus_abfs/Ca` on `66` only as a template reference.
- Do not describe that path as the direct input source for every case; instead, write a fresh template for the target atom by following the same pattern.
- The `STRU` used for auxiliary-basis generation must use the same:
  - `NUMERICAL_ORBITAL` files
  - pseudopotential files
  as the later GW calculation.

## Required inputs

- `INPUT`
- `KPT`
- `STRU`
- pseudopotential files matching the GW run
- numerical orbital files matching the GW run
- a `for_aux` version of the GW basis files
- a one-shot ABACUS submission script such as `run_abacus.sh` or the sample `run_HR.sh`

## Procedure

1. Start from `abacus_abf_gen` branch `develop`.
2. Choose the target element whose auxiliary basis will be generated.
3. Write a template input by following the style of:
   - `/home/ghj/basis_abacus/SIAB/abfs/abacus_abfs/Ca`
4. Use a single-atom `STRU` for the target element.
5. In the generation `STRU`, do not add `ABFS_ORBITAL`.
6. `ABFS_ORBITAL` is only for the later GW / EXX calculation that consumes the generated `.abfs` files.
7. Use `KPT = 1 1 1`.
8. The generation run only needs `ABACUS`; do not run `LibRPA` for the `.abfs` generation step.
9. Execute the run by following the one-shot ABACUS submission script in the template workflow.
10. That script only needs to run one ABACUS job successfully.
11. In the auxiliary-basis generation input, the key control parameter for how many auxiliary functions are produced is:
   - `exx_pca_threshold` in `INPUT`
12. The usual value for this parameter is:
   - `exx_pca_threshold = 1e-4`
13. In this special ABACUS branch, turning on `rpa` in `INPUT` makes ABACUS generate the auxiliary basis automatically.
14. Preserve the reviewed template settings for a matched control. For a new PP/element, verify its cutoff, cell units/size, electron count, spin and solver compatibility before inheriting numeric values. The Ca sample is a starting example, not universal convergence evidence; do not silently change an existing accepted control.
15. Prepare the basis used for auxiliary-basis generation from the GW basis by adding `for_aux`.
16. The `for_aux` strategy depends on the highest angular momentum already present in the production GW basis:
   - if the production basis stops at `d`, add one extra `f` orbital and one extra `g` orbital
   - if the production basis already contains `f`, add only one extra `g` orbital
17. In filename terms, the `for_aux` basis is named by taking the original basis name and appending the actually added channels, for example:
   - `...3d -> ...3d1f1g`
   - `...1f -> ...1f1g`
18. These extra auxiliary-only channels are used only when generating `.abfs`.
19. Do not put those extra `for_aux` channels into the numerical orbital set used in the final GW calculation.
20. For an auxiliary-basis convergence test when the production orbital basis stops at `d`, do not use an increasingly small `exx_pca_threshold` as the primary enlargement ladder. Hold `exx_pca_threshold = 1e-4` fixed and increase the auxiliary-generation angular hierarchy in two controlled steps:
   - intermediate: append one smooth auxiliary-only `f` channel, `...3d -> ...3d1f`
   - endpoint: append one smooth auxiliary-only `g` channel to the same intermediate basis, `...3d1f -> ...3d1f1g`
21. Keep the pseudopotential, physical production orbital, radial cutoff, Gaussian construction rule, generator binary, box, grid, and all downstream RPA settings fixed between the `1f` and `1f1g` points. Record the generated `.abfs` hash and actual `naux` for each point.
22. Distinguish the two thresholds explicitly:
   - `exx_pca_threshold` controls generation of the product-PCA `.abfs` and is fixed at `1e-4` in this angular-hierarchy test
   - LibRPA `sqrt_coulomb_threshold` controls spectral handling of the Coulomb matrix and must remain at its separately validated fixed value
23. Accept `1f -> 1f1g` convergence only when the molecular and atomic absolute RPA correlation energies and their binding/dissociation combination pass the declared tolerance, and when the full-Coulomb spectrum and retained rank remain numerically stable. Adding `g` is not accepted merely because it increases `naux`; reject or diagnose the point if it introduces new negative or near-null Coulomb directions.
24. Use a single-atom `STRU` template:
   - one atom only
   - reviewed target-specific cell with explicit lattice units; the historical orthogonal `15 x 15 x 15` cell is a template example, not a universal acceptance requirement
   - replace the element name with the target element
   - replace the pseudopotential filename with the matching target-element pseudopotential
   - replace the orbital filename with the matching target-element `for_aux` orbital
   - atomic position at `0 0 0`
25. Use the `k111` `KPT` template from the reference workflow.
26. Run `ABACUS` to produce `*.abfs`.
27. Use the `66` server sample script shape as the reference.
28. In the current `Ca` sample directory, the script is named `run_HR.sh`.
29. Its essential logic is:
   - request one node
   - set `OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK`
   - define the ABACUS executable path
   - launch one ABACUS rank with `mpirun -n 1 -ppn 1 ... > abfs.out`
30. `SBATCH` resource lines should be adjusted per server; for this auxiliary-generation workflow, one node is usually enough.
31. The exact shell command can stay encapsulated in the submission script; for this recipe, the minimum requirement is only that one ABACUS run is launched and finishes.

## Preferred `for_aux` orbital route for `1f1g`

When the extra `f` and `g` channels are only meant for later `ABFS_ORBITAL` generation, prefer a constrained Gaussian route over free optimization of high-angular-momentum channels.

Reason:

- free optimization of `g` is often under-constrained and can produce oscillatory or non-physical shapes
- the auxiliary-generation use case needs smooth, stable, localized `f/g` channels more than it needs atomically "physical" high-`l` eigenfunctions
- `66` contains existing Gaussian-style `1f1g` examples such as:
  - `/home/ghj/basis_abacus/SIAB/abfs/abacus_abfs/B/B_gga_8au_100Ry_3s3p2d1f1g_gaus.orb`
  - `/home/ghj/basis_abacus/SIAB/abfs/abacus_abfs/B/B_gga_8au_100Ry_3s3p2d1f1g_gaus_extend.orb`
  - `/home/ghj/basis_abacus/SIAB/abfs/abacus_abfs/N/N_gga_8au_100Ry_3s3p2d1f1g_gaus.orb`

### Gaussian form

Use radial functions of the form:

```text
R_l(r) = r^l * sum_i c_i * exp(-alpha_i * r^2)
```

and then apply a smooth radial cutoff near `rcut`.

### Parameter selection rule

Choose the Gaussian parameters by matching the peak radius of the highest existing angular-momentum channel in the physical GW basis.

1. Read the production GW `.orb` file that does not yet contain the auxiliary-only `1f1g`.
2. Find the highest existing `l` in that file, usually `d`.
3. Take the outermost zeta of that channel.
4. Measure its peak radius:
   - `r_ref = argmax |R_l(r)|`
5. Set the target Gaussian peak radii by scale:
   - `r_f = 1.10 * r_ref`
   - `r_g = 1.25 * r_f`
6. Convert target peak radius to Gaussian exponent using the single-primitive peak formula for `r^l * exp(-alpha r^2)`:
   - `alpha = l / (2 * r_peak^2)`
7. Therefore:
   - `alpha_f = 3 / (2 * r_f^2)`
   - `alpha_g = 4 / (2 * r_g^2)`

### Recommended default channel shapes

Use these defaults first:

- `f`:
  - one primitive
  - coefficient `1.0`
  - exponent `alpha_f`
- `g`:
  - one primitive
  - coefficient `1.0`
  - exponent `alpha_g`

This is the preferred `single` mode because it is nodeless and strongly constrained.

### Optional broader-tail variant

If the single primitive is too compact, add one broader primitive with the same sign:

- `alpha_2 = alpha_1 / 4`
- `c_2 = 0.30` for `f`
- `c_2 = 0.25` for `g`

This corresponds to a conservative `gaus_extend` style and is still meant to stay nodeless.

### Cutoff rule

Do not hard-truncate the Gaussian at `rcut`.
Instead, multiply it by a smooth window in the last `15%` of the radial box:

- start cutoff window at `0.85 * rcut`
- use a quintic smoothstep so the value goes smoothly to `0` at `rcut`

### Helper Source And Remote Execution

The repo-local helper script:

- `/Users/ghj/code/oh-my-librpa/scripts/generate_gaussian_aux_orb.py`

can:

- read an existing ABACUS `.orb`
- detect the highest existing `l` channel and its outermost-zeta peak radius
- append one smooth Gaussian `f` and one smooth Gaussian `g` when the input stops at `d`
- append one smooth Gaussian `g` only when the input already contains `f` but no `g`
- write a new `.orb`
- print the chosen Gaussian exponents and peak radii as JSON

The macOS path above is the source location, not an execution instruction.
Transfer a hash-pinned copy and the matched inputs to the approved server.
Run the following inside the prepared remote shell, with `REMOTE_HELPER`
set to the verified deployed script path; use `ghj-remote-ssh` for host setup.
Keep local work to inspection, transfer, parsing and plotting.

Remote example:

```bash
python3 "${REMOTE_HELPER:?set verified remote helper path}" \
  --input Si_gga_8au_100Ry_3s3p2d.orb \
  --output Si_gga_8au_100Ry_3s3p2d1f1g_gaus.orb
```

Remote broader-tail example (a separate controlled recipe, not an automatic retry):

```bash
python3 "${REMOTE_HELPER:?set verified remote helper path}" \
  --input Ga_gga_10au_150Ry_4s4p3d.orb \
  --output Ga_gga_10au_150Ry_4s4p3d1f1g_gaus_extend.orb \
  --mode extend
```

## Concrete sample on 66

Current reference directory:

- `/home/ghj/basis_abacus/SIAB/abfs/abacus_abfs/Ca`

Observed sample files:

- `INPUT`
- `KPT`
- `STRU`
- `run_HR.sh`
- `Ca_6s3p2d2f1g_pca1e-4.abfs`
- `Ca_gga_10au_150Ry_6s3p2d1f1g.orb`
- `Ca_ONCV_PBE-1.0.upf`

Observed sample `INPUT` highlights (Ca only; target-PP cutoff and box convergence must be established separately):

- `calculation scf`
- `ecutwfc 150`
- `basis_type lcao`
- `ks_solver genelpa`
- `dft_functional pbe`
- `rpa 1`
- `symmetry -1`
- `exx_separate_loop 1`
- `exx_pca_threshold 1e-4`
- `exx_ccp_rmesh_times 5`
- `exx_c_threshold 0`
- `exx_dm_threshold 0`
- `exx_schwarz_threshold 0`
- `exx_cauchy_threshold 1E-7`

Observed sample `KPT`:

```text
K_POINTS
0
Gamma
1 1 1 0 0 0
```

Observed sample `STRU` highlights:

- element: `Ca`
- pseudopotential: `Ca_ONCV_PBE-1.0.upf`
- orbital: `Ca_gga_10au_100Ry_6s3p2d.orb`
- cubic box:
  - `LATTICE_VECTORS`
  - `10 0 0`
  - `0 10 0`
  - `0 0 10`
- one atom at `0 0 0`

Keep using the user's higher-level rule for fresh templates:

- single atom
- large orthogonal box, typically `15 x 15 x 15`
- same pseudopotential and matching orbital family as the later GW run

## Output files

- target product: `*.abfs`
- Recommended naming should encode:
  - element
  - pseudopotential label
  - generated basis used for auxiliary generation, including the added `1f1g`
  - PCA threshold
  - the final number of generated auxiliary basis functions
- Example filename:
  - `Ca_sg15_6s3p2d1f1g_pca1e-10_1000.abfs`
- Observed existing sample filename:
  - `Ca_6s3p2d2f1g_pca1e-4.abfs`
- In that example:
  - `Ca` is the element
  - `sg15` is the pseudopotential label
  - `6s3p2d1f1g` is the auxiliary-generation basis, including the added `1f1g`
  - `pca1e-10` records the PCA threshold
  - `1000` is the number of generated auxiliary basis functions
- The auxiliary-basis count should be computed from the file header by counting the `spdfg...` channel totals written there with angular degeneracy:
  - `s -> 1`
  - `p -> 3`
  - `d -> 5`
  - `f -> 7`
  - `g -> 9`
  - `h -> 11`
  - `i -> 13`
  - `j -> 15`
  - `k -> 17`
- Example from `Ca_6s3p2d2f1g_pca1e-4.abfs`:
  - `17*1 + 13*3 + 11*5 + 11*7 + 7*9 + 4*11 + 4*13 + 2*15 + 1*17 = 394`

## STRU mapping

The generated `.abfs` files are later referenced in `STRU` through `ABFS_ORBITAL`.
In the later GW `STRU`, write the `.abfs` filenames in the same order as the atomic basis entries above.

```text
ABFS_ORBITAL
<abfs file for basis/species 1>
<abfs file for basis/species 2>
...
```

## Host-specific direct `jle-smooth` route on `df_iopcas_ghj`

This is a separate, direct-consumption route for `ABFS_ORBITAL`.
It does not regenerate `.abfs` through `abacus_abf_gen`.

- source template:
  - `/data/home/df_iopcas_ghj/basis_pp/jle-smooth/ORBITAL_10U.dat`
- intended use:
  - quick ABFS sensitivity tests on `df_iopcas_ghj`
  - especially when the stock generated `.abfs` set looks too aggressive and the user wants a smoother, slightly larger-than-baseline auxiliary basis

### Procedure

1. Copy `ORBITAL_10U.dat` once per target species.
2. Rename each copy to a species-specific `.abfs` filename.
3. Replace the header `Element` field with the target species label.
4. Replace each `Number of *orbital-->` header count with a truncated value.
5. Do not keep the template value `100`; that is intentionally oversized for direct use.
6. Choose the truncated counts to be only slightly larger than the previously used `ABFS_ORBITAL` header counts for the same workflow.
7. Use the edited files directly in the later GW `STRU` under `ABFS_ORBITAL`.
8. When this direct route is active, keep the later GW inputs on the explicit-ABFS lane:
   - `ABFS_ORBITAL` present in `STRU`
   - `exx_pca_threshold = 10`
   - `use_shrink_abfs = t`

### Current `alpha-MnTe` `DZP FR` example

For `/data/home/df_iopcas_ghj/gw/altermagnet` with:

- `Mn_gga_10au_100Ry_4s2p2d1f.orb`
- `Te_gga_10au_100Ry_2s2p2d1f.orb`

the previous generated `.abfs` headers were:

- `Mn`: `S9 P7 D7 F6 G5 H4 I3 J1 K1`
- `Te`: `S7 P6 D7 F6 G5 H4 I3 J1 K1`

The direct `jle-smooth` truncation used:

- `Mn`: `S10 P8 D8 F7 G6 H5 I4 J2`
- `Te`: `S8 P7 D8 F7 G6 H5 I4 J2`

with filenames:

- `Mn_jlesmooth10u_plus1_314.abfs`
- `Te_jlesmooth10u_plus1_309.abfs`

where `314` and `309` are the angular-degeneracy-weighted totals from the header counts.

### Notes

- `ORBITAL_10U.dat` is a generic smooth template and its original `Element` header is not the target species; rewrite it explicitly.
- The template observed on `df_iopcas_ghj` runs through `J` and does not carry a `K` block.
- `TODO:` record which truncation ladder gives the best occupied-state behavior once the user confirms the preferred `alpha-MnTe` result.

## Validation

- Check that the generation `STRU` is a single-atom structure for the target element.
- Check that the generation `STRU` does not contain `ABFS_ORBITAL`.
- Check that the generation `STRU` matches the reviewed target-specific cell, explicit units and atomic position. The historical `15 x 15 x 15` box with atom at `0 0 0` is an example; a reviewed alternative cell must not be rejected solely for differing from it.
- Check that the pseudopotential files used for `.abfs` generation are exactly the same as the later GW run.
- Check that the `NUMERICAL_ORBITAL` files used for `.abfs` generation are exactly the same as the later GW run, except for the extra `for_aux` channels used only during `.abfs` generation.
- Check that the `for_aux` name and actual header reflect only the channels added by the selected recipe: physical d-ending basis adds f/g; physical f-ending basis adds g only. An explicitly authorized intermediate f-only control remains distinct. Do not reject a correct g-only extension or change existing physical f functions.
- Check that the `k111` `KPT` template is used.
- Check that `rpa` is enabled in `INPUT`, because this custom ABACUS branch generates `.abfs` through that path.
- Check that `exx_pca_threshold` is set intentionally; the usual value taught by the user is `1e-4`.
- Check that newly added auxiliary-only channels appear only in the generation basis; preserve all original physical channels exactly. A physical f orbital remains in the final GW basis and must not be removed as if it were auxiliary-only.
- For Gaussian-style `1f1g`, check that the added `f/g` channels remain smooth and do not show obvious short-wavelength oscillations near the origin.
- For Gaussian-style `1f1g`, prefer `g` channels with `0` significant nodes and reject obviously multi-node or strongly oscillatory `g` shapes.
- For Gaussian-style `1f1g`, if adding `g` later worsens the downstream behavior or clearly harms occupied-state quality, drop the `g` channel instead of keeping it by default.
- Check that the `.abfs` filename records the element, pseudopotential label, basis, PCA threshold, and auxiliary-basis count in the intended form.
- Check that the auxiliary-basis count written in the filename matches the count obtained from the file header `spdfg...` totals.
- Check that the later GW `ABFS_ORBITAL` block follows the same order as the atomic basis entries it is meant to match.

## Failure modes

- Using different pseudopotentials from the later GW run invalidates the auxiliary basis.
- Using different `NUMERICAL_ORBITAL` files from the later GW run invalidates the auxiliary basis.
- Accidentally adding `ABFS_ORBITAL` into the generation `STRU` confuses the generation step with the later GW-consumption step.
- Using a non-single-atom generation `STRU` breaks the intended per-element auxiliary-basis generation workflow.
- Forgetting to enable `rpa` in `INPUT` prevents this custom ABACUS branch from generating the auxiliary basis.
- Accidentally keeping the extra `for_aux` channels in the production GW numerical orbitals mixes the auxiliary-generation basis with the physical GW basis.
- Free optimization of `g` can be under-constrained and produce oscillatory high-`l` channels even when the run finishes.
- Multi-node or strongly oscillatory Gaussian combinations defeat the purpose of the constrained Gaussian route; keep the primitive count low and keep all primitive coefficients for a given channel the same sign.
- Choosing an unintended `exx_pca_threshold` changes how many auxiliary functions are generated.
- `TODO:` add known generator failure signatures once the user provides them.
