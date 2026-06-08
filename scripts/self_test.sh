#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  self_test.sh [--workspace <path>] [--installed-root <path>]

Behavior:
  - Validates installed skills and asset layout
  - Syntax-checks the shipped shell scripts
  - Smoke-tests report writing, route-aware checks, and intake preflight
EOF
}

pass() {
  echo "PASS: $*"
  pass_count=$((pass_count + 1))
}

fail() {
  echo "FAIL: $*" >&2
  fail_count=$((fail_count + 1))
}

workspace=""
installed_root=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) workspace="$2"; shift 2 ;;
    --installed-root) installed_root="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "$installed_root" ]]; then
  installed_root="$(cd "$script_dir/.." && pwd)"
fi

if [[ -z "$workspace" ]]; then
  workspace="$(cd "$installed_root/.." && pwd)"
fi

pass_count=0
fail_count=0

for path in \
  "$workspace/skills/oh-my-librpa/SKILL.md" \
  "$workspace/skills/oh-my-librpa-abacus-librpa/SKILL.md" \
  "$workspace/skills/oh-my-librpa-fhi-aims-qsgw/SKILL.md" \
  "$workspace/skills/abacus-librpa-gw/SKILL.md" \
  "$workspace/skills/abacus-librpa-rpa/SKILL.md" \
  "$workspace/skills/abacus-librpa-debug/SKILL.md" \
  "$installed_root/install.sh" \
  "$installed_root/update.sh" \
  "$installed_root/rules/cards/librpa-default-presets.yml" \
  "$installed_root/rules/cards/molecular-gw-short-route.yml" \
  "$installed_root/rules/cards/periodic-gw-plotting.yml" \
  "$installed_root/rules/cards/server-profile-runtime.yml" \
  "$installed_root/registry/host-profiles/generic-hpc-example.env" \
  "$installed_root/docs/guide/fhi-aims-librpa-qsgw.md" \
  "$installed_root/templates/abacus-librpa-gw/minimal/INPUT_scf.template" \
  "$installed_root/templates/abacus-librpa-gw/template/plot_gw_band_paper.py" \
  "$installed_root/templates/abacus-librpa-gw/routes/molecule-gw-no-nscf-no-pyatb-no-shrink/INPUT_scf.template" \
  "$installed_root/templates/abacus-librpa-gw/routes/molecule-gw-no-nscf-no-pyatb-no-shrink/librpa.in.template" \
  "$installed_root/templates/abacus-librpa-gw/routes/molecule-gw-no-nscf-no-pyatb-no-shrink/KPT_scf.template" \
  "$installed_root/templates/run-log.template.md"; do
  if [[ -f "$path" ]]; then
    pass "Found required file: $path"
  else
    fail "Missing required file: $path"
  fi
done

if grep -q 'supporting markers only: `geometry.in`, `librpa.d/`, `self_energy/`' "$workspace/skills/oh-my-librpa/SKILL.md" \
  && ! grep -q 'existing non-ABACUS case' "$workspace/skills/oh-my-librpa/SKILL.md"; then
  pass 'top-level router keeps weak markers from stealing ABACUS-owned cases'
else
  fail 'top-level router still contains ambiguous FHI-aims ownership triggers'
fi

if grep -q 'Do not use `geometry.in`, `librpa.d/`, or `self_energy/` alone' "$workspace/skills/oh-my-librpa-fhi-aims-qsgw/SKILL.md"; then
  pass 'FHI-aims skill rejects weak ownership markers on their own'
else
  fail 'FHI-aims skill still accepts weak ownership markers without stronger evidence'
fi

if [[ -f "$installed_root/install-state.env" ]]; then
  pass "Found install state: $installed_root/install-state.env"
else
  pass 'install-state.env not present in this tree yet; this is expected before install'
fi

