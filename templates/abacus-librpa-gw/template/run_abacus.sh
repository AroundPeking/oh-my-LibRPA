#!/usr/bin/env bash
#SBATCH -p formal-6226R
#SBATCH -N 4
#SBATCH --cpus-per-task=32
#SBATCH --ntasks-per-node=1
#SBATCH -J BN
#SBATCH --mem=256000
##SBATCH --dependency=afterok:528530

set -eo pipefail

# Baseline template: periodic GW + shrink + symmetry lane.
# Prefer sourcing a materialized `env.sh` generated from a host profile.
# If the host depends on ~/.bashrc or conda activation, make those steps explicit in env.sh.

if [[ -f ./env.sh ]]; then
  # shellcheck disable=SC1091
  source ./env.sh
fi
set -u

python3_exec="${python3_exec:-${OH_MY_LIBRPA_PYTHON3_EXEC:-python3}}"
libri_root="${libri_root:-${OH_MY_LIBRPA_LIBRI_ROOT:-}}"
abacus_work="${abacus_work:-${OH_MY_LIBRPA_ABACUS_EXEC:-}}"
librpa_work="${librpa_work:-${OH_MY_LIBRPA_LIBRPA_EXEC:-}}"
mpirun_exec="${mpirun_exec:-${OH_MY_LIBRPA_MPI_LAUNCHER_CMD:-mpirun}}"
mpi_ranks="${mpi_ranks:-4}"
libri_mpi_ranks="${libri_mpi_ranks:-$mpi_ranks}"
pyatb_mpi_ranks="${pyatb_mpi_ranks:-1}"
omp_threads="${omp_threads:-${SLURM_CPUS_PER_TASK:-32}}"

export OMP_NUM_THREADS="$omp_threads"

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

log_runtime_config() {
  cat > resolved-runtime.env <<EOF
python3_exec=$python3_exec
libri_root=$libri_root
abacus_work=$abacus_work
librpa_work=$librpa_work
mpirun_exec=$mpirun_exec
mpi_ranks=$mpi_ranks
pyatb_mpi_ranks=$pyatb_mpi_ranks
libri_mpi_ranks=$libri_mpi_ranks
omp_threads=$omp_threads
PATH=$PATH
LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-}
CONDA_DEFAULT_ENV=${CONDA_DEFAULT_ENV:-}
EOF
}

[[ -n "$abacus_work" ]] || { echo 'Missing abacus_work; set it in env.sh or export OH_MY_LIBRPA_ABACUS_EXEC.' >&2; exit 1; }
[[ -n "$librpa_work" ]] || { echo 'Missing librpa_work; set it in env.sh or export OH_MY_LIBRPA_LIBRPA_EXEC.' >&2; exit 1; }
require_exec "$python3_exec" python3_exec
require_exec "$abacus_work" abacus_work
require_exec "$librpa_work" librpa_work
require_exec "$mpirun_exec" mpirun_exec
require_file INPUT_scf
require_file INPUT_nscf
require_file KPT_scf
require_file KPT_nscf
require_file perform.sh
require_file get_diel.py
require_file preprocess_abacus_for_librpa_band.py
require_file output_librpa.py

chmod +x perform.sh
log_runtime_config

echo "Begin Time: $(date)"
echo "Working directory is $PWD"
echo "Resolved python3_exec: $python3_exec"
echo "Resolved libri_root: ${libri_root:-}"
echo "Resolved abacus_work: $abacus_work"
echo "Resolved librpa_work: $librpa_work"
echo "Resolved mpirun_exec: $mpirun_exec"
echo "Resolved CONDA_DEFAULT_ENV: ${CONDA_DEFAULT_ENV:-}"
echo "mpi_ranks=$mpi_ranks pyatb_mpi_ranks=$pyatb_mpi_ranks libri_mpi_ranks=$libri_mpi_ranks OMP_NUM_THREADS=$OMP_NUM_THREADS"
echo "This job runs on the following nodes: ${SLURM_JOB_NODELIST:-local}"
echo "This job has allocated ${SLURM_JOB_CPUS_PER_NODE:-unknown} cpu cores."

cp KPT_scf KPT
cp INPUT_scf INPUT
"$mpirun_exec" -np "$mpi_ranks" "$abacus_work" >> "abacus.${SLURM_JOB_ID:-manual}.out"
require_file OUT.ABACUS/running_scf.log
require_file OUT.ABACUS/ABACUS-CHARGE-DENSITY.restart
require_file OUT.ABACUS/vxc_out.dat
for symfile in irreducible_sector.txt symrot_R.txt symrot_k.txt symrot_abf_k.txt; do
  require_file "OUT.ABACUS/$symfile"
  cp -f "OUT.ABACUS/$symfile" .
done
cp -a OUT.ABACUS/vxc_out.dat vxc_out

bash ./perform.sh
require_file band_out
require_glob 'KS_eigenvector_*.dat'
require_glob 'coulomb_cut_*'

cp KPT_nscf KPT
cp INPUT_nscf INPUT
"$mpirun_exec" -np "$mpi_ranks" "$abacus_work" >> "nscf.${SLURM_JOB_ID:-manual}.out"
require_file OUT.ABACUS/running_nscf.log
if [[ ! -f OUT.ABACUS/eig.txt && ! -f OUT.ABACUS/eig_occ.txt ]]; then
  echo "Missing required file: OUT.ABACUS/eig.txt or OUT.ABACUS/eig_occ.txt" >&2
  exit 1
fi

"$python3_exec" preprocess_abacus_for_librpa_band.py
require_file band_kpath_info
require_glob 'band_KS_*'
require_glob 'band_vxc*'

OMP_NUM_THREADS="$omp_threads" "$mpirun_exec" -np "$libri_mpi_ranks" "$librpa_work" >> "LibRPA.${SLURM_JOB_ID:-manual}.out"
if ! compgen -G 'librpa_para_nprocs_*_myid_0.out' >/dev/null && ! compgen -G 'LibRPA*.out' >/dev/null; then
  echo 'Missing required files matching: librpa_para_nprocs_*_myid_0.out or LibRPA*.out' >&2
  exit 1
fi
require_glob 'GW_band_spin_*'

echo "End Time: $(date)"
