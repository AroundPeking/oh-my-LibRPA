#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
checker="$script_dir/check_consistency.sh"

usage() {
  cat <<'EOF'
Usage:
  intake_preflight.sh <case_dir> \
    [--mode <auto|gw|rpa>] \
    [--system-type <auto|molecule|solid|2D>] \
    [--compute-location <local|server>] \
    [--ssh-target <host>] \
    [--check-connectivity]

Behavior:
  - Classifies the file bundle in a case directory
  - Infers workflow mode and system type when possible
  - Runs route-aware static checks when enough inputs exist
  - Reports a compact readiness summary before execution
EOF
}

join_lines() {
  if [[ "$#" -eq 0 ]]; then
    printf '%s' '-'
    return 0
  fi

  local item
  local values=()
  for item in "$@"; do
    [[ -n "$item" ]] || continue
    values+=("$item")
  done

  if [[ "${#values[@]}" -eq 0 ]]; then
    printf '%s' '-'
    return 0
  fi

  local IFS=', '
  printf '%s' "${values[*]}"
}

detect_task_value() {
  local librpa_file="$1"
  [[ -f "$librpa_file" ]] || return 1
  awk '
    BEGIN { IGNORECASE = 1 }
    {
      line = $0
      gsub(/^[ \t]+/, "", line)
      if (line ~ /^task([ \t=]|$)/) {
        value = line
        sub(/^task[ \t]*=?[ \t]*/, "", value)
        gsub(/[ \t]+$/, "", value)
        print tolower(value)
      }
    }
  ' "$librpa_file" | tail -n 1
}

detect_kpt_triplet() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  awk '
    /^[[:space:]]*#/ { next }
    NF >= 3 && $1 ~ /^[-+0-9.]+$/ && $2 ~ /^[-+0-9.]+$/ && $3 ~ /^[-+0-9.]+$/ {
      print $1 " " $2 " " $3
      exit
    }
  ' "$file"
}

collect_lines() {
  local array_name="$1"
  local command="$2"
  local line
  eval "$array_name=()"
  while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    eval "$array_name+=(\"\$line\")"
  done < <(eval "$command")
}

case_dir=""
mode="auto"
system_type="auto"
compute_location="local"
ssh_target=""
check_connectivity=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) mode="$2"; shift 2 ;;
    --system-type) system_type="$2"; shift 2 ;;
    --compute-location) compute_location="$2"; shift 2 ;;
    --ssh-target) ssh_target="$2"; shift 2 ;;
    --check-connectivity) check_connectivity=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --*)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -z "$case_dir" ]]; then
        case_dir="$1"
        shift
      else
        echo "Unexpected positional argument: $1" >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

if [[ -z "$case_dir" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -d "$case_dir" ]]; then
  echo "Missing case directory: $case_dir" >&2
  exit 1
fi

collect_lines structure_files "find '$case_dir' -type f \\( -name 'STRU' -o -name 'geometry.in' -o -name '*.cif' -o -name '*.xyz' \\) | sed 's#^$case_dir/##' | sort"
collect_lines input_bundle "find '$case_dir' -type f \\( -name 'INPUT' -o -name 'INPUT_scf' -o -name 'INPUT_nscf' -o -name 'KPT' -o -name 'KPT_scf' -o -name 'KPT_nscf' -o -name 'librpa.in' \\) | sed 's#^$case_dir/##' | sort"
collect_lines workflow_scripts "find '$case_dir' -type f \\( -name 'get_diel.py' -o -name 'perform.sh' -o -name 'preprocess_abacus_for_librpa_band.py' -o -name 'run_abacus.sh' \\) | sed 's#^$case_dir/##' | sort"
collect_lines basis_assets "find '$case_dir' -type f \\( -name '*.orb' -o -name '*.abfs' -o -name '*.upf' \\) | sed 's#^$case_dir/##' | sort"
collect_lines archives "find '$case_dir' -type f \\( -name '*.zip' -o -name '*.tar' -o -name '*.tar.gz' -o -name '*.tgz' \\) | sed 's#^$case_dir/##' | sort"
collect_lines log_files "find '$case_dir' \\( -type f \\( -name '*.log' -o -name '*.out' -o -name 'band_out' -o -name 'band_kpath_info' -o -name 'band_KS_*' -o -name 'band_vxc*' -o -name 'GW_band_spin_*' -o -name 'eig.txt' \\) -o -type d -name 'pyatb_librpa_df' \\) | sed 's#^$case_dir/##' | sort"

resolved_mode="$mode"
if [[ "$resolved_mode" == "auto" ]]; then
  task_value="$(detect_task_value "$case_dir/librpa.in" || true)"
  case "$task_value" in
    g0w0_band) resolved_mode="gw" ;;
    rpa) resolved_mode="rpa" ;;
    *) resolved_mode="unknown" ;;
  esac
fi