for script in \
  "$installed_root/update.sh" \
  "$installed_root/scripts/check_consistency.sh" \
  "$installed_root/scripts/check_slurm_resources.sh" \
  "$installed_root/scripts/build_camg2n2_abfs_ladder.py" \
  "$installed_root/scripts/generate_gaussian_aux_orb.py" \
  "$installed_root/scripts/intake_preflight.sh" \
  "$installed_root/scripts/materialize_batch_probe.sh" \
  "$installed_root/scripts/materialize_gw_template.sh" \
  "$installed_root/scripts/materialize_server_profile.sh" \
  "$installed_root/scripts/report_stage.sh" \
  "$installed_root/scripts/run_gw_workflow.sh" \
  "$installed_root/scripts/run_rpa_workflow.sh" \
  "$installed_root/scripts/self_test.sh" \
  "$installed_root/scripts/trim_abfs_channels.py" \
  "$installed_root/scripts/workflow_common.sh"; do
  if [[ -f "$script" ]]; then
    pass "Found script: $script"
  else
    fail "Missing script: $script"
    continue
  fi

  if [[ "$script" == *.py ]]; then
    if python3 -m py_compile "$script"; then
      pass "py_compile passed: $script"
    else
      fail "py_compile failed: $script"
    fi

    if python3 "$script" --help >/dev/null 2>&1; then
      pass "--help works: $script"
    else
      fail "--help failed: $script"
    fi
  else
    if bash -n "$script"; then
      pass "bash -n passed: $script"
    else
      fail "bash -n failed: $script"
    fi

    if [[ "$script" != *"workflow_common.sh" ]]; then
      if "$script" --help >/dev/null 2>&1; then
        pass "--help works: $script"
      else
        fail "--help failed: $script"
      fi
    fi
  fi
done

tmp_dir="$(mktemp -d)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

run_dir="$tmp_dir/run"
archive_root="$tmp_dir/archive"
if "$installed_root/scripts/report_stage.sh" \
  --run-id selftest \
  --mode debug \
  --stage intake \
  --status success \
  --run-dir "$run_dir" \
  --task-label self-test \
  --what-done 'Created a synthetic run report.' \
  --what-observed 'report_stage.sh completed.' \
  --next-step 'Continue self-test.' \
  --archive-root "$archive_root" >/dev/null; then
  if [[ -f "$run_dir/run-report.md" && -f "$archive_root/selftest-debug.md" ]]; then
    pass 'report_stage.sh created both run and archive logs'
  else
    fail 'report_stage.sh did not create both expected logs'
  fi
else
  fail 'report_stage.sh smoke test failed'
fi

case_rpa="$tmp_dir/rpa-case"
mkdir -p "$case_rpa"
cat <<'EOF' > "$case_rpa/INPUT_scf"
nbands 16
rpa 1
EOF
cat <<'EOF' > "$case_rpa/librpa.in"
task = rpa
nfreq = 16
use_shrink_abfs = f
EOF

if "$installed_root/scripts/check_consistency.sh" "$case_rpa" --mode rpa --system-type molecule >/dev/null 2>&1; then
  pass 'check_consistency.sh passed on a minimal RPA case'
else
  fail 'check_consistency.sh failed on a minimal RPA case'
fi

if "$installed_root/scripts/intake_preflight.sh" "$case_rpa" --mode rpa --system-type molecule >/dev/null 2>&1; then
  pass 'intake_preflight.sh produced a summary on a minimal RPA case'
else
  fail 'intake_preflight.sh failed on a minimal RPA case'
fi

case_resource="$tmp_dir/resource-case"
mkdir -p "$case_resource"
cat <<'EOF' > "$case_resource/run_abacus.sh"
#!/bin/bash
#SBATCH -p 9242
#SBATCH -N 4
#SBATCH --cpus-per-task=96
#SBATCH --ntasks-per-node=1
#SBATCH --mem=380000
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
EOF
if "$installed_root/scripts/check_slurm_resources.sh" "$case_resource/run_abacus.sh" \
  --target-partition 9242 \
  --target-nodes 4 \
  --expected-ntasks-per-node 1 \
  --node-cores 96 \
  --node-memory-mb 380000 >/dev/null 2>&1; then
  pass 'check_slurm_resources.sh accepts a script that matches supplied live partition facts'
else
  fail 'check_slurm_resources.sh rejected a matching Slurm resource layout'
fi

