# Research Notes: Reusable Patterns from oh-my-opencode

## Conclusions (Directly Transferable to oh-my-LibRPA)

1. **Provide an AI-facing install entry**
   - `oh-my-opencode` puts a copy-paste prompt and a `curl` doc entry in README.
   - `oh-my-LibRPA` should do the same: `Install and configure ... by following ...`.

2. **Separate orchestration from execution**
   - Orchestration layer decides route and sequencing.
   - Execution layer performs deterministic checks, generation, and diagnosis.

3. **Route by task category, not by hardcoded model strings**
   - Use categories such as:
     - `workflow-gw`
     - `workflow-rpa`
     - `diagnosis`
     - `literature-review`

4. **Write skills as executable protocols**
   - Skills should define concrete steps, IO expectations, and failure branches.
   - Keep format consistent: `symptom -> root_cause -> fix -> verify`.

5. **Keep documentation hierarchy clear**
   - `README` (entry) -> `guide` (how-to) -> `reference` (details).

## What Not to Copy

- High-marketing tone is not suitable for a scientific workflow repository.
- Generic multi-model showmanship should never outrank reproducibility.

## Concrete Actions for oh-my-LibRPA

- Keep `docs/guide/installation.md` as the AI-first entry.
- Add workflow guides such as `workflow-gw.md` and `workflow-rpa.md`.
- Standardize rule cards with fields:
  - `scene`
  - `symptom`
  - `root_cause`
  - `fix`
  - `verify`
  - `applies_to`
- Define a minimal smoke-pass exit criterion for each workflow.
