# GW Route

Use this reference after `oh-my-librpa` has already classified the task as GW.

## Route selection

Choose the workflow by system type:

- `molecule` -> default short route `SCF -> LibRPA`
- `solid` -> full route `SCF -> pyatb/DF -> NSCF -> preprocess -> LibRPA`
- `2D` -> start from the `solid` route, but ask for the intended Coulomb treatment, vacuum setup, and k-mesh expectations before submission; do not silently invent 2D-specific truncation settings

If the case is missing PP/NAO/ABFS files, pull them from the bundled asset library via `references/pp-nao-abfs-library.md` before generating new inputs.

If the user explicitly requests regenerated ABFS, or if the requested PP family / orbital radius / orbital tier is not present in the bundled library, switch to `references/abfs-generation.md` instead of silently reusing an approximate `.abfs` bundle.

If the case uses a locally merged ABACUS checkout or locally patched helper scripts, also apply `references/abacus-merge-compat.md`.

Before submitting any reused GW case bundle, run `scripts/intake_preflight.sh` and fix every compatibility failure first. Do not submit first and debug deprecated input keys later.

For reused periodic GW cases on the current `df` ABACUS route, reject these stale keys during the compatibility audit instead of letting NSCF fail remotely:

- `exx_use_ewald`
- `cs_inv_thr`
- `exx_spencer_type`
- `out_bandgap`

## Task defaults

Set or verify these `librpa.in` defaults unless a stronger empirical rule overrides them:

- `task = g0w0`
- `nfreq = 16`
- `use_soc = 0/1` according to the chosen spin/SOC branch
- `option_dielect_func = 3`
- `replace_w_head = t`
- `use_scalapack_gw_wc = t`
- `use_scalapack_ecrpa = t`
- `parallel_routing = libri`
- `vq_threshold = 0`
- `sqrt_coulomb_threshold = 0`
- `use_fullcoul_exx = f`

This matches the LibRPA 0.7.0 default and its ABACUS GW regressions. Enable full-Coulomb EXX only as an explicit physical-definition override with a definition-matched benchmark.
- `output_gw_sigc_mat_rf = f`
- `libri_chi0_threshold_C = 1e-4`
- `libri_chi0_threshold_G = 1e-5`
- `libri_exx_threshold_V = 1e-1`
- `libri_exx_threshold_C = 1e-4`
- `libri_exx_threshold_D = 1e-4`
- `libri_g0w0_threshold_C = 1e-5`
- `libri_g0w0_threshold_G = 1e-5`
- `libri_g0w0_threshold_Wc = 1e-6`

Only flip `output_gw_sigc_mat_rf` to `t` when the user explicitly asks to open NSCF band continuation.
When materializing a fresh GW case for that request, pass `--enable-nscf-band-continuation true`.

- for template-generated inputs that use explicit lattice vectors, set `latname = user_defined_lattice`

Time-frequency grid guardrails:

- if `tfgrid_type = minimax` or the key is omitted and LibRPA will use the default `minimax`, require `nfreq >= 6`
- reason: the LibRPA minimax path uses GreenX-backed minimax grids and the supported grid count starts at `6`; do not treat `nfreq < 6` as a valid minimax setup
- if a quick functional smoke test really needs `nfreq < 6`, explicitly switch away from minimax, for example to `tfgrid_type = evenspaced_tf` or `tfgrid_type = evenspaced`
- never present `nfreq < 6` as a production or convergence-quality GW/RPA setting; it is only acceptable for narrow path-validation smoke tests with a non-minimax grid

Before selecting PP / NAO / ABFS assets for a GW case, enforce the matching rule from `references/pp-nao-abfs-library.md`: pseudopotential, atomic basis, and auxiliary basis must correspond to the same intended setup and must not be mixed casually across unrelated PP families.

For shrink GW cases that use `ABFS_ORBITAL`, require the `.abfs` header to match the paired `.orb` radius cutoff. If the active `.orb` contains `f`, require the `.abfs` header to keep nonzero `f` and `g`.

For SOC cases, do not assume the current library is sufficient: SOC pseudopotentials are not yet bundled by default, so if the required SOC PP assets are missing, stop and ask the user to upload them.

If SOC is enabled, require SOC pseudopotentials. Never continue a SOC GW case with non-SOC pseudopotentials.