case_resource_bad="$tmp_dir/resource-case-bad"
mkdir -p "$case_resource_bad"
cat <<'EOF' > "$case_resource_bad/run_abacus.sh"
#!/bin/bash
#SBATCH -p 9242
#SBATCH -N 4
#SBATCH --cpus-per-task=32
#SBATCH --ntasks-per-node=1
#SBATCH --mem=256000
export OMP_NUM_THREADS=$SLURM_CPUS_PER_TASK
EOF
if "$installed_root/scripts/check_slurm_resources.sh" "$case_resource_bad/run_abacus.sh" \
  --target-partition 9242 \
  --target-nodes 4 \
  --expected-ntasks-per-node 1 \
  --node-cores 96 \
  --node-memory-mb 380000 >/dev/null 2>&1; then
  fail 'check_slurm_resources.sh accepted an underfilled Slurm resource layout'
else
  pass 'check_slurm_resources.sh blocks underfilled Slurm core/memory requests'
fi

case_gw_missing_helper="$tmp_dir/gw-missing-helper"
if "$installed_root/scripts/materialize_gw_template.sh" --case-dir "$case_gw_missing_helper" --system-type solid >/dev/null 2>&1; then
  if grep -q '^output_gw_sigc_mat_rf = f$' "$case_gw_missing_helper/librpa.in"; then
    pass 'solid GW baseline keeps output_gw_sigc_mat_rf disabled by default'
  else
    fail 'solid GW baseline still enables output_gw_sigc_mat_rf by default'
  fi

  rm -f "$case_gw_missing_helper/get_diel.py"
  if preflight_output="$("$installed_root/scripts/intake_preflight.sh" "$case_gw_missing_helper" --mode gw --system-type solid 2>&1)"; then
    if grep -q 'runnable badge: blocked' <<<"$preflight_output" \
      && grep -q 'missing items: get_diel.py' <<<"$preflight_output"; then
      pass 'intake_preflight.sh blocks a solid GW case when get_diel.py is missing'
    else
      fail 'intake_preflight.sh did not report blocked/missing get_diel.py on a solid GW case'
    fi
  else
    fail 'intake_preflight.sh crashed instead of reporting missing get_diel.py on a solid GW case'
  fi
else
  fail 'materialize_gw_template.sh failed to prepare the solid GW regression case'
fi

case_gw_missing_output="$tmp_dir/gw-missing-output-helper"
if "$installed_root/scripts/materialize_gw_template.sh" --case-dir "$case_gw_missing_output" --system-type solid >/dev/null 2>&1; then
  rm -f "$case_gw_missing_output/output_librpa.py"
  if preflight_output="$("$installed_root/scripts/intake_preflight.sh" "$case_gw_missing_output" --mode gw --system-type solid 2>&1)"; then
    if grep -q 'runnable badge: blocked' <<<"$preflight_output" \
      && grep -q 'missing items: output_librpa.py' <<<"$preflight_output"; then
      pass 'intake_preflight.sh blocks a solid GW case when output_librpa.py is missing'
    else
      fail 'intake_preflight.sh did not report blocked/missing output_librpa.py on a solid GW case'
    fi
  else
    fail 'intake_preflight.sh crashed instead of reporting missing output_librpa.py on a solid GW case'
  fi
else
  fail 'materialize_gw_template.sh failed to prepare the output_librpa.py regression case'
fi

case_gw_nscf_band_continuation="$tmp_dir/gw-nscf-band-continuation"
if "$installed_root/scripts/materialize_gw_template.sh" \
  --case-dir "$case_gw_nscf_band_continuation" \
  --system-type solid \
  --enable-nscf-band-continuation true >/dev/null 2>&1; then
  if grep -q '^output_gw_sigc_mat_rf = t$' "$case_gw_nscf_band_continuation/librpa.in" \
    && grep -q '^OH_MY_LIBRPA_ENABLE_NSCF_BAND_CONTINUATION=.*true' "$case_gw_nscf_band_continuation/.oh-my-librpa-route.env"; then
    pass 'NSCF band-continuation requests explicitly enable output_gw_sigc_mat_rf'
  else
    fail 'NSCF band-continuation materialization did not record or enable output_gw_sigc_mat_rf'
  fi
else
  fail 'materialize_gw_template.sh failed on the explicit NSCF band-continuation route'
fi

