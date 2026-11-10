---
name: oh-my-librpa
description: Entry point for ALL ABACUS or FHI-aims plus LibRPA work — load this first, before any oml sub-route skill. Covers GW, G0W0, QSGW, RPA, EXX, Delta-Sternheimer for solids, molecules, 2D, metals, nspin=2, SOC and historical cases; routes to the right sub-route and fixes PP/NAO/ABFS/k-mesh/version identity. Use when the user says ABACUS, FHI-aims, LibRPA, GW, QSGW, RPA, EXX, 能带, 跑个 GW, or asks to prepare, submit, check or debug such a calculation.
---

# Oh-My-LibRPA Stable Workflow

**This skill is the entry point. If the request touches ABACUS, FHI-aims,
LibRPA, GW, G0W0, QSGW, RPA, EXX or Delta-Sternheimer and you have not loaded
this file yet, stop and load it before acting.** Every other skill in this
repository is a leaf of this entry — including `siab-generate-orbitals`,
`fhi-aims-build` and `gw-toolchain`, which do not share the `abacus-*` /
`librpa-*` / `oh-my-librpa-*` prefix. They assume the identity below is already
fixed and must not re-decide it.

This is the stable compatibility lane. Use it for existing calculations,
historical reproductions, and routes that the experimental MCP does not yet
execute. Do not invoke `oh-my-librpa-mcp-test` unless the user explicitly asks
to test the MCP harness.

Apply `abacus-librpa-version-guard` before execution or interpretation and
`librpa-openmp-mkl-threading` when resource layout matters. Real ABACUS or
LibRPA calculations run on a remote server; local work is limited to source
inspection, input preparation, static checks, parsing, and plotting.

## Non-negotiables

These hold no matter which sub-route the request ends up in. The sub-route table
and the pipeline below decide *where to go*; this section decides *what must
stay true* on the way.

1. Preserve the user's existing case definition and use a fresh run directory.
2. Use reader v1 by default for current ABACUS and LibRPA, require `stru_out`
   for current symmetry handoff, and copy no legacy symmetry sidecars.
3. Keep PP, NAO, ABFS, k mesh, spin, symmetry, solver, and executable identity
   fixed unless the requested test changes that variable.
4. **Say where the basis comes from and how big it is, before any compute.**
   Never let a run start on a basis the user has not been shown. State, per
   species: the database element set id (or that the payloads are case-bundled
   and match no single set), the pseudopotential file, the NAO shell string and
   basis functions per atom, the auxiliary basis shell string and its dimension
   per atom, and the totals `nbasis` / `naux` for the structure. Under the MCP
   harness this is enforced: `prepare_run` writes the disclosure, `describe_basis`
   shows it, `acknowledge_basis` records the digest the user accepted, and
   `submit_stage` refuses (`BASIS_NOT_ACKNOWLEDGED`) until that exists. Do not
   choose a pseudopotential family on the user's behalf — when the library
   offers several usable sets for an element, list them and ask. Running
   `oh-my-librpa` without a shell means stating the same block in the reply
   before submitting anything.
5. Before submission, run the existing static preflight and record executable
   paths, hashes, source revisions, scheduler resources, and the duplicate-job
   check.
6. For optical spectra, exciton binding energies or exciton envelope densities,
   apply `references/bse-route.md`.
7. Before any GW or RPA calculation, query the LibRPA materials database through
   its MCP server for similar materials: `search_materials` for the same or a
   related material, `list_basis_sets(element=...)` for every recorded
   PP/NAO/ABFS/for_aux set, `get_material(record_id)` for the exact `set_id` per
   species. Reuse the hash-matched element bundle and recorded parameters when
   they exist; generate a new set only when the database has no match, and say
   which query established the gap. After a calculation is accepted, archive it
   with `librpa-database-intake` — a result that lives only in the material run
   folder is invisible to the next case.

## Which sub-route

Every one of these is a leaf of this entry and carries the same back-pointer.
Pick by what the request actually asks for; load only what you pick.

