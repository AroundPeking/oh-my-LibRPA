#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  stack_env_doctor.sh \
    [--env-script <path>] \
    [--python <path>] \
    [--abacus-bin <path>] \
    [--pyatb-cmd <path>] \
    [--librpa-bin <path>] \
    [--case-dir <path>] \
    [--format <text|markdown>]

Behavior:
  - Audits the local ABACUS + PYATB + LibRPA environment
  - Checks oneAPI/compiler basics, Python/venv, runtime binaries, and common library-path issues
  - Optionally runs intake and static checks on a supplied case directory
EOF
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

format="text"
env_script=""
python_cmd="${PYTHON:-python3}"
abacus_bin="${ABACUS_BIN:-}"
pyatb_cmd="${PYATB_CMD:-}"
librpa_bin="${LIBRPA_BIN:-}"
case_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-script) env_script="$2"; shift 2 ;;
    --python) python_cmd="$2"; shift 2 ;;
    --abacus-bin) abacus_bin="$2"; shift 2 ;;
    --pyatb-cmd) pyatb_cmd="$2"; shift 2 ;;
    --librpa-bin) librpa_bin="$2"; shift 2 ;;
    --case-dir) case_dir="$2"; shift 2 ;;
    --format) format="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "$format" in
  text|markdown) ;;
  *) echo "Unsupported format: $format" >&2; exit 2 ;;
esac

if [[ -n "$env_script" ]]; then
  [[ -f "$env_script" ]] || { echo "Missing env script: $env_script" >&2; exit 2; }
  # shellcheck disable=SC1090
  source "$env_script"
fi

pass_count=0
warn_count=0
fail_count=0

emit() {
  local level="$1"
  local message="$2"
  if [[ "$format" == "markdown" ]]; then
    printf -- '- %s: %s\n' "$level" "$message"
  else
    printf '%s: %s\n' "$level" "$message"
  fi
}

note_pass() { emit PASS "$1"; pass_count=$((pass_count + 1)); }
note_warn() { emit WARN "$1"; warn_count=$((warn_count + 1)); }
note_fail() { emit FAIL "$1"; fail_count=$((fail_count + 1)); }

has_cmd() {
  command -v "$1" >/dev/null 2>&1
}

