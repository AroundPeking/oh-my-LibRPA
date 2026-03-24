#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=workflow_common.sh
source "$script_dir/workflow_common.sh"

report_helper="$script_dir/report_stage.sh"

usage() {
  cat <<'EOF'
Usage:
  run_rpa_workflow.sh \
    --run-id <id> \
    --run-dir <path> \
    [--compute-location <local|server>] \
    [--ssh-target <host>] \
    [--task-label <text>] \
    [--system-type <molecule|solid|2D>] \
    [--reference-template <path>] \
    [--structure-files <text>] \
    [--input-bundle <text>] \
    [--workflow-scripts <text>] \
    [--basis-assets <text>] \
    [--task <text>] \
    [--nfreq <text>] \
    [--use-soc <text>] \
    [--nbands <text>] \
    [--kpt <text>] \
    [--archive-root <path>] \
    [--scf-cmd <command>] \
    [--librpa-cmd <command>] \
    [--librpa-poll-seconds <seconds>]

Behavior:
  - Runs the RPA path `SCF -> LibRPA`
  - Verifies SCF immediately after execution
  - Reports LibRPA as running, success, or failed
  - Calls report_stage.sh after each verified stage update
EOF
}

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "Missing required argument: $name" >&2
    usage >&2
    exit 2
  fi
}

run_id=""
run_dir=""
compute_location="local"
ssh_target=""
task_label=""
system_type="unknown"
reference_template="-"
structure_files="-"
input_bundle="-"
workflow_scripts="-"
basis_assets="-"
task_name="rpa"
nfreq="-"
use_soc="-"
nbands="-"
kpt="-"
archive_root="${OH_MY_LIBRPA_ARCHIVE_ROOT:-${CODEX_HOME:-$HOME/.codex}/workspace/librpa/oh-my-librpa}"
scf_cmd=""
librpa_cmd=""
librpa_poll_seconds=30

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) run_id="$2"; shift 2 ;;
    --run-dir) run_dir="$2"; shift 2 ;;
    --compute-location) compute_location="$2"; shift 2 ;;
    --ssh-target) ssh_target="$2"; shift 2 ;;
    --task-label) task_label="$2"; shift 2 ;;
    --system-type) system_type="$2"; shift 2 ;;
    --reference-template) reference_template="$2"; shift 2 ;;
    --structure-files) structure_files="$2"; shift 2 ;;
    --input-bundle) input_bundle="$2"; shift 2 ;;
    --workflow-scripts) workflow_scripts="$2"; shift 2 ;;
    --basis-assets) basis_assets="$2"; shift 2 ;;
    --task) task_name="$2"; shift 2 ;;
    --nfreq) nfreq="$2"; shift 2 ;;
    --use-soc) use_soc="$2"; shift 2 ;;
    --nbands) nbands="$2"; shift 2 ;;
    --kpt) kpt="$2"; shift 2 ;;
    --archive-root) archive_root="$2"; shift 2 ;;
    --scf-cmd) scf_cmd="$2"; shift 2 ;;
    --librpa-cmd) librpa_cmd="$2"; shift 2 ;;
    --librpa-poll-seconds) librpa_poll_seconds="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_value "--run-id" "$run_id"
require_value "--run-dir" "$run_dir"

if [[ "$compute_location" == "server" ]]; then
  require_value "--ssh-target" "$ssh_target"
fi

if [[ -z "$task_label" ]]; then
  task_label="rpa-${run_id}"
fi

report_stage() {
  local stage="$1"
  local status="$2"
  local started_at="$3"
  local ended_at="$4"
  local what_done="$5"
  local what_observed="$6"
  local next_step="$7"
  local key_outputs="$8"
  local final_result="${9:-}"
  local final_artifacts="${10:-}"

  "$report_helper" \
    --run-id "$run_id" \
    --mode rpa \
    --stage "$stage" \
    --status "$status" \
    --run-dir "$run_dir" \
    --task-label "$task_label" \
    --compute-location "$compute_location" \
    --system-type "$system_type" \
    --workdir "$run_dir" \
    --reference-template "$reference_template" \
    --structure-files "$structure_files" \
    --input-bundle "$input_bundle" \
    --workflow-scripts "$workflow_scripts" \
    --basis-assets "$basis_assets" \
    --task "$task_name" \
    --nfreq "$nfreq" \
    --use-soc "$use_soc" \
    --nbands "$nbands" \
    --kpt "$kpt" \
    --started-at "$started_at" \
    --ended-at "$ended_at" \
    --what-done "$what_done" \
    --what-observed "$what_observed" \
    --next-step "$next_step" \
    --key-outputs "$key_outputs" \
    --final-result "$final_result" \
    --final-artifacts "$final_artifacts" \
    --archive-root "$archive_root"
}

