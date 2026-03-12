#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  materialize_server_profile.sh \
    --case-dir <path> \
    [--profile <name-or-path>] \
    [--force]

Behavior:
  - Resolves a host profile from `registry/host-profiles/*.env` or an explicit path
  - Writes `env.sh` into the case directory
  - Writes `.oh-my-librpa-host-profile.env` metadata into the case directory
  - Materializes explicit runtime settings for batch jobs, including explicit `.bashrc` sourcing / conda activation when the host profile requires them
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case_dir=""
profile_ref="generic-hpc-example"
force=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --case-dir) case_dir="$2"; shift 2 ;;
    --profile) profile_ref="$2"; shift 2 ;;
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
installed_root="$(cd "$script_dir/.." && pwd)"
profiles_root="$installed_root/registry/host-profiles"

profile_path="$profile_ref"
if [[ ! -f "$profile_path" ]]; then
  profile_path="$profiles_root/${profile_ref}.env"
fi
[[ -f "$profile_path" ]] || fail "host profile not found: $profile_ref"

# shellcheck disable=SC1090
source "$profile_path"

server_name="${OH_MY_LIBRPA_SERVER_NAME:-$(basename "$profile_path" .env)}"
python3_exec="${OH_MY_LIBRPA_PYTHON3_EXEC:-}"
abacus_exec="${OH_MY_LIBRPA_ABACUS_EXEC:-}"
librpa_exec="${OH_MY_LIBRPA_LIBRPA_EXEC:-}"
mpi_launcher="${OH_MY_LIBRPA_MPI_LAUNCHER:-mpirun}"
mpi_launcher_cmd="${OH_MY_LIBRPA_MPI_LAUNCHER_CMD:-mpirun}"
env_sources_raw="${OH_MY_LIBRPA_ENV_SOURCES:-}"
module_loads_raw="${OH_MY_LIBRPA_MODULE_LOADS:-}"
path_prepend="${OH_MY_LIBRPA_PATH_PREPEND:-}"
ld_library_path_prepend="${OH_MY_LIBRPA_LD_LIBRARY_PATH_PREPEND:-}"
bashrc_source="${OH_MY_LIBRPA_BASHRC_SOURCE:-}"
conda_init_source="${OH_MY_LIBRPA_CONDA_INIT_SOURCE:-}"
conda_env="${OH_MY_LIBRPA_CONDA_ENV:-}"
default_mpi_ranks="${OH_MY_LIBRPA_DEFAULT_MPI_RANKS:-4}"
default_pyatb_mpi_ranks="${OH_MY_LIBRPA_DEFAULT_PYATB_MPI_RANKS:-1}"
default_omp_threads="${OH_MY_LIBRPA_DEFAULT_OMP_THREADS:-1}"

[[ -n "$python3_exec" ]] || fail "profile is missing OH_MY_LIBRPA_PYTHON3_EXEC"
[[ -n "$abacus_exec" ]] || fail "profile is missing OH_MY_LIBRPA_ABACUS_EXEC"
[[ -n "$librpa_exec" ]] || fail "profile is missing OH_MY_LIBRPA_LIBRPA_EXEC"
[[ -n "$mpi_launcher_cmd" ]] || fail "profile is missing OH_MY_LIBRPA_MPI_LAUNCHER_CMD"

env_sh="$case_dir/env.sh"
metadata="$case_dir/.oh-my-librpa-host-profile.env"

if [[ "$force" -ne 1 ]]; then
  [[ ! -e "$env_sh" ]] || fail "env.sh already exists; rerun with --force to overwrite"
  [[ ! -e "$metadata" ]] || fail ".oh-my-librpa-host-profile.env already exists; rerun with --force to overwrite"
fi

declare -a env_sources=()
declare -a module_loads=()
IFS=';' read -r -a env_sources <<< "$env_sources_raw"
IFS=';' read -r -a module_loads <<< "$module_loads_raw"