first_existing() {
  local candidate
  for candidate in "$@"; do
    if [[ -n "$candidate" && -e "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

resolve_tool() {
  local explicit="$1"
  shift
  if [[ -n "$explicit" ]]; then
    printf '%s\n' "$explicit"
    return 0
  fi
  local from_path
  from_path="$(command -v "$1" 2>/dev/null || true)"
  if [[ -n "$from_path" ]]; then
    printf '%s\n' "$from_path"
    return 0
  fi
  shift || true
  first_existing "$@" || true
}

run_capture() {
  bash -lc "$1" 2>&1
}

host_kind="LINUX"
if [[ -n "${WSL_DISTRO_NAME:-}" ]] || grep -qi microsoft /proc/version 2>/dev/null; then
  host_kind="WSL"
fi
note_pass "Host detected: $host_kind"

for cmd in git cmake "$python_cmd"; do
  if has_cmd "$cmd"; then
    note_pass "Found command: $cmd"
  else
    note_fail "Missing command: $cmd"
  fi
done

if "$python_cmd" -m venv --help >/dev/null 2>&1; then
  note_pass "Python venv support is available via $python_cmd -m venv"
else
  note_fail "Python venv support is missing for $python_cmd"
fi

if [[ -f /opt/intel/oneapi/setvars.sh ]]; then
  note_pass "oneAPI setvars found at /opt/intel/oneapi/setvars.sh"
else
  note_warn "oneAPI setvars not found at /opt/intel/oneapi/setvars.sh"
fi

for cmd in icpx ifx mpiicpx mpiifx; do
  if has_cmd "$cmd"; then
    note_pass "Found oneAPI compiler/runtime command: $cmd"
  else
    note_warn "Missing expected oneAPI command: $cmd"
  fi
done

abacus_bin="$(resolve_tool "$abacus_bin" abacus /home/bhj/software/abacus-develop-install/bin/abacus)"
if [[ -n "$abacus_bin" && -x "$abacus_bin" ]]; then
  version_out="$("$abacus_bin" --version 2>&1 || true)"
  if [[ -n "$version_out" ]]; then
    note_pass "ABACUS resolved at $abacus_bin"
  else
    note_warn "ABACUS resolved at $abacus_bin but version output was empty"
  fi
else
  note_warn "ABACUS binary not resolved; pass --abacus-bin or source an env script"
fi

pyatb_cmd="$(resolve_tool "$pyatb_cmd" pyatb)"
pyatb_python=""
if [[ -n "$pyatb_cmd" && -x "$pyatb_cmd" ]]; then
  shebang="$(head -n 1 "$pyatb_cmd" 2>/dev/null | sed 's/^#!//')"
  shebang="${shebang%% *}"
  if [[ -n "$shebang" && -x "$shebang" ]]; then
    pyatb_python="$shebang"
  else
    pyatb_python="$python_cmd"
  fi

  if "$pyatb_python" - <<'PY' >/dev/null 2>&1
import pyatb
print(pyatb.__file__)
PY
  then
    note_pass "PYATB import works via $pyatb_python (launcher: $pyatb_cmd)"
  else
    launcher_out="$("$pyatb_cmd" 2>&1 || true)"
    if printf '%s' "$launcher_out" | grep -qi 'No such file or directory: .*Input'; then
      note_pass "PYATB launcher is functional at $pyatb_cmd (it reached runtime input loading)"
    else
      note_fail "PYATB launcher exists at $pyatb_cmd but import/runtime bootstrap failed"
    fi
  fi
else
  note_warn "PYATB launcher not resolved; pass --pyatb-cmd or activate the PYATB venv"
fi

librpa_bin="$(resolve_tool "$librpa_bin" chi0_main.exe /home/bhj/software/LibRPA-merge-target-install/bin/chi0_main.exe /home/bhj/LibRPA-merge-target/build_fish/chi0_main.exe)"
if [[ -n "$librpa_bin" && -x "$librpa_bin" ]]; then
  note_pass "LibRPA binary resolved at $librpa_bin"
  if has_cmd ldd; then
    ldd_out="$(ldd "$librpa_bin" 2>&1 || true)"
    if printf '%s' "$ldd_out" | grep -q 'not found'; then
      note_fail "LibRPA runtime libraries are incomplete for $librpa_bin"
    else
      note_pass "LibRPA shared-library dependencies resolve cleanly under ldd"
    fi
    if printf '%s' "$ldd_out" | grep -qi 'libqsgw'; then
      note_pass "LibRPA sees libqsgw in the current runtime search path"
    else
      note_warn "LibRPA ldd output did not mention libqsgw explicitly; verify the matching runtime tree if this build expects it"
    fi
  fi
else
  note_warn "LibRPA binary not resolved; pass --librpa-bin or source an env script"
fi

for pkg in numpy scipy mpi4py pybind11; do
  if "$python_cmd" - <<PY >/dev/null 2>&1
import ${pkg}
PY
  then
    note_pass "Python package import works in $python_cmd: $pkg"
  else
    note_warn "Python package import failed in $python_cmd: $pkg"
  fi
done

if [[ -n "$case_dir" ]]; then
  [[ -d "$case_dir" ]] || { note_fail "Case directory does not exist: $case_dir"; case_dir=""; }
fi

if [[ -n "$case_dir" ]]; then
  if "$script_dir/intake_preflight.sh" "$case_dir" >/dev/null 2>&1; then
    note_pass "intake_preflight.sh accepted case directory: $case_dir"
  else
    note_warn "intake_preflight.sh reported issues for case directory: $case_dir"
  fi

  if "$script_dir/check_consistency.sh" "$case_dir" --mode auto --system-type auto >/dev/null 2>&1; then
    note_pass "check_consistency.sh passed for case directory: $case_dir"
  else
    note_warn "check_consistency.sh reported route/input issues for case directory: $case_dir"
  fi
fi

emit INFO "SUMMARY: pass=$pass_count warn=$warn_count fail=$fail_count"
if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi
emit INFO 'DONE: environment doctor passed without hard failures'
