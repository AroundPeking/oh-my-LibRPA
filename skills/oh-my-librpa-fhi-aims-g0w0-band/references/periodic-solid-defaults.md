# Periodic-Solid Defaults for FHI-Aims + LibRPA G0W0 Band

Use this reference when staging or preparing a periodic-solid `FHI-aims + LibRPA` single-shot GW case.

## Geometry

- `geometry.in` is interpreted in Angstrom
- periodic solids use `lattice_vector`
- atomic coordinates may use either:
  - `atom`
  - `atom_frac`
- if an ABACUS comparison case exists, preserve the same lattice and atomic positions unless the user explicitly asks to diverge

## Species Defaults

- default species family: `defaults_2020/intermediate_gw`
- if `control.in` is absent, generate the species blocks from the active element list in `geometry.in`
- do not mix species tiers from unrelated defaults unless the user explicitly asks for it

## Minimal `control.in` Expectations

An auto-generated periodic-solid `control.in` should include:

- a periodic FHI-aims global header
- a single-shot `g0w0` setup
- `k_grid`
- band-path output lines
- the species blocks from `intermediate_gw`

When no trusted reference case exists, prefer a compact header that can be audited easily. Typical anchors are:

- `xc pbe`
- `relativistic atomic_zora scalar`
- `occupation_type gaussian 0.0001`
- `qpe_calc gw_expt`
- `periodic_gw_use_average_inverse_dm_gamma .true.`
- `output librpa binary develop fold_C mommat`
- `output gw_regular_kgrid`
- `output k_eigenvalue 100000`
- `calculate_all_eigenstates`

## Minimal `librpa.in` Expectations

For this route, `librpa.in` should remain focused on `task = g0w0`. A compact baseline is:

```text
task = g0w0
option_dielect_func = 3
replace_w_head = t
use_scalapack_gw_wc = t
parallel_routing = libri
```

Set `nfreq` to the same integer used by `frequency_points` in `control.in`, unless a trusted old reference case explicitly overrides that pairing.

Keep thresholds and SOC switches aligned with the trusted reference case when one exists.

## ABACUS Alignment Rule

When an ABACUS comparison case exists, preserve:

- lattice and atomic structure
- `k_grid`
- band path
- number of points on each band segment

Prefer direct comparability over inventing a new FHI-aims-only band path.

## Slurm Decomposition

- `run_aims.sh` is MPI-heavy and low-OMP
- `run_librpa.sh` is low-MPI and high-OMP
- do not treat a single combined script as the default workflow

The default reasoning is:

- FHI-aims scales as the MPI-dense stage
- LibRPA should use as many OpenMP threads per rank as practical on the target host

## Stage Shapes

`run_aims.sh` should look like:

- MPI launch for FHI-aims
- `OMP_NUM_THREADS=1` unless the user explicitly asks otherwise
- no chained LibRPA stage in the same script by default

`run_librpa.sh` should look like:

- fewer MPI ranks
- larger `OMP_NUM_THREADS`
- direct LibRPA launch only

## Fresh-Run Order

The default run order is:

1. validate or generate `geometry.in`
2. validate or generate `control.in`
3. validate or generate `librpa.in`
4. run `FHI-aims`
5. run `LibRPA`
