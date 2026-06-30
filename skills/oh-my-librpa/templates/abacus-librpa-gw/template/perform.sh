#!/usr/bin/env bash
set -eo pipefail

if [[ -f ./env.sh ]]; then
  # shellcheck disable=SC1091
  source ./env.sh
fi
set -u

python3_exec="${python3_exec:-${OH_MY_LIBRPA_PYTHON3_EXEC:-python3}}"
mpirun_exec="${mpirun_exec:-${OH_MY_LIBRPA_MPI_LAUNCHER_CMD:-mpirun}}"
pyatb_mpi_ranks="${pyatb_mpi_ranks:-1}"

require_exec() {
  local path="$1"
  local label="$2"

  if [[ "$path" == */* ]]; then
    [[ -x "$path" ]] || { echo "Missing executable for $label: $path" >&2; exit 1; }
    return 0
  fi

  command -v "$path" >/dev/null 2>&1 || { echo "Executable for $label not found in PATH: $path" >&2; exit 1; }
}

require_file() {
  local path="$1"
  [[ -f "$path" ]] || { echo "Missing required file: $path" >&2; exit 1; }
}

require_glob() {
  local pattern="$1"
  compgen -G "$pattern" >/dev/null || { echo "Missing required files matching: $pattern" >&2; exit 1; }
}

require_exec "$python3_exec" python3_exec
require_exec "$mpirun_exec" mpirun_exec
require_file get_diel.py
require_file output_librpa.py

if [[ -n "${OH_MY_LIBRPA_LD_PRELOAD:-}" ]]; then
  export LD_PRELOAD="$OH_MY_LIBRPA_LD_PRELOAD"
fi
"$mpirun_exec" -np "$pyatb_mpi_ranks" "$python3_exec" get_diel.py
require_file pyatb_librpa_df/band_out
require_file pyatb_librpa_df/k_path_info
require_file pyatb_librpa_df/velocity_matrix
require_glob 'pyatb_librpa_df/KS_eigenvector_*.dat'
require_file band_out
require_glob 'KS_eigenvector_*.dat'
