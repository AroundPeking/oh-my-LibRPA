#!/usr/bin/env bash
set -euo pipefail

VERIFY_MESSAGE=""
LAST_TARGET_OUTPUT=""
LAST_COMMAND_EXIT_CODE=0
TARGET_BG_PID=""

workflow_now() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

run_target_command() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"
  local body="$4"

  local wrapped="cd $(printf '%q' "$run_dir") && $body"

  if [[ "$compute_location" == "server" ]]; then
    ssh "$ssh_target" "bash -lc $(printf '%q' "$wrapped")"
  else
    bash -lc "$wrapped"
  fi
}

capture_target_command() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"
  local body="$4"

  local output
  local command_status=0
  if output="$(run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body" 2>&1)"; then
    LAST_TARGET_OUTPUT="$output"
    LAST_COMMAND_EXIT_CODE=0
    return 0
  fi

  command_status=$?
  LAST_TARGET_OUTPUT="$output"
  LAST_COMMAND_EXIT_CODE=$command_status
  return 1
}

start_target_command_bg() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"
  local body="$4"

  local wrapped="cd $(printf '%q' "$run_dir") && $body"

  if [[ "$compute_location" == "server" ]]; then
    ssh "$ssh_target" "bash -lc $(printf '%q' "$wrapped")" &
  else
    bash -lc "$wrapped" &
  fi

  TARGET_BG_PID=$!
}

verify_scf_stage() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local body='[[ -s OUT.ABACUS/running_scf.log && -s OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart ]] && grep -Eq "Finish[[:space:]]+Time" OUT.ABACUS/running_scf.log && grep -Eq "Total[[:space:]]+Time" OUT.ABACUS/running_scf.log'
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='`running_scf.log` contains `Finish Time` and `Total Time` (allowing merged-branch spacing changes), and `ABACUS-CHARGE-DENSITY.restart` exists.'
    return 0
  fi

  VERIFY_MESSAGE='SCF success markers are incomplete: expected `running_scf.log` with `Finish Time`/`Total Time` and `ABACUS-CHARGE-DENSITY.restart`.'
  return 1
}

verify_pyatb_stage() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local body='[[ -d pyatb_librpa_df && -f pyatb_librpa_df/band_out ]] && compgen -G "pyatb_librpa_df/KS_eigenvector_*.dat" >/dev/null'
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='`pyatb_librpa_df/` exists, `band_out` exists, and `KS_eigenvector_*.dat` files were generated.'
    return 0
  fi

  VERIFY_MESSAGE='pyatb success markers are incomplete: expected `pyatb_librpa_df/band_out` and at least one `KS_eigenvector_*.dat`.'
  return 1
}

verify_nscf_stage() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local body='[[ -s OUT.ABACUS/running_nscf.log && -s OUT.ABACUS/eig.txt ]] && grep -Eq "Finish[[:space:]]+Time" OUT.ABACUS/running_nscf.log && grep -Eq "Total[[:space:]]+Time" OUT.ABACUS/running_nscf.log'
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='`running_nscf.log` contains `Finish Time` and `Total Time` (allowing merged-branch spacing changes), and `eig.txt` exists.'
    return 0
  fi

  VERIFY_MESSAGE='NSCF success markers are incomplete: expected `running_nscf.log` with `Finish Time`/`Total Time` and `eig.txt`.'
  return 1
}

verify_preprocess_stage() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local body='[[ -s band_kpath_info ]] && compgen -G "band_KS_*" >/dev/null && compgen -G "band_vxc*" >/dev/null'
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='`band_kpath_info`, `band_KS_*`, and `band_vxc*` were generated.'
    return 0
  fi

  VERIFY_MESSAGE='Preprocess success markers are incomplete: expected `band_kpath_info`, `band_KS_*`, and `band_vxc*`.'
  return 1
}

find_librpa_rank0_output() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  capture_target_command "$compute_location" "$ssh_target" "$run_dir" 'ls librpa_para_nprocs_*_myid_0.out 2>/dev/null | head -n 1'
  if [[ -n "$LAST_TARGET_OUTPUT" ]]; then
    printf '%s
' "$LAST_TARGET_OUTPUT"
    return 0
  fi
  return 1
}

verify_molecular_gw_prereqs_stage() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local body='[[ -s vxc_out ]] && compgen -G "coulomb_mat_*.txt" >/dev/null'
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='`vxc_out` exists and at least one `coulomb_mat_*.txt` file is present for the molecular GW LibRPA step.'
    return 0
  fi

  VERIFY_MESSAGE='Missing molecular GW prerequisites for LibRPA: expected `vxc_out` and at least one `coulomb_mat_*.txt` file in the working directory.'
  return 1
}

verify_librpa_success_stage() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local rank0
  rank0="$(find_librpa_rank0_output "$compute_location" "$ssh_target" "$run_dir" || true)"
  if [[ -z "$rank0" ]]; then
    VERIFY_MESSAGE='LibRPA rank-0 output file is missing.'
    return 1
  fi

  local body="grep -q 'Timer stop:  total\.' '$rank0' && compgen -G 'GW_band_spin_*' >/dev/null"
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='LibRPA rank-0 output reached `Timer stop:  total.` and `GW_band_spin_*` exists.'
    return 0
  fi

  body="grep -q 'libRPA finished successfully' '$rank0' && [[ -f band_out && -f vxc_out ]] && compgen -G 'coulomb_mat_*.txt' >/dev/null"
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='LibRPA rank-0 output reports `libRPA finished successfully`, and the molecular GW outputs `band_out`, `vxc_out`, and `coulomb_mat_*.txt` exist.'
    return 0
  fi

  VERIFY_MESSAGE='LibRPA did not reach the final completion markers: expected either `Timer stop:  total.` with `GW_band_spin_*`, or the molecular GW markers `libRPA finished successfully` + `band_out` + `vxc_out` + `coulomb_mat_*.txt`.'
  return 1
}

verify_rpa_librpa_success_stage() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local rank0
  rank0="$(find_librpa_rank0_output "$compute_location" "$ssh_target" "$run_dir" || true)"
  if [[ -z "$rank0" ]]; then
    VERIFY_MESSAGE='LibRPA rank-0 output file is missing.'
    return 1
  fi

  local body="grep -q 'Timer stop:  total\.' '$rank0'"
  if run_target_command "$compute_location" "$ssh_target" "$run_dir" "$body"; then
    VERIFY_MESSAGE='LibRPA rank-0 output reached `Timer stop:  total.`.'
    return 0
  fi

  VERIFY_MESSAGE='LibRPA did not reach the final completion marker: expected `Timer stop:  total.` in rank-0 output.'
  return 1
}

librpa_running_observation() {
  local compute_location="$1"
  local ssh_target="$2"
  local run_dir="$3"

  local rank0
  rank0="$(find_librpa_rank0_output "$compute_location" "$ssh_target" "$run_dir" || true)"
  if [[ -z "$rank0" ]]; then
    printf '%s' 'LibRPA process started; waiting for rank-0 output to appear.'
    return 0
  fi

  printf '%s' "LibRPA is running; monitoring rank-0 output ${rank0}."
}