resolved_system_type="$system_type"
if [[ "$resolved_system_type" == "auto" ]]; then
  triplet="$(detect_kpt_triplet "$case_dir/KPT" || detect_kpt_triplet "$case_dir/KPT_scf" || true)"
  if [[ "$triplet" == "1 1 1" ]]; then
    resolved_system_type="molecule"
  elif [[ -f "$case_dir/KPT_nscf" || -f "$case_dir/INPUT_nscf" ]]; then
    resolved_system_type="solid"
  else
    resolved_system_type="unknown"
  fi
fi

files_status="ready"
if [[ "${#structure_files[@]}" -eq 0 && "${#input_bundle[@]}" -eq 0 && "${#log_files[@]}" -eq 0 && "${#archives[@]}" -eq 0 ]]; then
  files_status="blocked"
fi

consistency_status="skipped"
consistency_notes='-'
if [[ -f "$case_dir/INPUT_scf" && -f "$case_dir/librpa.in" ]]; then
  if consistency_output="$($checker "$case_dir" --mode "$resolved_mode" --system-type "$resolved_system_type" 2>&1)"; then
    consistency_status="ready"
    consistency_notes="$(printf '%s' "$consistency_output" | tr '\n' '; ' | sed 's/; $//')"
  else
    consistency_status="blocked"
    consistency_notes="$(printf '%s' "$consistency_output" | tr '\n' '; ' | sed 's/; $//')"
  fi
fi

connectivity_status="ready"
connectivity_notes='Local compute selected.'
if [[ "$compute_location" == "server" ]]; then
  connectivity_status="pending"
  connectivity_notes='Server compute selected; login check not run yet.'

  if [[ -z "$ssh_target" ]]; then
    connectivity_notes='Server compute selected; ssh target is still missing.'
  elif [[ "$check_connectivity" -eq 1 ]]; then
    if ssh -o BatchMode=yes -o ConnectTimeout=5 "$ssh_target" 'printf ok' >/dev/null 2>&1; then
      connectivity_status="ready"
      connectivity_notes="SSH login check passed for $ssh_target."
    else
      connectivity_status="blocked"
      connectivity_notes="SSH login check failed for $ssh_target."
    fi
  else
    connectivity_notes="Server target $ssh_target is set; login check was intentionally skipped."
  fi
fi

missing_items=()
if [[ "${#structure_files[@]}" -eq 0 && "${#input_bundle[@]}" -eq 0 && "${#log_files[@]}" -eq 0 && "${#archives[@]}" -eq 0 ]]; then
  missing_items+=("upload structure, input bundle, logs, or archive")
fi
if [[ "$resolved_mode" == "gw" && "$resolved_system_type" != "molecule" ]]; then
  [[ -f "$case_dir/INPUT_nscf" ]] || missing_items+=("INPUT_nscf")
  [[ -f "$case_dir/KPT_nscf" ]] || missing_items+=("KPT_nscf")
fi
if [[ "$compute_location" == "server" && -z "$ssh_target" ]]; then
  missing_items+=("ssh target")
fi

runnable_status="ready"
if [[ "$files_status" == "blocked" || "$consistency_status" == "blocked" || "$connectivity_status" == "blocked" ]]; then
  runnable_status="blocked"
elif [[ "$connectivity_status" == "pending" || "$resolved_mode" == "unknown" || "$resolved_system_type" == "unknown" ]]; then
  runnable_status="pending"
fi

next_step='Proceed with route-specific generation or execution.'
if [[ "$runnable_status" == "blocked" ]]; then
  next_step="Fill the missing items first: $(join_lines "${missing_items[@]}")."
elif [[ "$runnable_status" == "pending" ]]; then
  if [[ "$compute_location" == "server" && "$connectivity_status" != "ready" ]]; then
    next_step='Confirm VPN if needed, then run server connectivity/login checks.'
  elif [[ "$resolved_mode" == "unknown" || "$resolved_system_type" == "unknown" ]]; then
    next_step='Confirm workflow mode and system type, then rerun preflight.'
  fi
fi

echo '[INTAKE] preflight summary'
echo "- case directory: $case_dir"
echo "- detected mode: $resolved_mode"
echo "- detected system type: $resolved_system_type"
echo "- files badge: $files_status"
echo "- consistency badge: $consistency_status"
echo "- connectivity badge: $connectivity_status"
echo "- runnable badge: $runnable_status"
echo "- structure files: $(join_lines "${structure_files[@]-}")"
echo "- input bundle: $(join_lines "${input_bundle[@]-}")"
echo "- workflow scripts: $(join_lines "${workflow_scripts[@]-}")"
echo "- basis assets: $(join_lines "${basis_assets[@]-}")"
echo "- logs/results: $(join_lines "${log_files[@]-}")"
echo "- archives: $(join_lines "${archives[@]-}")"
echo "- missing items: $(join_lines "${missing_items[@]-}")"
echo "- consistency notes: $consistency_notes"
echo "- connectivity notes: $connectivity_notes"
echo "- next step: $next_step"