| Sub-route | Take it when the request is about |
|---|---|
| `oh-my-librpa-abacus-librpa` | ABACUS-side router: INPUT/KPT/STRU, producer outputs, reader-v1 handoff |
| `abacus-librpa-gw` | building or validating a GW/G0W0 case (SCF/DF/NSCF chaining, `librpa.in`) |
| `abacus-librpa-rpa` | RPA calculations: preparing, static checks, conservative defaults, troubleshooting |
| `abacus-librpa-debug` | a run already failed — logs, parser errors, inconsistent outputs |
| `abacus-scf-convergence` | SCF itself will not converge (drho oscillation, `scf_nmax`, magnetic/metaGGA) |
| `abacus-pp-pbe-head-screening` | choosing GTH/SG15/PseudoDojo PP + TZDP orbitals, PBE-vs-aims head check |
| `abacus-librpa-abfs-orbital` | `.abfs` / `ABFS_ORBITAL` — where to get them, how to write them |
| `siab-generate-orbitals` | generating or regenerating `.orb` with SIAB (dimer PW + SA) |
| `abacus-librpa-strict2d-ewald-headwing` | 2D production GW: 2D Ewald, analytic Gamma head/wing, PyATB |
| `abacus-librpa-strict2d-direct-coulomb` | the full-Ewald 2D Coulomb matrix is indefinite or cutoff-sensitive |
| `abacus-delta-st-solid-convergence` | periodic-solid Delta-Sternheimer RPA protocol |
| `abacus-delta-st-molecular-convergence` | molecular Delta-Sternheimer RPA, box/FD-grid/binding energy |
| `abacus-delta-st-efficient-production` | an existing Delta-ST series must fit a wall-time limit |
| `oh-my-librpa-fhi-aims-g0w0-band` | FHI-aims single-shot G0W0 band — only when strong FHI-aims markers establish ownership |
| `oh-my-librpa-fhi-aims-qsgw` | FHI-aims staged QSGW campaigns (`qsgw_band`, `qsgw_band0`) — only when strong FHI-aims markers establish ownership |
| `fhi-aims-build` | building or repairing the FHI-aims executable itself |
| `gw-toolchain` | provisioning OneAPI/GCC/ELPA/LibXC/LibRPA/PYATB/ABACUS on a new host |
| `librpa-openmp-mkl-threading` | MPI/OpenMP/MKL layout, low CPU utilization |
| `abacus-librpa-version-guard` | matching a calculation against the immutable OML compatibility profile before execution or interpretation |
| `librpa-database-intake` | **after** a result is accepted — archiving it into the database |
| `librpa-pr-review` | LibRPA pull requests. Never for running a calculation. |
| `oh-my-librpa-mcp-test` | only when the user explicitly asks to test the MCP harness |

If two rows both look applicable, the more specific one wins (a strict-2D case
takes `abacus-librpa-strict2d-ewald-headwing`, not `abacus-librpa-gw`), and this
entry still owns the identity decisions in items 4–7 above.

A real request usually chains several rows, in this order. Skip what the case
does not need; do not reorder the three gates.

```text
1  abacus-librpa-version-guard        pin revisions/hashes before anything runs
2  abacus-pp-pbe-head-screening      PP + NAO/ABFS identity (DB first, then generate)
   abacus-librpa-abfs-orbital        only when .abfs still has to be resolved
   siab-generate-orbitals            only when .orb still has to be built
3  abacus-scf-convergence            if SCF will not converge — before blaming GW
4  oh-my-librpa-abacus-librpa        ABACUS-side router: INPUT/KPT/STRU + reader-v1
   abacus-librpa-gw (or abacus-librpa-rpa)   build/validate the case
   + abacus-librpa-strict2d-ewald-headwing
     (or abacus-librpa-strict2d-direct-coulomb)
                                     when the material is 2D
   + abacus-delta-st-solid-convergence
     (or abacus-delta-st-molecular-convergence)
                                     when the target is a Delta-ST RPA energy
   + oh-my-librpa-fhi-aims-g0w0-band (or oh-my-librpa-fhi-aims-qsgw)
                                     when the producer is FHI-aims
5  abacus-librpa-debug               only after a run actually failed
6  librpa-database-intake            only after the result is accepted
```

E.g.「MoS2 二维材料跑个 GW」= 1 → 2 → 4 (`abacus-librpa-gw` +
`abacus-librpa-strict2d-ewald-headwing`) → 6. A request to debug a failed run
starts at 5 but still owns 1's provenance check.