gaussian_in="$tmp_dir/base.orb"
gaussian_out="$tmp_dir/base-aux.orb"
cat <<'EOF' > "$gaussian_in"
---------------------------------------------------------------------------
Element                     X
Energy Cutoff(Ry)           100
Radius Cutoff(a.u.)         10
Lmax                        2
Number of Sorbital-->       1
Number of Porbital-->       1
Number of Dorbital-->       1
---------------------------------------------------------------------------
SUMMARY  END

Mesh                        101
dr                          0.1
                Type               L               N
                   0               0               0
EOF
python3 - "$gaussian_in" <<'PY'
from math import exp
from pathlib import Path
import sys

path = Path(sys.argv[1])
with path.open("a", encoding="utf-8") as fh:
    for idx in range(101):
        r = idx * 0.1
        value = exp(-r)
        fh.write(f"   {value:.14e}")
        if (idx + 1) % 4 == 0:
            fh.write("\n")
    fh.write("\n")
    fh.write("                Type               L               N\n")
    fh.write("                   0               1               0\n")
    for idx in range(101):
        r = idx * 0.1
        value = r * exp(-r)
        fh.write(f"   {value:.14e}")
        if (idx + 1) % 4 == 0:
            fh.write("\n")
    fh.write("\n")
    fh.write("                Type               L               N\n")
    fh.write("                   0               2               0\n")
    for idx in range(101):
        r = idx * 0.1
        value = (r ** 2) * exp(-0.5 * r * r)
        fh.write(f"   {value:.14e}")
        if (idx + 1) % 4 == 0:
            fh.write("\n")
    fh.write("\n")
PY

if python3 "$installed_root/scripts/generate_gaussian_aux_orb.py" \
  --input "$gaussian_in" \
  --output "$gaussian_out" \
  >/dev/null 2>&1; then
  if python3 - "$gaussian_out" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
required = [
    "Number of Forbital-->       1",
    "Number of Gorbital-->       1",
    "Lmax                        4",
]
for marker in required:
    if marker not in text:
        raise SystemExit(1)
PY
  then
    pass 'generate_gaussian_aux_orb.py appended smooth F/G channels to a minimal orbitals file'
  else
    fail 'generate_gaussian_aux_orb.py output is missing the expected F/G header markers'
  fi
else
  fail 'generate_gaussian_aux_orb.py smoke test failed'
fi

trim_in="$tmp_dir/base.abfs"
trim_out="$tmp_dir/base-trimmed.abfs"
cat <<'EOF' > "$trim_in"
---------------------------------------------------------------------------
Element                     X
Energy Cutoff(Ry)           100
Radius Cutoff(a.u.)         10
Lmax                        6
Number of Sorbital-->       2
Number of Porbital-->       2
Number of Dorbital-->       1
Number of Forbital-->       1
Number of Gorbital-->       1
Number of Horbital-->       1
Number of Iorbital-->       1
---------------------------------------------------------------------------
SUMMARY  END

Mesh                        5
dr                          0.1
EOF
python3 - "$trim_in" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
channels = [
    (0, 0),
    (0, 1),
    (1, 0),
    (1, 1),
    (2, 0),
    (3, 0),
    (4, 0),
    (5, 0),
    (6, 0),
]
with path.open("a", encoding="utf-8") as fh:
    for l_value, n_value in channels:
        fh.write("                Type               L               N\n")
        fh.write(f"                   0               {l_value}               {n_value}\n")
        base = 10 * l_value + n_value
        values = [base + step for step in range(5)]
        for start in range(0, len(values), 4):
            chunk = values[start : start + 4]
            fh.write("".join(f"   {value:.14e}" for value in chunk))
            fh.write("\n")
        fh.write("\n")
PY

if python3 "$installed_root/scripts/trim_abfs_channels.py" \
  --input "$trim_in" \
  --output "$trim_out" \
  --count 0=1 \
  --count 1=2 \
  --count 2=1 \
  --count 3=1 \
  --count 4=0 \
  --count 5=1 \
  --count 6=0 \
  >/dev/null 2>&1; then
  if python3 - "$trim_out" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
required = [
    "Lmax                        5",
    "Number of Sorbital-->       1",
    "Number of Porbital-->       2",
    "Number of Dorbital-->       1",
    "Number of Forbital-->       1",
    "Number of Gorbital-->       0",
    "Number of Horbital-->       1",
]
for marker in required:
    if marker not in text:
        raise SystemExit(1)
