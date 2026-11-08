---
name: oh-my-librpa-fhi-aims-g0w0-band
description: Use when users ask for periodic-solid FHI-aims + LibRPA single-shot G0W0 workflows, including requests that use the deprecated g0w0_band name.
---

# oh-my-librpa-fhi-aims-g0w0-band

Treat this as the periodic-solid `FHI-aims + LibRPA` single-shot GW lane. The route name preserves the older user-facing term, but LibRPA 0.7.0 input uses `task = g0w0`.

If the request is about QSGW-family tasks such as `qsgw_band`, `qsgw_band0`, `qsgw`, or `qsgwa`, stop and hand the task to `skills/oh-my-librpa-fhi-aims-qsgw/`.

If the request is about building or repairing the FHI-aims executable itself, stop and hand the task to `skills/fhi-aims-build/`.

## Scope

- periodic solids only
- single-shot `g0w0` only
- `geometry.in`, `control.in`, and `librpa.in` intake
- stage-only or fresh-run preparation
- two-stage Slurm submission

## Hard Defaults

- treat `FHI-aims` as the MPI-heavy stage
- treat `LibRPA` as the OpenMP-heavy stage
- apply `$librpa-openmp-mkl-threading` before staging or submitting the LibRPA stage
- for one MPI rank per node, do not inherit an unexplained `MKL_NUM_THREADS=1` default
- use two separate job scripts by default:
  - `run_aims.sh`
  - `run_librpa.sh`
- do not default to a single script that chains both stages
- `geometry.in` is interpreted in Angstrom
- both `atom` and `atom_frac` are allowed
- if an ABACUS comparison case exists, align:
  - structure
  - `k_grid`
  - band path
  - band-point counts

## Symmetry And BZ Sampling

Keep the FHI-aims `bz_sampling` reduction separate from LibRPA's use of
symmetry operations.

- `periodic_gw_optimize_kgrid_symmetry none`, `inverse`, and `all` control only
  the `bz_sampling` q-point mapping and the reduced q-dependent data written by
  FHI-aims.
- `none` keeps the unreduced q grid.
- `inverse` identifies `q` and `-q` by time-reversal/inversion pairing.
- `all` maps q points with the full spatial symmetry group and therefore gives
  the smallest irreducible q region.
- `stru_out` contains the spatial symmetry operations for all three modes. Do
  not infer that `inverse` or `none` suppresses symmetry-operation output.
- LibRPA independently decides whether to use those operations. For a
  symmetry-enabled GW production run, keep the applicable switches explicit:

```text
use_symmetry_exx = true
use_symmetry_rpa = true
use_symmetry_gw = true
```

For the currently validated FHI-aims reader-v1 to LibRPA route, use
`periodic_gw_optimize_kgrid_symmetry inverse` unless the exact FHI-aims and
LibRPA revisions have passed a same-case `all` versus `inverse` EXX/GW
regression. This is an interface-compatibility rule, not a claim that `all` is
physically invalid or that `inverse` is the only way to export symmetry.

The efficiency tradeoff is stage-specific. `all` can reduce q-dependent
Coulomb, chi0, dielectric, and W work much more strongly than `inverse`; for an
8x8x8 example, 43 versus 260 representatives is about 6.05 times fewer q
representatives. This is not a whole-job 6.05x speedup: the full SCF k grid,
band path, state/frequency loops, dense linear algebra, communication, and I/O
have different scaling. With `inverse`, LibRPA can still use the complete
`stru_out` operations for its EXX/RPA/GW symmetry reduction when the
`use_symmetry_*` switches are enabled.

## Intake States

- `geometry.in + control.in + librpa.in`
- `geometry.in + control.in`
- `geometry.in` only
- trusted old FHI-aims reference case
- ABACUS comparison case also present

## Required Reads

- read `references/periodic-solid-defaults.md`
- if the host is `df_iopcas_ghj`, also read `references/df-periodic-solid-example.md`

## Core Workflow

1. Confirm the lane is `FHI-aims + LibRPA`, the intent is single-shot GW, and the system is a periodic solid.
2. If `control.in` is missing, generate a periodic-solid skeleton from `geometry.in` and the active element list.
3. If `librpa.in` is missing, create a minimal `task = g0w0` baseline and keep `nfreq` consistent with the FHI-aims setup.
4. Before staging, audit the LibRPA input with `scripts/verify_librpa_input.py`:
   - `--dimension 3d --require-cs-threshold --control-in control.in` for a 3D solid;
   - `--dimension 2d` for a strict-2D case.
   A failure stops the workflow. Never rebuild `librpa.in` from the driver parameter dump: `cs_R_threshold` is a dump name, the input key is `cs_threshold`, and an unknown key is silently ignored (default `1e-6`, not the intended `0`). A 3D run must not carry the strict-2D switches `option_dielect_func = 4` or `use_fullcoul_wc = t`.
   A failure stops the workflow. Never rebuild `librpa.in` from the driver parameter dump: `cs_R_threshold` is a dump name, the input key is `cs_threshold`, and an unknown key is silently ignored (the default is `1e-6`, not the intended `0`). A 3D run must not carry the strict-2D switches `option_dielect_func = 4` or `use_fullcoul_wc = t`.
5. If ABACUS comparison inputs exist, preserve the ABACUS structure, `k_grid`, band path, and band-point counts unless the user explicitly overrides them.
6. Stage two scripts:
   - `run_aims.sh` for the MPI-heavy aims stage
   - `run_librpa.sh` for the OpenMP-heavy LibRPA stage
7. Keep the executable-path style, partition style, and directory layout from a trusted old case when one exists.
8. Preserve a trusted case's `periodic_gw_optimize_kgrid_symmetry` value. If it
   is omitted, determine and record the FHI-aims default instead of silently
   replacing it with `all`.
9. Stop before submission when the user asks for staging only or when route ownership is still ambiguous.

## Verification

- prove the case includes `geometry.in`
- prove `control.in` uses periodic-solid FHI-aims conventions
- prove the species blocks come from `defaults_2020/intermediate_gw` when auto-generated
- prove `run_aims.sh` and `run_librpa.sh` are separate
- prove the LibRPA MPI, OpenMP, and MKL thread counts pass `$librpa-openmp-mkl-threading`
- prove `scripts/verify_librpa_input.py` passed on the exact `librpa.in` that will be submitted (including `cs_threshold` and the 3D/2D dielectric switches)
- prove the ABACUS alignment rule was followed when comparison inputs exist
- record the requested FHI-aims `bz_sampling` mode and verify the resulting
  full-to-representative q mapping from `bz_sampling_out`
- verify `stru_out` contains the expected spatial symmetry operations
  independently of the `none`/`inverse`/`all` q-mapping choice
- verify the LibRPA input echo and runtime log show the intended
  `use_symmetry_exx`, `use_symmetry_rpa`, and `use_symmetry_gw` values
- do not accept `all` from its smaller q count alone; require an EXX reference
  gate and, for production GW, the corresponding GW numerical gate