{
  printf '%s\n' '#!/usr/bin/env bash'
  printf '%s\n' 'set -eo pipefail'
  printf '%s\n' 'set +u'
  if [[ -n "$bashrc_source" ]]; then
    printf 'source %s >/dev/null 2>&1 || true\n' "$bashrc_source"
  fi
  for cmd in "${env_sources[@]-}"; do
    [[ -n "$cmd" ]] || continue
    printf 'source %s >/dev/null 2>&1 || true\n' "$cmd"
  done
  if [[ -n "$conda_init_source" ]]; then
    printf 'source %s >/dev/null 2>&1 || true\n' "$conda_init_source"
  fi
  if [[ -n "$conda_env" ]]; then
    printf '%s\n' 'if command -v conda >/dev/null 2>&1; then'
    printf '  conda activate %q >/dev/null 2>&1 || true\n' "$conda_env"
    printf '%s\n' 'fi'
  fi
  printf '%s\n' 'if command -v module >/dev/null 2>&1; then'
  for mod in "${module_loads[@]-}"; do
    [[ -n "$mod" ]] || continue
    printf '  module load %q >/dev/null 2>&1 || true\n' "$mod"
  done
  printf '%s\n' 'fi'
  if [[ -n "$path_prepend" ]]; then
    printf 'export PATH=%q${PATH:+:${PATH}}\n' "$path_prepend"
  fi
  if [[ -n "$ld_library_path_prepend" ]]; then
    printf 'export LD_LIBRARY_PATH=%q${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}\n' "$ld_library_path_prepend"
  fi
  printf '%s\n' 'set -u'
  printf 'export OH_MY_LIBRPA_SERVER_NAME=%q\n' "$server_name"
  printf 'export python3_exec=%q\n' "$python3_exec"
  printf 'export abacus_work=%q\n' "$abacus_exec"
  printf 'export librpa_work=%q\n' "$librpa_exec"
  printf 'export mpi_launcher=%q\n' "$mpi_launcher"
  printf 'export mpirun_exec=%q\n' "$mpi_launcher_cmd"
  printf 'export mpi_ranks=${mpi_ranks:-%q}\n' "$default_mpi_ranks"
  printf 'export pyatb_mpi_ranks=${pyatb_mpi_ranks:-%q}\n' "$default_pyatb_mpi_ranks"
  printf 'export omp_threads=${omp_threads:-%q}\n' "$default_omp_threads"
} > "$env_sh"
chmod +x "$env_sh"

{
  printf 'OH_MY_LIBRPA_SERVER_NAME=%q\n' "$server_name"
  printf 'OH_MY_LIBRPA_PROFILE_SOURCE=%q\n' "$profile_path"
  printf 'OH_MY_LIBRPA_BASHRC_SOURCE=%q\n' "$bashrc_source"
  printf 'OH_MY_LIBRPA_CONDA_INIT_SOURCE=%q\n' "$conda_init_source"
  printf 'OH_MY_LIBRPA_CONDA_ENV=%q\n' "$conda_env"
  printf 'OH_MY_LIBRPA_PYTHON3_EXEC=%q\n' "$python3_exec"
  printf 'OH_MY_LIBRPA_ABACUS_EXEC=%q\n' "$abacus_exec"
  printf 'OH_MY_LIBRPA_LIBRPA_EXEC=%q\n' "$librpa_exec"
  printf 'OH_MY_LIBRPA_MPI_LAUNCHER=%q\n' "$mpi_launcher"
  printf 'OH_MY_LIBRPA_MPI_LAUNCHER_CMD=%q\n' "$mpi_launcher_cmd"
  printf 'OH_MY_LIBRPA_DEFAULT_MPI_RANKS=%q\n' "$default_mpi_ranks"
  printf 'OH_MY_LIBRPA_DEFAULT_PYATB_MPI_RANKS=%q\n' "$default_pyatb_mpi_ranks"
  printf 'OH_MY_LIBRPA_DEFAULT_OMP_THREADS=%q\n' "$default_omp_threads"
} > "$metadata"

cat <<EOF
PROFILE=$server_name
PROFILE_SOURCE=$profile_path
CASE_DIR=$case_dir
ENV_SH=$env_sh
PYTHON3_EXEC=$python3_exec
ABACUS_EXEC=$abacus_exec
LIBRPA_EXEC=$librpa_exec
MPI_LAUNCHER=$mpi_launcher
MPI_LAUNCHER_CMD=$mpi_launcher_cmd
BASHRC_SOURCE=$bashrc_source
CONDA_INIT_SOURCE=$conda_init_source
CONDA_ENV=$conda_env
EOF