if "Number of Iorbital" in text:
    raise SystemExit(1)
if "                   0               0               1" in text:
    raise SystemExit(1)
if "                   0               4               0" in text:
    raise SystemExit(1)
if "                   0               6               0" in text:
    raise SystemExit(1)
PY
  then
    pass 'trim_abfs_channels.py rewrote counts, Lmax, and retained the requested leading channels'
  else
    fail 'trim_abfs_channels.py output did not match the requested ABFS channel counts'
  fi
else
  fail 'trim_abfs_channels.py smoke test failed'
fi

ladder_base="$tmp_dir/ladder-base"
ladder_full="$tmp_dir/ladder-full"
mkdir -p "$ladder_base" "$ladder_full"
python3 - "$ladder_base" "$ladder_full" <<'PY'
from pathlib import Path
import sys

base_dir = Path(sys.argv[1])
full_dir = Path(sys.argv[2])

files = {
    "base": {
        "Ca": {0: 11, 1: 9, 2: 8, 3: 5, 4: 3},
        "Mg": {0: 12, 1: 9, 2: 8, 3: 4, 4: 3},
        "N": {0: 9, 1: 7, 2: 7, 3: 5, 4: 3},
    },
    "full": {
        "Ca": {0: 12, 1: 9, 2: 10, 3: 8, 4: 6, 5: 3, 6: 3, 7: 1, 8: 1},
        "Mg": {0: 12, 1: 10, 2: 10, 3: 7, 4: 6, 5: 3, 6: 3, 7: 1, 8: 1},
        "N": {0: 8, 1: 8, 2: 8, 3: 7, 4: 5, 5: 3, 6: 3, 7: 1, 8: 1},
    },
}

def write_abfs(path: Path, element: str, counts: dict[int, int]) -> None:
    mesh = 5
    lines = [
        "---------------------------------------------------------------------------",
        f"Element                     {element}",
        "Energy Cutoff(Ry)           100",
        "Radius Cutoff(a.u.)         10",
        f"Lmax                        {max(counts)}",
    ]
    labels = "SPDFGHIJK"
    for l_value in range(max(counts) + 1):
        lines.append(f"Number of {labels[l_value]}orbital-->       {counts.get(l_value, 0)}")
    lines.extend(
        [
            "---------------------------------------------------------------------------",
            "SUMMARY  END",
            "",
            f"Mesh                        {mesh}",
            "dr                          0.1",
        ]
    )
    for l_value in sorted(counts):
        for n_value in range(counts[l_value]):
            lines.append("                Type               L               N")
            lines.append(f"                   0               {l_value}               {n_value}")
            base = 100 * l_value + 10 * n_value
            values = [base + step for step in range(mesh)]
            for start in range(0, len(values), 4):
                chunk = values[start : start + 4]
                lines.append("".join(f"   {value:.14e}" for value in chunk))
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

for family, root in (("base", base_dir), ("full", full_dir)):
    for element, counts in files[family].items():
        write_abfs(root / f"{element}_{family}.abfs", element, counts)
PY

if ladder_output="$(python3 "$installed_root/scripts/build_camg2n2_abfs_ladder.py" \
  --base-dir "$ladder_base" \
  --full-dir "$ladder_full" \
  --dry-run 2>/dev/null)"; then
  if grep -q '"G1"' <<<"$ladder_output" \
    && grep -q '"estimated_cell_size": 780' <<<"$ladder_output" \
    && grep -q '"estimated_cell_size": 923' <<<"$ladder_output" \
    && grep -q '"estimated_cell_size": 1283' <<<"$ladder_output" \
    && grep -q '"estimated_cell_size": 1358' <<<"$ladder_output"; then
    pass 'build_camg2n2_abfs_ladder.py reports the approved G1-G4 synchronized stage sizes'
  else
    fail 'build_camg2n2_abfs_ladder.py dry-run output is missing the approved G1-G4 stage sizes'
  fi
else
  fail 'build_camg2n2_abfs_ladder.py dry-run failed'
fi

ladder_written="$tmp_dir/ladder-written"
if python3 "$installed_root/scripts/build_camg2n2_abfs_ladder.py" \
  --base-dir "$ladder_base" \
  --full-dir "$ladder_full" \
  --output-root "$ladder_written" \
  --stage G1 >/dev/null 2>&1; then
  if python3 - "$ladder_written/G1/N_full_G1_151.abfs" <<'PY'
