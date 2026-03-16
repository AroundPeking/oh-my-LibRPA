# GW Route

Use this reference after `oh-my-librpa` has already classified the task as GW.

## Route selection

Choose the workflow by system type:

- `molecule` -> default short route `SCF -> LibRPA`
- `solid` -> full route `SCF -> pyatb/DF -> NSCF -> preprocess -> LibRPA`
- `2D` -> start from the `solid` route, but ask for the intended Coulomb treatment, vacuum setup, and k-mesh expectations before submission; do not silently invent 2D-specific truncation settings

If the case is missing PP/NAO/ABFS files, pull them from the bundled asset library via `references/pp-nao-abfs-library.md` before generating new inputs.

If the case uses a locally merged ABACUS checkout or locally patched helper scripts, also apply `references/abacus-merge-compat.md`.

## Task defaults

Set or verify these `librpa.in` defaults unless a stronger empirical rule overrides them:

- `task = g0w0_band`
- `nfreq = 16`
- `use_soc = 0/1` according to the chosen spin/SOC branch
- `option_dielect_func = 3`
- `replace_w_head = t`
- `use_scalapack_gw_wc = t`
- `use_scalapack_ecrpa = t`
- `parallel_routing = libri`
- `vq_threshold = 0`
- `sqrt_coulomb_threshold = 0`
- `use_fullcoul_exx = t`
- `output_gw_sigc_mat_rf = t`
- `libri_chi0_threshold_C = 1e-4`
- `libri_chi0_threshold_G = 1e-5`
- `libri_exx_threshold_V = 1e-1`
- `libri_exx_threshold_C = 1e-4`
- `libri_exx_threshold_D = 1e-4`
- `libri_g0w0_threshold_C = 1e-5`
- `libri_g0w0_threshold_G = 1e-5`
- `libri_g0w0_threshold_Wc = 1e-6`

- for template-generated inputs that use explicit lattice vectors, set `latname = user_defined_lattice`

Before selecting PP / NAO / ABFS assets for a GW case, enforce the matching rule from `references/pp-nao-abfs-library.md`: pseudopotential, atomic basis, and auxiliary basis must correspond to the same intended setup and must not be mixed casually across unrelated PP families.

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
- do not run `pyatb`
- set `replace_w_head = f`
- for the tested short smoke path, materialize the route with:
  - `oh-my-librpa/scripts/materialize_gw_template.sh --case-dir <case_dir> --system-type molecule --needs-nscf false --needs-pyatb false --use-shrink-abfs false`
- keep `out_mat_xc 1`, `exx_singularity_correction = massidda`, `exx_pca_threshold 1e-6`, `rpa_ccp_rmesh_times 6`, `exx_ccp_rmesh_times 3`, `exx_cs_inv_thr 1e-5`
- do not enable `out_chg`, `out_mat_r`, or `out_mat_hs2` on that short route
- copy `OUT.ABACUS/vxc_out.dat` to `./vxc_out` after SCF
- stop before LibRPA unless at least one `coulomb_mat_*.txt` file exists

## Solid branch

Use the full periodic route.

Required checks and stages:

- ask how many k-points to use in `KPT`; default to `8 8 8`
- require explicit `KPT_nscf`
- prefer the updated `get_diel.py` and `preprocess_abacus_for_librpa_band.py` copies that match the merged ABACUS branch; do not fall back to stale helpers that assume only legacy `EFERMI` parsing or one fixed wavefunction filename pattern
- after SCF, run `pyatb` to generate `pyatb_librpa_df`
- then run NSCF
- then run `preprocess_abacus_for_librpa_band.py`
- then run `LibRPA`
- prefer `run_gw_workflow.sh` when available so stage execution and verification stay in one flow

## Periodic symmetry lane

Use this lane only for periodic GW when the user explicitly asks to enable symmetry or when the case already contains ABACUS symmetry sidecars.

Required settings:

- `INPUT_scf`: keep `rpa 1` and set `symmetry 1`
- `INPUT_nscf`: keep `symmetry -1`
- if the case keeps a standalone band `INPUT`, keep that file on `symmetry -1` as well
- `librpa.in`: set `use_abacus_exx_symmetry = t` and `use_abacus_gw_symmetry = t`
- if `use_shrink_abfs = t`, require `symrot_abf_k.txt` together with `irreducible_sector.txt`, `symrot_R.txt`, and `symrot_k.txt`

Required stage handling:

- generate the symmetry sidecars from the same SCF that produces the Coulomb and density-matrix inputs
- after the symmetry-enabled SCF, verify the sidecars exist under `OUT.ABACUS/`
- copy the sidecars into the LibRPA working directory before `preprocess_abacus_for_librpa_band.py` and `LibRPA`
- fail fast if any required sidecar is missing

Comparison rule:

- for symmetry-vs-no-symmetry checks, keep `nbands`, k-meshes, shrink settings, thresholds, PP/NAO/ABFS files, helper scripts, and post-processing identical
- only patch the symmetry-related keys and sidecar staging

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

## Stage success criteria

Use these generic checks.

### SCF success

- `OUT.ABACUS/running_scf.log` exists
- the log contains both `Finish Time` and `Total Time`
- `OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart` exists and is non-empty
- when the periodic symmetry lane is enabled, `OUT.ABACUS/irreducible_sector.txt`, `OUT.ABACUS/symrot_R.txt`, `OUT.ABACUS/symrot_k.txt`, and `OUT.ABACUS/symrot_abf_k.txt` all exist

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
- molecular: output contains `libRPA finished successfully` and required outputs such as `band_out`, `vxc_out`, and `coulomb_mat_*.txt` exist

### LibRPA running

- rank-0 output exists
- there is no final completion marker yet
- the file is still growing

### LibRPA failed

- there is no final completion marker
- and the output file is no longer growing, or the output file is missing

## Post-processing

For periodic GW post-processing, prefer `plot_gw_band_paper.py`.

- inputs: `GW_band_spin_*`, `band_out`, `band_kpath_info`, `KPT_nscf`
- outputs: near-gap PNG/PDF plus a short text summary
- use a restricted near-gap CBM search instead of a blind global conduction-band search

## Reporting requirement

For every recommendation or action, report:

- why this is needed
- what risk it addresses
- how to validate it cheaply
- what the next stage is

After each verified stage, update the task Markdown logs and send the user a short stage summary.
