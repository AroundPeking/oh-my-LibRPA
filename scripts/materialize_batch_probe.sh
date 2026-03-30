#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  materialize_batch_probe.sh \
    --case-dir <path> \
    [--profile <name-or-path>] \
    [--probe-ranks <n>] \
    [--force]

Behavior:
  - Ensures `env.sh` exists for the selected host profile
  - Writes `probe_batch.sh` into the case directory
  - The probe checks PATH, python3, launcher resolution, and a minimal MPI hostname smoke test
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case_dir=""
profile_ref="generic-hpc-example"
probe_ranks=4
force=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --case-dir) case_dir="$2"; shift 2 ;;
    --profile) profile_ref="$2"; shift 2 ;;
    --probe-ranks) probe_ranks="$2"; shift 2 ;;
    --force) force=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "$case_dir" ]] || fail "missing required argument: --case-dir"
mkdir -p "$case_dir"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
profile_helper="$script_dir/materialize_server_profile.sh"
probe_script="$case_dir/probe_batch.sh"

if [[ ! -f "$case_dir/env.sh" ]]; then
  "$profile_helper" --case-dir "$case_dir" --profile "$profile_ref"
fi

if [[ -f "$probe_script" && "$force" -ne 1 ]]; then
  fail "probe_batch.sh already exists; rerun with --force to overwrite"
fi

cat > "$probe_script" <<EOF
#!/usr/bin/env bash
set -eo pipefail
source ./env.sh

echo '[PROBE] begin'
echo "server=\${OH_MY_LIBRPA_SERVER_NAME:-unknown}"
echo "hostname=\$(hostname)"
echo "pwd=\$PWD"
echo "PATH=\$PATH"
echo "LD_LIBRARY_PATH=\${LD_LIBRARY_PATH:-}"
echo "CONDA_DEFAULT_ENV=\${CONDA_DEFAULT_ENV:-}"
echo "python3_exec=\$python3_exec"
echo "libri_root=\${libri_root:-}"
echo "abacus_work=\$abacus_work"
echo "librpa_work=\$librpa_work"
echo "mpirun_exec=\$mpirun_exec"

[[ -x "\$python3_exec" ]] || { echo '[PROBE] missing python3_exec' >&2; exit 1; }
if [[ -n "\${libri_root:-}" ]]; then
  [[ -d "\$libri_root" ]] || { echo '[PROBE] missing libri_root directory' >&2; exit 1; }
fi
[[ -x "\$abacus_work" ]] || { echo '[PROBE] missing abacus executable' >&2; exit 1; }
[[ -x "\$librpa_work" ]] || { echo '[PROBE] missing librpa executable' >&2; exit 1; }
[[ -x "\$mpirun_exec" ]] || command -v "\$mpirun_exec" >/dev/null 2>&1 || { echo '[PROBE] missing launcher executable' >&2; exit 1; }

"\$python3_exec" --version
"\$mpirun_exec" -np ${probe_ranks} /bin/hostname

echo '[PROBE] done'
EOF
chmod +x "$probe_script"

echo "PROBE_SCRIPT=$probe_script"
