---
name: oh-my-librpa
description: Stable compatibility workflow for preparing, running, auditing, debugging, or regression-testing ABACUS and FHI-aims workflows that feed LibRPA GW/RPA calculations, including magnetic and historical cases outside the experimental MCP executor.
---

# Oh-My-LibRPA Stable Workflow

This is the stable compatibility lane. Use it for existing calculations,
historical reproductions, and routes that the experimental MCP does not yet
execute. Do not invoke `oh-my-librpa-mcp-test` unless the user explicitly asks
to test the MCP harness.

Apply `abacus-librpa-version-guard` before execution or interpretation and
`librpa-openmp-mkl-threading` when resource layout matters. Real ABACUS or
LibRPA calculations run on a remote server; local work is limited to source
inspection, input preparation, static checks, parsing, and plotting.

## Routing

1. Preserve the user's existing case definition and use a fresh run directory.
2. Route ABACUS inputs through `oh-my-librpa-abacus-librpa`, then use
   `abacus-librpa-gw`, `abacus-librpa-rpa`, or `abacus-librpa-debug`.
3. Route FHI-aims inputs through `oh-my-librpa-fhi-aims-g0w0-band` or
   `oh-my-librpa-fhi-aims-qsgw` only when strong FHI-aims markers establish
   ownership.
4. Use reader v1 by default for current ABACUS and LibRPA, require `stru_out`
   for current symmetry handoff, and copy no legacy symmetry sidecars.
5. Keep PP, NAO, ABFS, k mesh, spin, symmetry, solver, and executable identity
   fixed unless the requested test changes that variable.
6. Before submission, run the existing static preflight and record executable
   paths, hashes, source revisions, scheduler resources, and the duplicate-job
   check.

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
- `references/regression-route.md` — regression and reference comparison rules.
- `references/server-profiles.md` — server and execution profile layout.
- `references/abacus-merge-compat.md` — ABACUS merge compatibility notes.
