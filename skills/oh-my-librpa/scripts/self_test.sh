#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  self_test.sh [--workspace <path>] [--installed-root <path>]

Behavior:
  - Validates the Codex skill bundle layout
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
  "$installed_root/SKILL.md" \
  "$installed_root/rules/cards/librpa-default-presets.yml" \
  "$installed_root/rules/cards/molecular-gw-short-route.yml" \
  "$installed_root/rules/cards/periodic-gw-plotting.yml" \
  "$installed_root/rules/cards/server-profile-runtime.yml" \
  "$installed_root/registry/host-profiles/generic-hpc-example.env" \
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

for script in \
  "$installed_root/scripts/check_consistency.sh" \
  "$installed_root/scripts/check_slurm_resources.sh" \
  "$installed_root/scripts/ensure_abacus_orbitals_checkout.sh" \
  "$installed_root/scripts/intake_preflight.sh" \
  "$installed_root/scripts/materialize_batch_probe.sh" \
  "$installed_root/scripts/materialize_gw_template.sh" \
  "$installed_root/scripts/materialize_server_profile.sh" \
  "$installed_root/scripts/report_stage.sh" \
  "$installed_root/scripts/run_gw_workflow.sh" \
  "$installed_root/scripts/run_rpa_workflow.sh" \
  "$installed_root/scripts/self_test.sh" \
  "$installed_root/scripts/workflow_common.sh"; do
  if [[ -f "$script" ]]; then
    pass "Found script: $script"
  else
    fail "Missing script: $script"
    continue
  fi

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

case_gw_bad_abfs="$tmp_dir/gw-bad-abfs"
mkdir -p "$case_gw_bad_abfs"
cat <<'EOF' > "$case_gw_bad_abfs/INPUT_scf"
nbands 16
rpa 1
exx_pca_threshold 10
shrink_abfs_pca_thr 1e-4
shrink_lu_inv_thr 1e-3
exx_cs_inv_thr 1e-5
exx_singularity_correction massidda
EOF
cat <<'EOF' > "$case_gw_bad_abfs/INPUT_nscf"
nbands 16
EOF
cat <<'EOF' > "$case_gw_bad_abfs/librpa.in"
task = g0w0_band
nfreq = 16
use_shrink_abfs = t
EOF
cat <<'EOF' > "$case_gw_bad_abfs/KPT_nscf"
K_POINTS
2
Line
0.0 0.0 0.0 1 #G
0.5 0.0 0.0 1 #X
EOF
cat <<'EOF' > "$case_gw_bad_abfs/STRU"
ATOMIC_SPECIES
X 1.0 X.upf

NUMERICAL_ORBITAL
X.orb

ABFS_ORBITAL
X.abfs

LATTICE_CONSTANT
1.0
EOF
cat <<'EOF' > "$case_gw_bad_abfs/X.orb"
Element                     X
Radius Cutoff(a.u.)         10
Number of Sorbital          6
Number of Porbital          3
Number of Dorbital          3
Number of Forbital          2
EOF
cat <<'EOF' > "$case_gw_bad_abfs/X.abfs"
Element                     X
Radius Cutoff(a.u.)         8
Number of Sorbital-->       4
Number of Porbital-->       3
Number of Dorbital-->       2
Number of Forbital-->       1
Number of Gorbital-->       0
EOF
cat <<'EOF' > "$case_gw_bad_abfs/X.upf"
<UPF version="2.0.1"></UPF>
EOF

if "$installed_root/scripts/check_consistency.sh" "$case_gw_bad_abfs" --mode gw --system-type solid >/dev/null 2>&1; then
  fail 'check_consistency.sh accepted a shrink GW case with mismatched ABFS radius / missing g channel'
else
  pass 'check_consistency.sh rejects a shrink GW case with mismatched ABFS radius / missing g channel'
fi

case_gw_good_abfs="$tmp_dir/gw-good-abfs"
mkdir -p "$case_gw_good_abfs"
cp "$case_gw_bad_abfs/INPUT_scf" "$case_gw_good_abfs/INPUT_scf"
cp "$case_gw_bad_abfs/INPUT_nscf" "$case_gw_good_abfs/INPUT_nscf"
cp "$case_gw_bad_abfs/librpa.in" "$case_gw_good_abfs/librpa.in"
cp "$case_gw_bad_abfs/KPT_nscf" "$case_gw_good_abfs/KPT_nscf"
cp "$case_gw_bad_abfs/STRU" "$case_gw_good_abfs/STRU"
cp "$case_gw_bad_abfs/X.upf" "$case_gw_good_abfs/X.upf"
cp "$case_gw_bad_abfs/X.orb" "$case_gw_good_abfs/X.orb"
cat <<'EOF' >> "$case_gw_good_abfs/INPUT_scf"
out_librpa_reader_version 1
EOF
cat <<'EOF' >> "$case_gw_good_abfs/librpa.in"
prefix_coul_full = v1_coulomb_full_iq_
prefix_coul_cut = v1_coulomb_cut_iq_
prefix_lri_coeff = v1_Cs_data_
prefix_lri_coeff_shrink = v1_Cs_data_
version_coul_reader = 1
version_lri_reader = 1
use_cholesky_gw_wc = t
use_elpa_sqrt_coulomb = t
use_kpara_scf_eigvec = t
libri_chi0_collect_max_bytes = 2147483648
EOF
cat <<'EOF' > "$case_gw_good_abfs/X.abfs"
Element                     X
Radius Cutoff(a.u.)         10
Number of Sorbital-->       4
Number of Porbital-->       3
Number of Dorbital-->       2
Number of Forbital-->       1
Number of Gorbital-->       1
EOF

if "$installed_root/scripts/check_consistency.sh" "$case_gw_good_abfs" --mode gw --system-type solid >/dev/null 2>&1; then
  pass 'check_consistency.sh accepts a shrink GW case with matched ABFS radius and nonzero f/g channels'
else
  fail 'check_consistency.sh rejected a shrink GW case with matched ABFS radius and nonzero f/g channels'
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

case_missing_output="$tmp_dir/missing-output-librpa"
mkdir -p "$case_missing_output"
cat <<'EOF' > "$case_missing_output/INPUT_scf"
latname user_defined_lattice
rpa 1
exx_singularity_correction massidda
nbands 10
EOF
cat <<'EOF' > "$case_missing_output/INPUT_nscf"
latname user_defined_lattice
nbands 10
EOF
cat <<'EOF' > "$case_missing_output/KPT_nscf"
K_POINTS
0
Gamma
1 1 1 0 0 0
EOF
cat <<'EOF' > "$case_missing_output/librpa.in"
task = g0w0_band
nfreq = 16
tfgrid_type = minimax
EOF
cat <<'EOF' > "$case_missing_output/get_diel.py"
print("E_FERMI")
print("EFERMI")
EOF
cat <<'EOF' > "$case_missing_output/perform.sh"
python get_diel.py
EOF
cat <<'EOF' > "$case_missing_output/preprocess_abacus_for_librpa_band.py"
def resolve_wfc_file():
    return None
print("KPT.info")
print("wfk")
EOF

if ! "$installed_root/scripts/check_consistency.sh" "$case_missing_output" --mode gw --system-type solid >/tmp/oh-my-librpa-missing-output-librpa.log 2>&1 \
  && grep -q 'output_librpa.py' /tmp/oh-my-librpa-missing-output-librpa.log; then
  pass 'check_consistency.sh rejects periodic GW helper bundles that omit output_librpa.py'
else
  fail 'check_consistency.sh did not reject a periodic GW helper bundle missing output_librpa.py'
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
