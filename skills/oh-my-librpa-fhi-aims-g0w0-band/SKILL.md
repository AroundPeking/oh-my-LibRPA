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
4. If ABACUS comparison inputs exist, preserve the ABACUS structure, `k_grid`, band path, and band-point counts unless the user explicitly overrides them.
5. Stage two scripts:
   - `run_aims.sh` for the MPI-heavy aims stage
   - `run_librpa.sh` for the OpenMP-heavy LibRPA stage
6. Keep the executable-path style, partition style, and directory layout from a trusted old case when one exists.
7. Stop before submission when the user asks for staging only or when route ownership is still ambiguous.

## Verification

- prove the case includes `geometry.in`
- prove `control.in` uses periodic-solid FHI-aims conventions
- prove the species blocks come from `defaults_2020/intermediate_gw` when auto-generated
- prove `run_aims.sh` and `run_librpa.sh` are separate
- prove the ABACUS alignment rule was followed when comparison inputs exist
