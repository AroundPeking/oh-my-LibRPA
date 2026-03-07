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
  "$workspace/skills/abacus-librpa-gw/SKILL.md" \
  "$workspace/skills/abacus-librpa-rpa/SKILL.md" \
  "$workspace/skills/abacus-librpa-debug/SKILL.md" \
  "$installed_root/rules/cards/librpa-default-presets.yml" \
  "$installed_root/templates/abacus-librpa-gw/minimal/INPUT_scf.template" \
  "$installed_root/templates/run-log.template.md"; do
  if [[ -f "$path" ]]; then
    pass "Found required file: $path"
  else
    fail "Missing required file: $path"
  fi
done

for script in \
  "$installed_root/scripts/check_consistency.sh" \
  "$installed_root/scripts/intake_preflight.sh" \
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

if "$installed_root/scripts/intake_preflight.sh" "$case_rpa" --mode rpa --system-type molecule >/dev/null 2>&1; then
  pass 'intake_preflight.sh produced a summary on a minimal RPA case'
else
  fail 'intake_preflight.sh failed on a minimal RPA case'
fi

echo "SUMMARY: pass=$pass_count fail=$fail_count"

if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi

echo 'DONE: self-test passed'
