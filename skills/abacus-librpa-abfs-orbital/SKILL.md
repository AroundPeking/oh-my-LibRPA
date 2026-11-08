---
name: abacus-librpa-abfs-orbital
description: Obtain, select, validate, or document ABFS_ORBITAL inputs for ABACUS + LibRPA workflows. Use when the user asks how to get .abfs files, how to write ABFS_ORBITAL entries in STRU, how to build or source auxiliary bases, or when the user is teaching a new ABFS_ORBITAL recipe that should be saved for reuse.
---

# ABACUS + LibRPA ABFS_ORBITAL

Use this skill when the task is specifically about auxiliary-basis files and `ABFS_ORBITAL`, not the full GW route.

## Reuse-first entrypoint

**Query the LibRPA materials database before writing any generation command.**
The canonical element assets live in
`https://github.com/AroundPeking/LibRPA-database`, reachable through the
`librpa-database` MCP server:

- `list_basis_sets(element=...)` lists every recorded PP/NAO/ABFS/for_aux set
  for an element, with the SHA-256 of each payload;
- `search_materials(...)` finds the archived calculations that already bind a
  set, so a new material can start from the set an old one used;
- `get_material(record_id)` returns the exact `set_id` per species.

PP, physical NAO and raw ABFS are transferable element assets, not new
per-material products. Search the database before assuming an asset is
missing: an asset absent from the catalog index is not proof that it does not
exist, so first re-query by element and by a related material. The local
`2d_gw_pp_basis_library` and `2d_gw/pp_basis_library` trees were retired on
2026-11-05 after every one of their 263 PP/NAO/ABFS payloads was confirmed
present in the database by hash; do not point at them.

Never silently mix GTH/SG15/Dojo pairs. Cross-material reuse does not waive
target overlap, RI/EXX checks, and does not include material-specific shrink
transformations.

After a calculation is accepted, archive the result into the database with
`librpa-database-intake`; a generated asset that only lives in a material run
folder is invisible to the next case.

## Core workflow

1. Identify which of these intents applies:
   - the user already has `.abfs` files and wants to wire them into `STRU`
   - the user wants to know how to obtain `.abfs` files for a given system
   - the user wants to validate whether existing `.abfs` files match the NAO / pseudopotential setup
   - the user is teaching a new `ABFS_ORBITAL` method that should be stored as a reusable playbook
2. Read `references/abfs-orbital-recipe.md` before giving procedural guidance.
3. Keep the source of truth explicit:
   - where the `.abfs` files come from
   - which ABACUS / LibRPA lane they are meant for
   - whether the method is generic, element-library based, or host-specific
4. Treat provided `.abfs` files as authoritative assets unless the user asks to regenerate them.
   Match the PP, physical NAO and ABFS hashes plus the auxiliary recipe when available. Missing original-generation evidence is recorded separately from a verified historical producer-use association; it is not by itself grounds to regenerate. Generate genuinely missing or demonstrated-inadequate assets only within current user authorization. For physical SIAB orbital design, use `abacus-pp-pbe-head-screening` and its `references/siab-generation-validation.md`, not the auxiliary-only recipe.
5. When the user is teaching a new method, update `references/abfs-orbital-recipe.md` with the exact steps, not a paraphrased summary.

## What to record when the user teaches a method

Capture these items exactly:

- prerequisites: code branch, binaries, scripts, host assumptions
- required inputs: `.orb`, `.upf`, `STRU`, element list, cutoff/radius assumptions
- exact commands
- expected output filenames and naming rules
- how the resulting filenames map into `ABFS_ORBITAL` lines in `STRU`
- validation checks
- known failure modes or incompatible combinations

If any of those are still unknown, leave a clear `TODO:` line instead of inventing details.

## Validation rules

Whenever checking an `ABFS_ORBITAL` setup, verify at least:

- each species in `STRU` has the intended `.abfs` file
- file naming and species mapping are unambiguous
- the method is consistent with the user's shrink / PCA lane
- if the workflow mixes different NAO cutoff radii across species, record that explicitly because it can matter for debugging
- distinguish same-center radial Gram, periodic physical-orbital overlap, local RI fit/inverse metric, and final full Coulomb. Atomic normalization/Gram or full-Coulomb PSD alone does not validate the local fit or EXX/GW accuracy

## Output style

When answering from this skill, report:

- source of the `.abfs` recipe
- exact `ABFS_ORBITAL` entries or exact next command
- what was verified
- any unresolved assumptions