## Spin / SOC alignment

Keep all files consistent:

- Collinear spin, no SOC
  - `INPUT`: `nspin = 2`, `lspinorb = 0`
  - `get_diel.py`: matching `nspin`, `use_soc = False`
  - `preprocess_abacus_for_librpa_band.py`: `use_soc = False`
  - `librpa.in`: `use_soc = 0`

- Noncollinear with SOC
  - `INPUT`: `nspin = 4`, `lspinorb = 1`
  - `get_diel.py`: matching `nspin`, `use_soc = True`
  - `preprocess_abacus_for_librpa_band.py`: `use_soc = True`
  - `librpa.in`: `use_soc = 1`

## Basis-count / nbands rule

Verify `nbands` against the basis size before execution.

Count basis functions from `.orb` files with:

- degeneracy by angular momentum: `s=1`, `p=3`, `d=5`, `f=7`, ...
- multiply each channel by radial multiplicity
- sum over all atoms in the primitive cell
- if SOC is enabled, multiply the final total by `2`

Then:

- set `nbands` in `INPUT_scf`
- set the same `nbands` in `INPUT_nscf` when that file is part of the route
- cross-check against ABACUS `NBASE`
- stop and explain the counting rule if any ambiguity remains

## Molecule branch

Use the conservative short route by default.

Required settings and checks:

- set `KPT = 1 1 1`
- treat `gamma_only` as route-aware, not a universal hard rule
- use official ABACUS input names
- do not run `pyatb`, `NSCF`, or `preprocess_abacus_for_librpa_band.py`; the short route is `SCF -> LibRPA`
- set `replace_w_head = f`
- set `use_symmetry_exx = f` and `use_symmetry_gw = f`; do not require input symmetry sidecars on this route
- keep `output_gw_sigc_mat_rf = f`
- for the tested short smoke path, materialize the route with:
  - `scripts/materialize_gw_template.sh --case-dir <case_dir> --system-type molecule --needs-nscf false --needs-pyatb false --use-shrink-abfs false`
- keep `out_mat_xc 1`, `out_librpa_reader_version 1`, `exx_singularity_correction = massidda`, `exx_pca_threshold 1e-6`, `exx_cs_inv_thr 1e-5`
- keep LibRPA on explicit reader-v1 names: `prefix_coul_full = v1_coulomb_full_iq_`, `prefix_coul_cut = v1_coulomb_cut_iq_`, `prefix_eigvecs_scf = KS_eigenvector`, `prefix_lri_coeff = v1_Cs_data_`, `prefix_lri_coeff_shrink = v1_Cs_shrinked_data_`, `prefix_shrink_sinvS = v1_shrink_sinvS_`, `fn_basis_wfc = basis_wfc_out`, `fn_basis_aux = basis_aux_out`, `fn_basis_aux_shrink = basis_aux_shrink_out` when `use_shrink_abfs = t`, `fn_eigocc_scf = band_out`, `fn_vxc_scf = vxc_out`, `version_coul_reader = 1`, `version_lri_reader = 1`
- keep `use_cholesky_gw_wc = t`, `use_elpa_sqrt_coulomb = t`, `use_kpara_scf_eigvec = t`, and `libri_chi0_collect_max_bytes = 2147483648`
- set `exx_ccp_rmesh_times` equal to `rpa_ccp_rmesh_times` for molecular GW
- do not enable `out_chg`, `out_mat_r`, or `out_mat_hs2` on that short route
- copy `OUT.ABACUS/vxc_out.dat` to `./vxc_out` after SCF
- stop before LibRPA unless `v1_coulomb_full_iq_*`, `v1_coulomb_cut_iq_*`, `v1_Cs_data_*`, and `KS_eigenvector_*.dat` exist

## Solid branch

Use the full periodic route.

Required checks and stages:

