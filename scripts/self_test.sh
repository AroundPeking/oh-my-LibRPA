#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  self_test.sh \
    [--workspace <path>] \
    [--skills-root <path>] \
    [--installed-root <path>] \
    [--target <openclaw|opencode|codex>]

Behavior:
  - Validates installed skills and asset layout
  - Syntax-checks the shipped shell scripts
  - Smoke-tests report writing, route-aware checks, and intake preflight
  - Verifies the default archive root resolves relative to the active platform root
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
skills_root=""
installed_root=""
target="unknown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) workspace="$2"; shift 2 ;;
    --skills-root) skills_root="$2"; shift 2 ;;
    --installed-root) installed_root="$2"; shift 2 ;;
    --target) target="$2"; shift 2 ;;
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

platform_root="$(cd "$installed_root/.." && pwd)"

if [[ -z "$skills_root" && -n "$workspace" ]]; then
  skills_root="$workspace/skills"
fi

if [[ -z "$skills_root" ]]; then
  skills_root="$platform_root/skills"
fi

pass_count=0
fail_count=0

default_archive_root="${OH_MY_LIBRPA_ARCHIVE_ROOT:-$platform_root/librpa/oh-my-librpa}"

echo "INFO: target=$target skills_root=$skills_root installed_root=$installed_root"

for path in \
  "$skills_root/oh-my-librpa/SKILL.md" \
  "$skills_root/abacus-librpa-gw/SKILL.md" \
  "$skills_root/abacus-librpa-rpa/SKILL.md" \
  "$skills_root/abacus-librpa-debug/SKILL.md" \
  "$skills_root/abacus-pyatb-librpa-stack/SKILL.md" \
  "$installed_root/rules/cards/librpa-default-presets.yml" \
  "$installed_root/rules/cards/abacus-pyatb-librpa-env-fixes.yml" \
  "$installed_root/templates/abacus-librpa-gw/minimal/INPUT_scf.template" \
  "$installed_root/templates/env/abacus-pyatb-librpa.env.sh.template" \
  "$installed_root/docs/guide/abacus-pyatb-librpa-stack.md" \
  "$installed_root/examples/smoke-abacus-pyatb-librpa/README.md" \
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
  "$installed_root/scripts/stack_env_doctor.sh" \
  "$installed_root/scripts/stack_smoke_test.sh" \
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

run_id="selftest-$$"
archive_probe="$default_archive_root/${run_id}-debug.md"
rm -f "$archive_probe"
run_dir="$tmp_dir/run"
if "$installed_root/scripts/report_stage.sh" \
  --run-id "$run_id" \
  --mode debug \
  --stage intake \
  --status success \
  --run-dir "$run_dir" \
  --task-label self-test \
  --what-done 'Created a synthetic run report.' \
  --what-observed 'report_stage.sh completed.' \
  --next-step 'Continue self-test.' >/dev/null; then
  if [[ -f "$run_dir/run-report.md" && -f "$archive_probe" ]]; then
    pass 'report_stage.sh created both run and default archive logs'
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
