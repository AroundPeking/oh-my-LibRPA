# ABACUS Merge Compatibility (2026-03-12)

Use this reference when the workflow is based on a locally merged ABACUS checkout or locally patched helper scripts:

- merged ABACUS source tree: `<merged-abacus-root>`
- current local helper-script source of truth:
  - `<path-to-get_diel.py>`
  - `<path-to-preprocess_abacus_for_librpa_band.py>`
- repository template copies updated to match that baseline:
  - `templates/abacus-librpa-gw/template/get_diel.py`
  - `templates/abacus-librpa-gw/template/preprocess_abacus_for_librpa_band.py`

## Input-key deltas

Apply these updates to generated or patched workflow inputs:

- when the case uses explicit lattice vectors, set `latname = user_defined_lattice`
- replace old `exx_use_ewald 1` with `exx_singularity_correction = massidda`
- replace old `cs_inv_thr` with `exx_cs_inv_thr`
- drop stale `exx_spencer_type`
- drop invalid `out_bandgap`

Do not keep both the old and new EXX keys in the same input.

## Mandatory compatibility audit for reused cases

When a case bundle was cloned from an older ABACUS run, audit `INPUT_scf` and `INPUT_nscf` before any submission.

Block submission if either file still contains:

- `exx_use_ewald`
- `cs_inv_thr`
- `exx_spencer_type`
- `out_bandgap`

For any input file that actively sets `rpa 1`, require:

- `exx_singularity_correction massidda`

This rule is stage-local:

- if `INPUT_scf` has `rpa 1`, require `massidda` there
- if `INPUT_nscf` comments out `rpa`, do not force `massidda` there just for style

For periodic hybrid-functional runs such as `HSE`, `PBE0`, or other non-`rpa` EXX jobs:

- do not inherit the `massidda` requirement from the GW/RPA route just because the case also uses EXX
- do not copy tiny test-lane values such as `exx_hybrid_step = 2` into a production SCF/NSCF run without re-checking convergence intent
- if the user did not request a special hybrid stepping policy, prefer leaving `exx_hybrid_step` unset rather than forcing a short debug value

## Pair-correction lane

When `librpa.in` enables `use_pair_embedding_corr = t`, require:

- `INPUT_scf`: `out_pair_embedding_metric 1`
- `INPUT_scf`: `pair_embedding_distance_cut <value>`
- `librpa.in`: `pair_embedding_distance_cut = <same value>`
- `librpa.in`: `pair_embedding_metric_thr = <value>`

For the intended no-shrink comparison lane:

- keep `use_shrink_abfs = f` in `librpa.in`
- remove `shrink_abfs_pca_thr` and `shrink_lu_inv_thr` from `INPUT_scf`
- do not add `ABFS_ORBITAL` just to “help” pair correction
- keep k-mesh, `nbands`, helper scripts, and other GW thresholds aligned with the comparison baseline

## Helper-script deltas

### `get_diel.py`

The updated script accepts both Fermi-energy spellings from `OUT.ABACUS/running_scf.log`:

- `E_FERMI`
- legacy `EFERMI`

Keep this distinction explicit:

- parser and wavefunction-fallback improvements belong in `get_diel.py`
- `output_librpa.py` is the writer for `pyatb_librpa_df`
- do not conflate those roles when patching periodic GW helpers

For the current periodic `head/wing` lane:

- do not change `get_diel.py` into an IBZ-only `pyatb_librpa_df` exporter based on legacy symmetry sidecars
- keep `pyatb_librpa_df` on the full regular k-grid
- do not overwrite root `stru_out`, `band_out`, `k_path_info`, `velocity_matrix`, or `KS_eigenvector_*.dat` with `pyatb_librpa_df/*`; those root files must remain compatible with the ABACUS run that LibRPA reads

### `preprocess_abacus_for_librpa_band.py`

The updated script resolves multiple wavefunction filename patterns instead of assuming one fixed ABACUS export name.

Current lookup behavior:

- SOC:
  - `wfs12k<ik>_nao.txt`
  - `wfk<ik>s4_nao.txt`
- non-SOC, `nspin = 1`:
  - `wfs1k<ik>_nao.txt`
  - `wfs1_nao.txt`
  - `wfk<ik>_nao.txt`
- non-SOC, `nspin = 2`:
  - `wfs<isp>k<ik>_nao.txt`
  - `wfs<isp>_nao.txt`
  - `wfk<ik>s<isp>_nao.txt`

It also reads `KPT.info` from the ABACUS output directory and infers `nspins` from `vxc_out.dat`.

## Operational rule

For post-merge GW-band preparation, prefer these updated helpers and updated template copies.

If a case breaks after the merge, check for stale helper scripts before changing physics parameters.
