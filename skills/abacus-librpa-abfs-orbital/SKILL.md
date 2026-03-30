---
name: abacus-librpa-abfs-orbital
description: Obtain, select, validate, or document ABFS_ORBITAL inputs for ABACUS + LibRPA workflows. Use when the user asks how to get .abfs files, how to write ABFS_ORBITAL entries in STRU, how to build or source auxiliary bases, or when the user is teaching a new ABFS_ORBITAL recipe that should be saved for reuse.
---

# ABACUS + LibRPA ABFS_ORBITAL

Use this skill when the task is specifically about auxiliary-basis files and `ABFS_ORBITAL`, not the full GW route.

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

## Output style

When answering from this skill, report:

- source of the `.abfs` recipe
- exact `ABFS_ORBITAL` entries or exact next command
- what was verified
- any unresolved assumptions
