# RPA Route

Use this reference after `oh-my-librpa` has already classified the task as RPA.

Primary objective: get stable and reproducible RPA output first, then optimize scale or performance.

If the case is missing PP/NAO/ABFS files, pull them from the bundled asset library via `references/pp-nao-abfs-library.md` before filling the workflow.

If SOC is enabled for an RPA case, require SOC pseudopotentials from a matched PP / NAO / ABFS set. If the needed SOC PP assets are not present in the library, stop and ask the user to upload them.

## Default route

Use the short route:

- `SCF -> LibRPA`

Do not silently insert GW-only preprocessing into a normal RPA job:

- do not run `pyatb`
- do not run NSCF for the standard RPA route
- do not run `preprocess_abacus_for_librpa_band.py`
- do not require `KPT_nscf`

For `2D`, follow the same short route unless the user explicitly asks for a more specialized setup; ask about Coulomb treatment and vacuum assumptions before submission.

### Registered strict-2D SOS-RPA replay

For profile `abacus-librpa-2026-09-02-strict2d-sos-rpa-v1`, select route
`strict_2d_sos_rpa`. This is a LibRPA-only replay with no ABACUS/PyATB rerun;
reuse only the validated reader-v1 producer and its
`librpa_2d_coulomb_head.dat`. Fix `nfreq=16`, full 2D Ewald,
`replace_w_head=t`, `use_2d_dielectric=t`, `use_pyatb=t`, and
`rpa_headwing_mode=qavg`; do not set `head_only`. On df_dcu use `normal`, keep
all paths under `/work1`, launch four ranks with `mpirun -ppn 1`, and use 30
OpenMP/MKL threads per rank.

Admission requires source/MPI tests, producer completeness, duplicate-job
checks, finite energies, qavg weight closure, negligible imaginary parts,
q-sum equality, zero LU info, and MPI/singleton consistency. N=8, N=10, N=12,
and N=16 validate the function and numerics only; the observed exponent still
drifts, so a denser stable asymptotic series is required before any convergence
claim.

### Reviewed strict-2D SOS-RPA reference

Profile `abacus-librpa-2026-09-03-strict2d-sos-rpa-v2` binds the same replay to
benchmark `strict2d-sos-rpa-mos2-qavg-v1` and marks it `ENABLED`. The
reference-bounded criterion accepts the documented four-mesh behavior without
requiring complete adjacent-grid invariance. It makes no asymptotic exponent
claim and is not strict-2D GW acceptance. Call `inspect_route_benchmark` and
`evaluate_route_benchmark` before using the production profile.

## Default `librpa.in` preset

Set or verify:

- `task = rpa`
- `nfreq = 16`
- `use_scalapack_gw_wc = t`
- `use_scalapack_ecrpa = t`
- `parallel_routing = libri`
- `use_soc = 0/1` according to the INPUT spin/SOC state
- `vq_threshold = 0`
- `sqrt_coulomb_threshold = 0`
- `use_fullcoul_exx = f`

Full-Coulomb EXX is a separate physical-definition choice and must not be enabled as an implicit RPA default.
- `libri_chi0_threshold_C = 1e-4`
- `libri_chi0_threshold_G = 1e-5`
- `libri_exx_threshold_V = 1e-1`
- `libri_exx_threshold_C = 1e-4`
- `libri_exx_threshold_D = 1e-4`

## Static checklist

Before execution, verify:

- all input paths come from one consistent SCF source chain
- no GW-only preprocessing step has been inserted into the RPA route
- frequency-grid parameters are self-consistent
- file paths are not stitched from unrelated directories
- the run directory is fresh and isolated

## Recommended execution style

- start with a small-system smoke case
- change one major variable per iteration
- only scale `nfreq` or workload after the short route is stable
- prefer `run_rpa_workflow.sh` when available so execution, verification, and reporting stay in one flow

## Reporting requirement

After each stage, send a short operational update:

- what was done
- what was observed
- what is next

Prioritize minimal viable fixes over broad speculative changes.