## Metals

A metal is not a separate lane. It is a modifier on the solid branch:
`gw-solid-branch-302` still governs the SCF -> NSCF -> LibRPA chain, and
`gw-metal-solid-branch-303` (3D) or `gw-metal-2d-branch-304` (2D) adds only what
differs — fractional occupations carried end to end, `option_dielect_func = 3`
with `replace_w_head = t`, the velocity matrix that head/wing needs, the
square-BLACS rank constraint, the sparse-IR grid sizing rules, and the
regularized replay that separates a reportable band from the native table.
Both metal cards deploy the existing 2D strict-Ewald and 3D full-Coulomb
treatment rather than replacing them; a 2D metal is the 2D route plus the metal
contract, not a third workflow.

Read `rules/cards/metal-gw.yml` for the enumerated failure signatures
(`metal-gw-failures-401`) and the acceptance gates
(`metal-gw-acceptance-402`) before interpreting any metal band.

## Spin And SOC

- Nonmagnetic collinear: `nspin = 1`, `lspinorb = 0`.
- Magnetic collinear without SOC: `nspin = 2`, `lspinorb = 0`; keep both spin
  channels consistent in ABACUS outputs, PyATB, preprocessing, and LibRPA.
- Noncollinear or SOC: use the reviewed `nspin = 4` route, disable the periodic
  spatial-symmetry lane unless that exact combination has separate evidence,
  and keep PyATB's `use_soc` convention consistent.

An MCP `ROUTE_NOT_EXECUTABLE` or unregistered historical profile means only
that the experimental executor lacks coverage. It is not evidence that the
underlying reviewed GW workflow or physical calculation is invalid.

Never overwrite an existing calculation directory, cancel an unrelated job,
or resubmit while a matching job or immutable receipt exists. Keep scheduler,
numerical, and scientific conclusions separate.

## References

- `references/delta-st-route.md` — Delta-Sternheimer RPA route: memory
  fallbacks (`effective_workers=1` means a memory-limited outer-channel run),
  global-equation MPI sizing (ranks must not be pinned to `nfreq`), and the
  required same-matrix endpoint test.
- `references/gw-route.md` — periodic and molecular G0W0 route contracts.
- `references/rpa-route.md` — RPA total-energy route contracts.
- `references/bse-route.md` — GW+BSE route: the four `scf -> nscf -> GW -> BSE`
  stages, the `Wc_iR_*_ifreq_0.mtx` sidecar that stage 4 requires from stage 3,
  the version-dependent spelling of the W(R) output switch, and the hard
  boundary that this BSE solves Q = 0 excitons only.
- `references/regression-route.md` — regression and reference comparison rules.
- `references/ws2-2d-qsgw-g0w0-hr.md` — WS2 2D standard recipe: one `qsgw` task
  carrying the band channel, G0W0 eqp and QSGW bands together, H(R) and
  Sigma(R, iw) for ML, the shifted 2 eV cut, the `use_kpara_scf_eigvec=f`
  requirement, and the k10/k20 database comparison.
- `references/abfs-generation.md` — generating `.abfs` from scratch when the
  database has no match: the PP/NAO/ABFS family lock (never mix Dojo-NC-SR with
  SG15, never swap TZDP orbitals onto a DZP-derived auxiliary basis), the default
  checkout, the angular-momentum rule, and the validation step.
- `references/pp-nao-abfs-library.md` — reading the bundled PP/NAO/ABFS asset
  library: which system-level combination is a tested match, the element-by-
  element fallback order, why a mixed-family set needs an explicit risk callout,
  and the stop rules (missing element, missing SOC pseudopotential).
- `references/debug-route.md` — triage once a run has already failed: the
  six-step diagnosis order (which stage failed, mixed chains, stale outputs,
  renamed keywords, conflicting thresholds, spin/SOC and `nbands` mismatch),
  the fast routing hints for common signatures (`stod`, missing shrink sync,
  IBZ-only `coulomb_*`), and the required report structure.
- `references/server-profiles.md` — server and execution profile layout.
- `references/abacus-merge-compat.md` — ABACUS merge compatibility notes.
