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

Do not keep both the old and new EXX keys in the same input.

## Helper-script deltas

### `get_diel.py`

The updated script accepts both Fermi-energy spellings from `OUT.ABACUS/running_scf.log`:

- `E_FERMI`
- legacy `EFERMI`

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