from pathlib import Path
import sys

text = Path(sys.argv[1]).read_text()
required = [
    "Number of Sorbital-->       9",
    "Number of Porbital-->       8",
    "Number of Dorbital-->       8",
    "Number of Forbital-->       6",
    "Number of Gorbital-->       4",
]
for marker in required:
    if marker not in text:
        raise SystemExit(1)
PY
  then
    pass 'build_camg2n2_abfs_ladder.py preserves baseline-leading channels when the large endpoint is smaller'
  else
    fail 'build_camg2n2_abfs_ladder.py did not preserve baseline-leading channels when the large endpoint is smaller'
  fi
else
  fail 'build_camg2n2_abfs_ladder.py file generation failed on the baseline-fallback regression case'
fi

case_gw="$tmp_dir/gw-molecule-short"
if "$installed_root/scripts/materialize_gw_template.sh" \
  --case-dir "$case_gw" \
  --system-type molecule \
  --needs-nscf false \
  --needs-pyatb false \
  --use-shrink-abfs false >/dev/null 2>&1; then
  pass 'materialize_gw_template.sh selected the dedicated molecular GW route'
else
  fail 'materialize_gw_template.sh failed on the dedicated molecular GW route'
fi

if [[ -f "$case_gw/.oh-my-librpa-route.env" ]] && grep -q '^OH_MY_LIBRPA_ROUTE_ID=.*molecule-gw-no-nscf-no-pyatb-no-shrink' "$case_gw/.oh-my-librpa-route.env"; then
  pass 'route metadata records the dedicated molecular GW route'
else
  fail 'route metadata is missing or does not record the dedicated molecular GW route'
fi

if grep -q 'out_mat_xc[[:space:]]\+1' "$case_gw/INPUT_scf" \
  && grep -q 'out_librpa_reader_version[[:space:]]\+1' "$case_gw/INPUT_scf" \
  && awk '
    $1 == "exx_ccp_rmesh_times" { exx = $2 }
    $1 == "rpa_ccp_rmesh_times" { rpa = $2 }
    END { exit !(exx != "" && rpa != "" && exx == rpa) }
  ' "$case_gw/INPUT_scf" \
  && ! grep -q 'out_chg[[:space:]]\+1' "$case_gw/INPUT_scf" \
  && ! grep -q 'out_mat_r[[:space:]]\+1' "$case_gw/INPUT_scf" \
  && ! grep -q 'out_mat_hs2[[:space:]]\+1' "$case_gw/INPUT_scf"; then
  pass 'materialized INPUT_scf matches the molecular short-route output set'
else
  fail 'materialized INPUT_scf does not match the molecular short-route output set'
fi

if grep -q '^replace_w_head = f$' "$case_gw/librpa.in" \
  && grep -q '^prefix_coul_full = v1_coulomb_full_iq_$' "$case_gw/librpa.in" \
  && grep -q '^prefix_coul_cut = v1_coulomb_cut_iq_$' "$case_gw/librpa.in" \
  && grep -q '^prefix_lri_coeff = v1_Cs_data_$' "$case_gw/librpa.in" \
  && grep -q '^version_coul_reader = 1$' "$case_gw/librpa.in" \
  && grep -q '^version_lri_reader = 1$' "$case_gw/librpa.in" \
  && grep -q '^use_cholesky_gw_wc = t$' "$case_gw/librpa.in" \
  && grep -q '^use_elpa_sqrt_coulomb = t$' "$case_gw/librpa.in" \
  && grep -q '^use_kpara_scf_eigvec = t$' "$case_gw/librpa.in" \
  && grep -q '^libri_chi0_collect_max_bytes = 2147483648$' "$case_gw/librpa.in" \
  && grep -q '^use_abacus_exx_symmetry = f$' "$case_gw/librpa.in" \
  && grep -q '^use_abacus_gw_symmetry = f$' "$case_gw/librpa.in" \
  && grep -q '^use_shrink_abfs = f$' "$case_gw/librpa.in"; then
  pass 'materialized librpa.in matches the molecular short-route defaults'