- ask how many k-points to use in `KPT`; default to `8 8 8`
- require explicit `KPT_nscf`
- prefer the updated `get_diel.py` and `preprocess_abacus_for_librpa_band.py` copies that match the merged ABACUS branch; do not fall back to stale helpers that assume only legacy `EFERMI` parsing or one fixed wavefunction filename pattern
- treat the periodic GW helper quartet as inseparable: `perform.sh`, `get_diel.py`, `output_librpa.py`, and `preprocess_abacus_for_librpa_band.py`
- when cloning a prior GW case into a fresh run directory, copy the full helper quartet together or re-materialize it from the template; never copy only a subset
- only enable `output_gw_sigc_mat_rf = t` when the user explicitly asks to open NSCF band continuation; for a materialized case, pass `--enable-nscf-band-continuation true`
- after SCF, run pinned PyATB `enable_head_wing` to generate `pyatb_librpa_df`; for LibRPA `v0.7.0`, both `KS_eigenvector_*.dat` and `velocity_matrix` are reader-v1 binary files
- then run NSCF
- then run `preprocess_abacus_for_librpa_band.py`
- then run `LibRPA`
- prefer `run_gw_workflow.sh` when available so stage execution and verification stay in one flow

Helper-file rule:

- do not mix the roles of `get_diel.py` and `output_librpa.py`
- keep the newer parser/fallback improvements in `get_diel.py`, but do not rewrite its `__main__` into an IBZ-only exporter based on legacy symmetry sidecars
- treat `perform.sh`, `get_diel.py`, `output_librpa.py`, and `preprocess_abacus_for_librpa_band.py` as a matched helper quartet; patch them intentionally, not piecemeal

## Periodic symmetry lane

Use this lane only for periodic GW when the user explicitly asks to enable symmetry or when the case already has a symmetry-enabled `stru_out` from ABACUS.

Do not use this lane for SOC cases. When SOC is enabled, keep the ABACUS side on `symmetry = -1` and disable `use_symmetry_exx` / `use_symmetry_gw` in `librpa.in`.

Required settings:

- `INPUT_scf`: keep `rpa 1` and set `symmetry 1`
- `INPUT_nscf`: keep `symmetry -1`
- if the case keeps a standalone band `INPUT`, keep that file on `symmetry -1` as well
- `librpa.in`: set `use_symmetry_exx = t` and `use_symmetry_gw = t`; reject old OML symmetry spellings because LibRPA 0.7.0 does not parse them as aliases
- leave `input_symmetry_convention = auto` unless a case needs an explicit convention for old inputs
- require `stru_out` from the same symmetry-enabled SCF; current LibRPA rebuilds rotations from the symmetry metadata in that file
- do not require or copy legacy `irreducible_sector.txt`, `symrot_R.txt`, `symrot_k.txt`, or `symrot_abf_k.txt`

Required stage handling:

- after the symmetry-enabled SCF, verify `stru_out` exists in the LibRPA working directory
- for the current `head/wing` lane, always generate `pyatb_librpa_df` on the full regular k-grid; LibRPA maps `pyatb_librpa_df/k_path_info` onto its active k-list, so do not feed IBZ k-points or star weights from legacy sidecars into `output_librpa.py` by default
- keep the root-level `stru_out`, `band_out`, `k_path_info`, `velocity_matrix`, and `KS_eigenvector_*.dat` aligned with the same ABACUS run; do not overwrite those root files with the full-BZ `pyatb_librpa_df/*` copies
- if a temporary full-BZ regeneration is needed for `pyatb_librpa_df`, do it in isolation and copy back only the `pyatb_librpa_df/` directory unless the user explicitly requests a root-level replacement
- fail fast if `stru_out` is missing

Comparison rule:

- for symmetry-vs-no-symmetry checks, keep `nbands`, k-meshes, shrink settings, thresholds, PP/NAO/ABFS files, helper scripts, and post-processing identical
- only patch the symmetry-related keys and the `stru_out`-producing SCF stage

## Shrink strategy

Use shrink by default for the generic periodic GW lane.

Do not force shrink onto the tested short molecular smoke route.

Generic shrink lane:

- `use_shrink_abfs = t`
- `rpa 1`
- `exx_pca_threshold 10`
- `shrink_abfs_pca_thr 1e-4`
- `shrink_lu_inv_thr 1e-3`
- `exx_cs_inv_thr 1e-5`

Additional rule:

- when shrink is enabled, require `ABFS_ORBITAL` in `STRU`
- if the user provides `.abfs` files, use those names directly
- keep ABACUS-side shrink and LibRPA-side shrink strictly synchronized as a host-independent workflow invariant
- if the case bundle was generated from a shrink SCF or already contains shrink artifacts such as legacy `Cs_shrinked_data_*` / `shrink_sinvS_*` or v1 `v1_Cs_shrinked_data_*` / `v1_shrink_sinvS_*`, require `librpa.in: use_shrink_abfs = t`
- if the case bundle was generated from a no-shrink SCF, require `librpa.in: use_shrink_abfs = f`
- never "turn off shrink only in librpa.in" while reusing a shrink-generated ABACUS bundle; treat that as an invalid mixed workflow

