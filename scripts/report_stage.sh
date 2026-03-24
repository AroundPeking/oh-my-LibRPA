#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  report_stage.sh \
    --run-id <id> \
    --mode <gw|rpa|debug> \
    --stage <name> \
    --status <success|running|failed> \
    --run-dir <path> \
    [--task-label <text>] \
    [--compute-location <local|server>] \
    [--system-type <molecule|solid|2D>] \
    [--workdir <path>] \
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
    [--kpt-nscf <text>] \
    [--started-at <text>] \
    [--ended-at <text>] \
    [--what-done <text>] \
    [--what-observed <text>] \
    [--next-step <text>] \
    [--key-outputs <text>] \
    [--final-result <text>] \
    [--final-artifacts <text>] \
    [--archive-root <path>]

Behavior:
  - Creates/updates <run_dir>/run-report.md
  - Creates/updates an archived copy under ${CODEX_HOME:-$HOME/.codex}/workspace/librpa/oh-my-librpa/
  - Prints a short chat-ready summary to stdout
EOF
}

now() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

upper() {
  printf '%s' "$1" | tr '[:lower:]' '[:upper:]'
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

replace_summary_line() {
  local path="$1"
  local prefix="$2"
  local newline="$3"
  local tmp_file
  tmp_file="${path}.tmp"

  awk -v prefix="$prefix" -v newline="$newline" '
    BEGIN { replaced = 0 }
    index($0, prefix) == 1 && replaced == 0 {
      print newline
      replaced = 1
      next
    }
    { print }
  ' "$path" > "$tmp_file"
  mv "$tmp_file" "$path"
}

append_stage_block() {
  local path="$1"
  replace_summary_line "$path" "- updated_at:" "- updated_at: ${ended_at}"
  cat <<EOF >> "$path"

---

### Stage: ${stage}

- started_at: ${started_at}
- ended_at: ${ended_at}
- status: ${status}
- what_was_done: ${what_done}
- what_was_observed: ${what_observed}
- key_outputs: ${key_outputs}
- next: ${next_step}
EOF

  if [[ -n "$final_result" || -n "$final_artifacts" ]]; then
    cat <<EOF >> "$path"

## Final Result

- result: ${final_result}
- artifacts: ${final_artifacts}
EOF
  fi
}

init_log_if_missing() {
  local path="$1"
  if [[ -f "$path" ]]; then
    return 0
  fi

  cat <<EOF > "$path"
# Run Log: ${task_label}

## Summary

- mode: ${mode}
- system_type: ${system_type}
- compute_location: ${compute_location}
- workdir: ${workdir}
- run_report_path: ${run_report}
- archive_report_path: ${archive_report}
- started_at: ${started_at}
- updated_at: ${ended_at}

## Inputs

- structure_files: ${structure_files}
- input_bundle: ${input_bundle}
- workflow_scripts: ${workflow_scripts}
- basis_assets: ${basis_assets}
- reference_template: ${reference_template}

## Key Parameters

- task: ${task}
- nfreq: ${nfreq}
- use_soc: ${use_soc}
- nbands: ${nbands}
- KPT: ${kpt}
- KPT_nscf: ${kpt_nscf}

## Stage Timeline
EOF
}

mode=""
stage=""
status=""
run_id=""
run_dir=""
task_label=""
compute_location="unknown"
system_type="unknown"
workdir=""
reference_template="-"
structure_files="-"
input_bundle="-"
workflow_scripts="-"
basis_assets="-"
task="-"
nfreq="-"
use_soc="-"
nbands="-"
kpt="-"
kpt_nscf="-"
started_at=""
ended_at=""
what_done="-"
what_observed="-"
next_step="-"
key_outputs="-"
final_result=""
final_artifacts=""
archive_root="${OH_MY_LIBRPA_ARCHIVE_ROOT:-${CODEX_HOME:-$HOME/.codex}/workspace/librpa/oh-my-librpa}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) run_id="$2"; shift 2 ;;
    --mode) mode="$2"; shift 2 ;;
    --stage) stage="$2"; shift 2 ;;
    --status) status="$2"; shift 2 ;;
    --run-dir) run_dir="$2"; shift 2 ;;
    --task-label) task_label="$2"; shift 2 ;;
    --compute-location) compute_location="$2"; shift 2 ;;
    --system-type) system_type="$2"; shift 2 ;;
    --workdir) workdir="$2"; shift 2 ;;
    --reference-template) reference_template="$2"; shift 2 ;;
    --structure-files) structure_files="$2"; shift 2 ;;
    --input-bundle) input_bundle="$2"; shift 2 ;;
    --workflow-scripts) workflow_scripts="$2"; shift 2 ;;
    --basis-assets) basis_assets="$2"; shift 2 ;;
    --task) task="$2"; shift 2 ;;
    --nfreq) nfreq="$2"; shift 2 ;;
    --use-soc) use_soc="$2"; shift 2 ;;
    --nbands) nbands="$2"; shift 2 ;;
    --kpt) kpt="$2"; shift 2 ;;
    --kpt-nscf) kpt_nscf="$2"; shift 2 ;;
    --started-at) started_at="$2"; shift 2 ;;
    --ended-at) ended_at="$2"; shift 2 ;;
    --what-done) what_done="$2"; shift 2 ;;
    --what-observed) what_observed="$2"; shift 2 ;;
    --next-step) next_step="$2"; shift 2 ;;
    --key-outputs) key_outputs="$2"; shift 2 ;;
    --final-result) final_result="$2"; shift 2 ;;
    --final-artifacts) final_artifacts="$2"; shift 2 ;;
    --archive-root) archive_root="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_value "--run-id" "$run_id"
require_value "--mode" "$mode"
require_value "--stage" "$stage"
require_value "--status" "$status"
require_value "--run-dir" "$run_dir"

case "$status" in
  success|running|failed) ;;
  *)
    echo "Unsupported status: $status" >&2
    exit 2
    ;;
esac

if [[ -z "$task_label" ]]; then
  task_label="${mode}-${run_id}"
fi

if [[ -z "$workdir" ]]; then
  workdir="$run_dir"
fi

if [[ -z "$started_at" ]]; then
  started_at="$(now)"
fi

if [[ -z "$ended_at" ]]; then
  ended_at="$(now)"
fi

mkdir -p "$run_dir"
mkdir -p "$archive_root"

run_report="$run_dir/run-report.md"
archive_report="$archive_root/${run_id}-${mode}.md"

init_log_if_missing "$run_report"
init_log_if_missing "$archive_report"
append_stage_block "$run_report"
append_stage_block "$archive_report"

cat <<EOF
[$(upper "$mode")] ${stage} ${status}
- what was done: ${what_done}
- what was observed: ${what_observed}
- what is next: ${next_step}
- run report: ${run_report}
- archive report: ${archive_report}
EOF
