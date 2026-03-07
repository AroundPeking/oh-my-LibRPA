#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  stack_smoke_test.sh \
    --case-dir <path> \
    [--run-root <path>] \
    [--env-script <path>] \
    [--python <path>] \
    [--abacus-bin <path>] \
    [--pyatb-cmd <path>] \
    [--librpa-bin <path>] \
    [--skip-abacus] \
    [--skip-pyatb] \
    [--skip-librpa]

Behavior:
  - Creates a fresh copied run directory
  - Reuses SCF / PYATB / LibRPA outputs when already present
  - Otherwise smoke-tests ABACUS SCF, PYATB helper generation, and LibRPA runtime when the needed inputs exist
  - Treats the result as a stack smoke test, not a full numerical reproduction, unless the full chain is really present
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

case_dir=""
run_root="${TMPDIR:-/tmp}"
env_script=""
python_cmd="${PYTHON:-python3}"
abacus_bin="${ABACUS_BIN:-}"
pyatb_cmd="${PYATB_CMD:-}"
librpa_bin="${LIBRPA_BIN:-}"
skip_abacus=0
skip_pyatb=0
skip_librpa=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --case-dir) case_dir="$2"; shift 2 ;;
    --run-root) run_root="$2"; shift 2 ;;
    --env-script) env_script="$2"; shift 2 ;;
    --python) python_cmd="$2"; shift 2 ;;
    --abacus-bin) abacus_bin="$2"; shift 2 ;;
    --pyatb-cmd) pyatb_cmd="$2"; shift 2 ;;
    --librpa-bin) librpa_bin="$2"; shift 2 ;;
    --skip-abacus) skip_abacus=1; shift ;;
    --skip-pyatb) skip_pyatb=1; shift ;;
    --skip-librpa) skip_librpa=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$case_dir" ]] || { usage >&2; exit 2; }
[[ -d "$case_dir" ]] || { echo "Missing case directory: $case_dir" >&2; exit 2; }
mkdir -p "$run_root"

if [[ -n "$env_script" ]]; then
  [[ -f "$env_script" ]] || { echo "Missing env script: $env_script" >&2; exit 2; }
  # shellcheck disable=SC1090
  source "$env_script"
fi