## No-shrink + pair-correction comparison lane

Use this lane when the user wants a fair comparison against a shrink baseline while testing whether pair correction can recover similar GW quality without shrink.

Required settings:

- keep the same `KPT_scf`, `KPT_nscf`, `nbands`, pseudopotentials, NAOs, and helper scripts as the comparison baseline
- `librpa.in`: `use_shrink_abfs = f`
- `INPUT_scf`: do not set `shrink_abfs_pca_thr`
- `INPUT_scf`: do not set `shrink_lu_inv_thr`
- do not add `ABFS_ORBITAL` just for this lane

If pair correction is enabled in this lane:

- `INPUT_scf`: `out_pair_embedding_metric 1`
- `INPUT_scf`: `pair_embedding_distance_cut <value>`
- `librpa.in`: `use_pair_embedding_corr = t`
- `librpa.in`: `pair_embedding_distance_cut = <same value>`
- `librpa.in`: `pair_embedding_metric_thr = <value>`

Failure rule:

- if `use_shrink_abfs = f` but `INPUT_scf` still contains shrink-only keys, treat that as a mixed lane and fix the inputs before submission
- if `use_shrink_abfs = f` but the bundle still contains shrink outputs such as legacy `Cs_shrinked_data_*` / `shrink_sinvS_*` or v1 `v1_Cs_shrinked_data_*` / `v1_shrink_sinvS_*`, also treat that as a mixed lane and block submission

## Stage success criteria

Use these generic checks.

### SCF success

- `OUT.ABACUS/running_scf.log` exists
- the log contains both `Finish Time` and `Total Time`
- `OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart` exists and is non-empty
- when the periodic symmetry lane is enabled, `stru_out` exists and comes from the same symmetry-enabled SCF

### pyatb success

- `pyatb_librpa_df/` exists
- `pyatb_librpa_df/band_out` exists
- at least one `pyatb_librpa_df/KS_eigenvector_*.dat` exists

### NSCF success

- `OUT.ABACUS/running_nscf.log` exists
- the log contains both `Finish Time` and `Total Time`
- either `OUT.ABACUS/eig.txt` or `OUT.ABACUS/eig_occ.txt` exists and is non-empty

### preprocess success

- `band_kpath_info` exists
- at least one `band_KS_*` file exists
- at least one `band_vxc*` file exists

### LibRPA success

Accept either periodic or molecular success markers:

- periodic: a rank-0 output file (for example `librpa_para_nprocs_*_myid_0.out` or `LibRPA*.out`) reaches `Timer stop:  total.` or `libRPA finished successfully`, and `GW_band_spin_*.dat` exists
- molecular: output contains `libRPA finished successfully` and required reader-v1 outputs such as `band_out`, `vxc_out`, `v1_Cs_data_*`, `v1_coulomb_full_iq_*`, and `v1_coulomb_cut_iq_*` exist

### LibRPA running

- rank-0 output exists
- there is no final completion marker yet
- the file is still growing

### LibRPA failed

- there is no final completion marker
- and the output file is no longer growing, or the output file is missing

## Post-processing

For periodic GW post-processing, prefer `plot_gw_band_paper.py` and load `rules/cards/periodic-gw-plotting.yml` before deciding any sorting policy.

- inputs: `GW_band_spin_*`, `band_out`, `band_kpath_info`, `KPT_nscf`
- outputs: near-gap PNG/PDF plus a short text summary
- use a restricted near-gap CBM search instead of a blind global conduction-band search
- if reordering is needed for plotting, never globally reorder the full band table; sort only within the plotted manifold at each k-point
- for occupied-only plots, sort only the occupied manifold
- for near-gap plots, sort occupied and low-lying conduction manifolds separately

## Reporting requirement

For every recommendation or action, report:

- why this is needed
- what risk it addresses
- how to validate it cheaply
- what the next stage is

After each verified stage, update the task Markdown logs and send the user a short stage summary.
