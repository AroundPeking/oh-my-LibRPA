# Skills Core

`skills-core/` is the **only source of truth** for the project's LibRPA domain skills.

This directory should contain only reusable, platform-neutral project skills.

Current core skills:

- `oh-my-librpa`
- `abacus-librpa-gw`
- `abacus-librpa-rpa`
- `abacus-librpa-debug`
- `abacus-pyatb-librpa-stack`

Boundary:

- Keep platform-specific adapters out of this directory.
- Keep shared rules, templates, references, and scripts outside this directory.
- Installers should read from `skills-core/` and publish into each target platform's `skills/` directory.