execute_verified_stage() {
  local stage="$1"
  local command="$2"
  local verify_function="$3"
  local success_outputs="$4"
  local next_step="$5"

  local started_at
  local ended_at
  started_at="$(workflow_now)"

  if [[ -n "$command" ]]; then
    if ! run_target_command "$compute_location" "$ssh_target" "$run_dir" "$command"; then
      ended_at="$(workflow_now)"
      report_stage "$stage" failed "$started_at" "$ended_at" "Executed ${stage} command." "Command exited non-zero during ${stage}." "Stop and inspect the command output before continuing." "${success_outputs}"
      return 1
    fi
  fi

  if "$verify_function" "$compute_location" "$ssh_target" "$run_dir"; then
    ended_at="$(workflow_now)"
    if [[ -n "$command" ]]; then
      report_stage "$stage" success "$started_at" "$ended_at" "Executed ${stage} and verified its outputs." "$VERIFY_MESSAGE" "$next_step" "$success_outputs"
    else
      report_stage "$stage" success "$started_at" "$ended_at" "Detected existing ${stage} outputs and verified them." "$VERIFY_MESSAGE" "$next_step" "$success_outputs"
    fi
    return 0
  fi

  ended_at="$(workflow_now)"
  if [[ -n "$command" ]]; then
    report_stage "$stage" failed "$started_at" "$ended_at" "Executed ${stage} but post-check verification failed." "$VERIFY_MESSAGE" "Stop and inspect the generated outputs before continuing." "$success_outputs"
  else
    report_stage "$stage" failed "$started_at" "$ended_at" "No ${stage} command was provided and existing outputs did not verify." "$VERIFY_MESSAGE" "Provide a ${stage} command or repair the existing outputs." "$success_outputs"
  fi
  return 1
}

execute_librpa_stage() {
  local started_at
  local ended_at
  started_at="$(workflow_now)"

  if [[ -z "$librpa_cmd" ]]; then
    if verify_rpa_librpa_success_stage "$compute_location" "$ssh_target" "$run_dir"; then
      ended_at="$(workflow_now)"
      report_stage librpa success "$started_at" "$ended_at" "Detected existing LibRPA outputs and verified them." "$VERIFY_MESSAGE" "Workflow complete." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out' "RPA workflow completed successfully." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out'
      return 0
    fi

    ended_at="$(workflow_now)"
    report_stage librpa failed "$started_at" "$ended_at" "No LibRPA command was provided and existing outputs did not verify." "$VERIFY_MESSAGE" "Provide a LibRPA command or repair the existing outputs." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out'
    return 1
  fi

  local runner_pid
  start_target_command_bg "$compute_location" "$ssh_target" "$run_dir" "$librpa_cmd"
  runner_pid="$TARGET_BG_PID"

  report_stage librpa running "$started_at" "$started_at" "Started the LibRPA command." "$(librpa_running_observation "$compute_location" "$ssh_target" "$run_dir")" "Keep monitoring until LibRPA reaches completion markers." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out'

  local command_status=0
  while kill -0 "$runner_pid" 2>/dev/null; do
    sleep "$librpa_poll_seconds"
  done

  if ! wait "$runner_pid"; then
    command_status=$?
  fi

  if verify_rpa_librpa_success_stage "$compute_location" "$ssh_target" "$run_dir"; then
    ended_at="$(workflow_now)"
    report_stage librpa success "$started_at" "$ended_at" "LibRPA finished and passed its completion checks." "$VERIFY_MESSAGE" "Workflow complete." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out' "RPA workflow completed successfully." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out'
    return 0
  fi

  ended_at="$(workflow_now)"
  if [[ "$command_status" -ne 0 ]]; then
    report_stage librpa failed "$started_at" "$ended_at" "LibRPA command exited with a non-zero status." "$VERIFY_MESSAGE" "Inspect rank-0 output and remote command stderr before retrying." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out'
  else
    report_stage librpa failed "$started_at" "$ended_at" "LibRPA command finished but final success markers are missing." "$VERIFY_MESSAGE" "Inspect rank-0 output before retrying." 'librpa_para_nprocs_*_myid_0.out or LibRPA*.out'
  fi
  return 1
}

execute_verified_stage scf "$scf_cmd" verify_scf_stage 'OUT.ABACUS/running_scf.log, OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart' 'Run LibRPA.'
execute_librpa_stage
