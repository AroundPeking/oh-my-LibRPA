# LibRPA Regression Route

Use this route for LibRPA regression maintenance, ABACUS+LibRPA test bundles, reference refreshes, and post-feature validation.

## Scope Rules

- Keep each regression case single-purpose. Do not add symmetry knobs to the MnO2 `nspin=2` case; it should remain a spin/shrink/head-wing coverage case.
- Add symmetry coverage as a separate small periodic GW case with both `use_shrink_abfs = t` and `use_input_*_symmetry = t`.
- Do not modify the regression framework unless the user explicitly asks. Prefer existing XML regex checks plus an external table comparison for band files.
- Use clean producer ownership. Root `band_out`, `vxc_out`, `stru_out`, `KS_eigenvector_*.dat`, `coulomb_*`, `Cs_*`, `shrink_sinvS_*`, and symmetry sidecars must come from ABACUS. `pyatb_librpa_df/*` is only for head/wing replacement and must not be copied over root files.

## Input Symmetry Bundle Requirements

A symmetry-on ABACUS+LibRPA bundle must include a complete sidecar set generated with the same SCF input:

- `irreducible_sector.txt`
- `symrot_R.txt`
- `symrot_k.txt`
- `symrot_abf_k.txt` when ABACUS emits it

The LibRPA input must keep these knobs aligned with the bundle:

```text
use_shrink_abfs = t
use_input_exx_symmetry = t
use_input_gw_symmetry = t
```

For a fast end-to-end case, target `nfreq = 8`, a very small auxiliary basis, and a short band path. The package should contain runtime inputs only, not generated logs, `OUT.ABACUS`, `LibRPA*.out`, `librpa.d`, old `GW_band_spin_*`, or debug dumps.

## Refreshing References

Before replacing `refs/<case>/`, rerun the case from a clean workspace with the intended executable and record:

- LibRPA git commit and executable path
- ABACUS executable path when regenerating inputs
- MPI ranks, OpenMP threads, node partition, and wall time
- `librpa.in` symmetry/shrink/head-wing flags
- Maximum differences from the previous accepted reference, if one exists

Only copy these final artifacts into `refs/<case>/`:

- `librpa.out`
- `KS_band_spin_*.dat`, if produced
- `EXX_band_spin_*.dat`, if produced
- `GW_band_spin_*.dat`, if produced

## Band Table Comparison

When validating a run against refs, compare all produced band tables numerically:

```bash
python3 - <<'PY'
from pathlib import Path

ref = Path("refs/CASE_NAME")
run = Path("workspace/CASE_NAME")
tol = 1e-6

def load_table(path):
    rows = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        rows.append([float(x) for x in s.split()])
    if rows and any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"{path}: non-rectangular table")
    return rows

def shape(rows):
    return (len(rows), len(rows[0]) if rows else 0)

def max_abs_diff(a, b):
    if shape(a) != shape(b):
        raise ValueError(f"shape mismatch {shape(a)} vs {shape(b)}")
    return max((abs(x - y) for ra, rb in zip(a, b) for x, y in zip(ra, rb)), default=0.0)

ok = True
for pattern in ("KS_band_spin_*.dat", "EXX_band_spin_*.dat", "GW_band_spin_*.dat"):
    ref_files = sorted(ref.glob(pattern))
    run_files = sorted(run.glob(pattern))
    if [p.name for p in ref_files] != [p.name for p in run_files]:
        print(f"{pattern}: file set mismatch")
        ok = False
        continue
    for rf, tf in zip(ref_files, run_files):
        a = load_table(rf)
        b = load_table(tf)
        if shape(a) != shape(b):
            print(f"{rf.name}: shape mismatch {shape(a)} vs {shape(b)}")
            ok = False
            continue
        diff = max_abs_diff(a, b)
        print(f"{rf.name}: max_abs_diff={diff:.3e}")
        ok = ok and diff <= tol

raise SystemExit(0 if ok else 1)
PY
```

Use `1e-6` for deterministic same-executable ref refreshes. If cross-machine BLAS or compiler changes cause harmless last-digit drift, report the observed max diff and only relax tolerance with an explicit reason.

## Completion Gate

After any LibRPA or ABACUS+LibRPA feature change, run at least:

- The active `testsuite.xml` regression subset that matches the touched feature.
- The MnO2 `nspin=2` case when spin, occupations, shrink, head/wing, or ABACUS parser paths are touched.
- A separate symmetry+shrink ABACUS+LibRPA case when symmetry, shrink, Coulomb/chi0/Wc/Sigma restore, or ABACUS sidecar handling is touched.

Do not claim a feature is safe until the relevant regression command and any band-table comparison have been reported with pass/fail output.