else
  fail 'materialized librpa.in does not match the molecular short-route defaults'
fi

if grep -q 'cp -a OUT.ABACUS/vxc_out.dat ./vxc_out' "$case_gw/run_abacus.sh" \
  && grep -q 'v1_coulomb_full_iq_\*' "$case_gw/run_abacus.sh" \
  && grep -q 'v1_coulomb_cut_iq_\*' "$case_gw/run_abacus.sh" \
  && grep -q 'v1_Cs_data_\*' "$case_gw/run_abacus.sh" \
  && grep -q 'KS_eigenvector_\*\.dat' "$case_gw/run_abacus.sh"; then
  pass 'materialized run_abacus.sh contains the direct LibRPA handoff guards'
else
  fail 'materialized run_abacus.sh is missing the direct LibRPA handoff guards'
fi

if [[ ! -f "$case_gw/INPUT_nscf" && ! -f "$case_gw/KPT_nscf" && ! -f "$case_gw/get_diel.py" && ! -f "$case_gw/perform.sh" && ! -f "$case_gw/preprocess_abacus_for_librpa_band.py" ]] && grep -q '^1 1 1 0 0 0$' "$case_gw/KPT_scf"; then
  pass 'materialized molecular GW case drops NSCF assets and keeps Gamma-only KPT_scf'
else
  fail 'materialized molecular GW case did not drop NSCF assets or did not keep Gamma-only KPT_scf'
fi

if "$installed_root/scripts/check_consistency.sh" "$case_gw" --mode gw --system-type molecule >/dev/null 2>&1; then
  pass 'check_consistency.sh passed on the materialized molecular GW short route'
else
  fail 'check_consistency.sh failed on the materialized molecular GW short route'
fi

case_server="$tmp_dir/server-profile"
mkdir -p "$case_server"
if "$installed_root/scripts/materialize_server_profile.sh" --case-dir "$case_server" --profile generic-hpc-example >/dev/null 2>&1; then
  pass 'materialize_server_profile.sh wrote env.sh from the generic example profile'
else
  fail 'materialize_server_profile.sh failed on the generic example profile'
fi

if [[ -f "$case_server/env.sh" && -f "$case_server/.oh-my-librpa-host-profile.env" ]] \
  && grep -q 'python3_exec=' "$case_server/env.sh" \
  && grep -q 'mpirun_exec=' "$case_server/env.sh"; then
  pass 'materialized server profile records explicit python3 and launcher settings'
else
  fail 'materialized server profile is missing explicit python3 or launcher settings'
fi

if "$installed_root/scripts/materialize_batch_probe.sh" --case-dir "$case_server" --profile generic-hpc-example --force >/dev/null 2>&1 \
  && [[ -f "$case_server/probe_batch.sh" ]]; then
  pass 'materialize_batch_probe.sh wrote a batch-node probe script'
else
  fail 'materialize_batch_probe.sh failed to write a batch-node probe script'
fi

if grep -q 'python3_exec' "$installed_root/templates/abacus-librpa-gw/template/run_abacus.sh" \
  && grep -q 'resolved-runtime.env' "$installed_root/templates/abacus-librpa-gw/template/run_abacus.sh" \
  && ! grep -qE '(^|[[:space:]])python preprocess_abacus_for_librpa_band.py' "$installed_root/templates/abacus-librpa-gw/template/run_abacus.sh"; then
  pass 'periodic run_abacus.sh uses explicit runtime resolution and avoids bare python helpers'
else
  fail 'periodic run_abacus.sh still lacks explicit runtime resolution or still uses bare python helpers'
fi

if grep -q 'python3_exec' "$installed_root/templates/abacus-librpa-gw/template/perform.sh" \
  && grep -q 'output_librpa.py' "$installed_root/templates/abacus-librpa-gw/template/perform.sh" \
  && ! grep -qE '(^|[[:space:]])python get_diel.py' "$installed_root/templates/abacus-librpa-gw/template/perform.sh"; then
  pass 'perform.sh uses explicit python3 resolution and checks helper dependencies'
else
  fail 'perform.sh still lacks explicit python3 resolution or helper checks'
fi