resolve_tool() {
  local explicit="$1"
  shift
  if [[ -n "$explicit" ]]; then
    printf '%s\n' "$explicit"
    return 0
  fi
  local primary="$1"
  shift
  local from_path
  from_path="$(command -v "$primary" 2>/dev/null || true)"
  if [[ -n "$from_path" ]]; then
    printf '%s\n' "$from_path"
    return 0
  fi
  local candidate
  for candidate in "$@"; do
    if [[ -n "$candidate" && -e "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

run_id="stack-smoke-$(date +%Y%m%d-%H%M%S)"
run_dir="$run_root/$(basename "$case_dir")-${run_id}"
mkdir -p "$run_dir"
cp -a "$case_dir/." "$run_dir/"

echo "INFO: copied case to $run_dir"

pass_count=0
warn_count=0
fail_count=0

note_pass() { echo "PASS: $*"; pass_count=$((pass_count + 1)); }
note_warn() { echo "WARN: $*"; warn_count=$((warn_count + 1)); }
note_fail() { echo "FAIL: $*"; fail_count=$((fail_count + 1)); }

has_scf_success() {
  [[ -f "$1/OUT.ABACUS/running_scf.log" && -f "$1/OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart" ]] && \
    grep -q 'Finish Time' "$1/OUT.ABACUS/running_scf.log" && \
    grep -q 'Total  Time' "$1/OUT.ABACUS/running_scf.log"
}

has_pyatb_success() {
  [[ -d "$1/pyatb_librpa_df" && -f "$1/pyatb_librpa_df/band_out" ]] && compgen -G "$1/pyatb_librpa_df/KS_eigenvector_*.dat" >/dev/null
}

has_exported_pyatb_bundle() {
  [[ -f "$1/band_out" ]] && compgen -G "$1/KS_eigenvector_*.dat" >/dev/null
}

has_abacus_pyatb_inputs() {
  [[ -f "$1/OUT.ABACUS/hrs1_nao.csr" && -f "$1/OUT.ABACUS/srs1_nao.csr" && -f "$1/OUT.ABACUS/rr.csr" ]]
}

resolve_exported_bundle_dir() {
  local base="$1"
  local candidate
  for candidate in "$base/input_librpa/input_librpa" "$base/input_librpa" "$base"; do
    if [[ -d "$candidate" ]] && has_exported_pyatb_bundle "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

find_librpa_rank0() {
  local dir="$1"
  find "$dir" -maxdepth 1 -type f -name 'librpa_para_nprocs_*_myid_0.out' | head -n 1
}

has_librpa_success() {
  local dir="$1"
  local rank0
  rank0="$(find_librpa_rank0 "$dir")"
  [[ -n "$rank0" ]] || return 1
  grep -q 'Timer stop:  total\.' "$rank0"
}

abacus_bin="$(resolve_tool "$abacus_bin" abacus /home/bhj/software/abacus-develop-install/bin/abacus || true)"
pyatb_cmd="$(resolve_tool "$pyatb_cmd" pyatb || true)"
librpa_bin="$(resolve_tool "$librpa_bin" chi0_main.exe /home/bhj/software/LibRPA-merge-target-install/bin/chi0_main.exe /home/bhj/LibRPA-merge-target/build_fish/chi0_main.exe || true)"

pyatb_python=""
if [[ -n "$pyatb_cmd" && -x "$pyatb_cmd" ]]; then
  shebang="$(head -n 1 "$pyatb_cmd" 2>/dev/null | sed 's/^#!//')"
  shebang="${shebang%% *}"
  if [[ -n "$shebang" && -x "$shebang" ]]; then
    pyatb_python="$shebang"
  else
    pyatb_python="$python_cmd"
  fi
else
  pyatb_python="$python_cmd"
fi

if [[ "$skip_abacus" -eq 0 ]]; then
  if has_scf_success "$run_dir"; then
    note_pass "Reused existing ABACUS SCF outputs"
  else
    if [[ -z "$abacus_bin" || ! -x "$abacus_bin" ]]; then
      note_fail "ABACUS binary not resolved"
    else
      if [[ -f "$run_dir/INPUT_scf" ]]; then
        cp "$run_dir/INPUT_scf" "$run_dir/INPUT"
      fi
      if [[ -f "$run_dir/KPT_scf" ]]; then
        cp "$run_dir/KPT_scf" "$run_dir/KPT"
      fi
      (
        cd "$run_dir"
        "$abacus_bin" > abacus-smoke.log 2>&1
      ) || note_fail "ABACUS SCF command failed; see $run_dir/abacus-smoke.log"

      if has_scf_success "$run_dir"; then
        note_pass "ABACUS SCF smoke test passed"
      else
        note_fail "ABACUS SCF success markers are incomplete"
      fi
    fi
  fi
else
  note_warn "Skipped ABACUS stage by request"
fi

if [[ "$skip_pyatb" -eq 0 ]]; then
  if has_pyatb_success "$run_dir"; then
    note_pass "Reused existing PYATB outputs"
  else
    exported_bundle_dir="$(resolve_exported_bundle_dir "$run_dir" || true)"
    if ! "$pyatb_python" - <<'PY' >/dev/null 2>&1
import pyatb
PY
    then
      note_fail "PYATB import is unavailable via $pyatb_python"
    elif [[ ! -f "$run_dir/OUT.ABACUS/running_scf.log" ]]; then
      note_fail "Cannot run PYATB smoke test without ABACUS SCF outputs"
    elif ! has_abacus_pyatb_inputs "$run_dir"; then
      if [[ -n "$exported_bundle_dir" ]]; then
        note_warn "Current ABACUS SCF outputs do not include hrs/srs/rr CSR matrices; reusing exported PYATB-ready bundle instead"
        note_pass "Exported PYATB bundle is present at $exported_bundle_dir"
      else
        note_fail "ABACUS SCF finished but did not produce hrs/srs/rr CSR matrices needed by PYATB"
      fi
    else
      cp "$repo_root/templates/abacus-librpa-gw/template/get_diel.py" "$run_dir/get_diel.py"
      cp "$repo_root/templates/abacus-librpa-gw/template/output_librpa.py" "$run_dir/output_librpa.py"
      [[ -f "$run_dir/KPT_scf" ]] || cp "$run_dir/KPT" "$run_dir/KPT_scf"
      if [[ -f "$run_dir/OUT.ABACUS/vxc_out.dat" && ! -f "$run_dir/vxc_out" ]]; then
        cp "$run_dir/OUT.ABACUS/vxc_out.dat" "$run_dir/vxc_out"
      fi
      (
        cd "$run_dir"
        "$pyatb_python" get_diel.py > pyatb-smoke.log 2>&1
      ) || note_fail "PYATB helper execution failed; see $run_dir/pyatb-smoke.log"

      if has_pyatb_success "$run_dir"; then
        note_pass "ABACUS -> PYATB smoke path passed"
      else
        note_fail "PYATB success markers are incomplete"
      fi
    fi
  fi
else
  note_warn "Skipped PYATB stage by request"
fi

if [[ "$skip_librpa" -eq 0 ]]; then
  librpa_dir=""
  if has_librpa_success "$run_dir"; then
    librpa_dir="$run_dir"
    note_pass "Reused existing LibRPA outputs in the main run directory"
  elif [[ -d "$run_dir/input_librpa" ]]; then
    librpa_dir="$(resolve_exported_bundle_dir "$run_dir" || true)"
  elif [[ -f "$run_dir/input_librpa.tar.gz" ]]; then
    mkdir -p "$run_dir/input_librpa"
    tar -xzf "$run_dir/input_librpa.tar.gz" -C "$run_dir/input_librpa"
    librpa_dir="$(resolve_exported_bundle_dir "$run_dir" || true)"
  fi

  if [[ -n "$librpa_dir" && ! -f "$librpa_dir/librpa.in" && -f "$run_dir/librpa.in" ]]; then
    cp "$run_dir/librpa.in" "$librpa_dir/librpa.in"
  fi

  if [[ -z "$librpa_dir" ]]; then
    note_warn "No LibRPA input bundle was found; skipped LibRPA smoke stage"
  elif has_librpa_success "$librpa_dir"; then
    note_pass "LibRPA success markers already exist in $librpa_dir"
  else
    if [[ -z "$librpa_bin" || ! -x "$librpa_bin" ]]; then
      note_fail "LibRPA binary not resolved"
    else
      (
        cd "$librpa_dir"
        "$librpa_bin" > librpa-smoke.log 2>&1
      ) || note_fail "LibRPA command failed; see $librpa_dir/librpa-smoke.log"

      if has_librpa_success "$librpa_dir"; then
        note_pass "LibRPA smoke test passed"
      else
        note_fail "LibRPA success markers are incomplete"
      fi
    fi
  fi
else
  note_warn "Skipped LibRPA stage by request"
fi

echo "INFO: run_dir=$run_dir"
echo "SUMMARY: pass=$pass_count warn=$warn_count fail=$fail_count"
if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi
echo 'DONE: stack smoke test passed'