if command -v python3 >/dev/null 2>&1; then
  if python3 -m py_compile "$installed_root/templates/abacus-librpa-gw/template/plot_gw_band_paper.py"; then
    pass 'plot_gw_band_paper.py passes python bytecode compilation'
  else
    fail 'plot_gw_band_paper.py failed python bytecode compilation'
  fi
else
  pass 'python3 not available for plot_gw_band_paper.py bytecode compilation; skipped'
fi

if command -v python3 >/dev/null 2>&1; then
  plot_script="$installed_root/templates/abacus-librpa-gw/template/plot_gw_band_paper.py"
  if python3 - <<EOF >/dev/null 2>&1
import importlib.util
from pathlib import Path
import numpy as np

path = Path("$plot_script")
spec = importlib.util.spec_from_file_location("plot_gw_band_paper", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

aux = np.array([
    [10.0, 20.0, 30.0, 40.0, 50.0],
    [11.0, 21.0, 31.0, 41.0, 51.0],
])
ene = np.array([
    [-5.0, -0.2,  9.5,  0.7, 15.0],
    [-5.1, -0.1, 10.5,  0.6, 15.1],
])

aux_sorted, ene_sorted = mod.sort_gw_bands_in_window(aux, ene, 1, 4)

assert np.allclose(ene_sorted[:, 0], ene[:, 0])
assert np.allclose(ene_sorted[:, 4], ene[:, 4])
assert np.allclose(aux_sorted[:, 0], aux[:, 0])
assert np.allclose(aux_sorted[:, 4], aux[:, 4])
assert np.allclose(ene_sorted[:, 1:4], np.array([
    [-0.2, 0.7, 9.5],
    [-0.1, 0.6, 10.5],
]))
assert np.allclose(aux_sorted[:, 1:4], np.array([
    [20.0, 40.0, 30.0],
    [21.0, 41.0, 31.0],
]))
EOF
  then
    pass 'plot_gw_band_paper.py can reorder only a selected near-Fermi band window without touching outer bands'
  else
    fail 'plot_gw_band_paper.py failed the near-Fermi-only band reordering regression test'
  fi
else
  pass 'python3 not available for plot_gw_band_paper.py near-Fermi-only reordering regression test; skipped'
fi

plot_case="$tmp_dir/plot-case"
mkdir -p "$plot_case"
cat <<'EOF' > "$plot_case/GW_band_spin_1.dat"
1 0.0 0.0 0.0 0.0 5.00 0.0 6.20
2 0.5 0.0 0.0 0.0 5.10 0.0 6.35
3 1.0 0.0 0.0 0.0 5.20 0.0 6.40
EOF
cat <<'EOF' > "$plot_case/band_out"
1 2
1 1.0 0 0
2 0.0 0 0
EOF
cat <<'EOF' > "$plot_case/band_kpath_info"
nk = 3
0.0 0.0 0.0
0.5 0.0 0.0
1.0 0.0 0.0
EOF
cat <<'EOF' > "$plot_case/KPT_nscf"
K_POINTS
2
Line
0.0 0.0 0.0 2 # G
0.5 0.0 0.0 1 # X
EOF

if command -v python3 >/dev/null 2>&1; then
  if python3 - <<'EOF' >/dev/null 2>&1
import importlib
importlib.import_module('numpy')
importlib.import_module('matplotlib')
EOF
  then
    if python3 "$installed_root/templates/abacus-librpa-gw/template/plot_gw_band_paper.py" --run-dir "$plot_case" --prefix test_gw_band --valence-bands 1 --conduction-bands 1 --cbm-search-window 1 >/dev/null 2>&1 \
      && [[ -f "$plot_case/plots/test_gw_band.png" && -f "$plot_case/plots/test_gw_band.pdf" && -f "$plot_case/plots/test_gw_band_summary.txt" ]]; then
      pass 'plot_gw_band_paper.py generated PNG/PDF/summary outputs on a synthetic periodic GW case'
    else
      fail 'plot_gw_band_paper.py failed on a synthetic periodic GW case'
    fi
  else
    pass 'numpy/matplotlib not available for plot_gw_band_paper.py runtime smoke test; skipped'
  fi
else
  pass 'python3 not available for plot_gw_band_paper.py runtime smoke test; skipped'
fi

echo "SUMMARY: pass=$pass_count fail=$fail_count"

if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi

echo 'DONE: self-test passed'
