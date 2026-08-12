from __future__ import annotations

import shlex
from typing import Mapping


CONTROLLED_PERIODIC_STAGES = ("scf", "pyatb", "nscf", "preprocess", "librpa")


def stage_job_name(run_id: str, stage: str) -> str:
    if stage not in CONTROLLED_PERIODIC_STAGES:
        raise ValueError(f"unsupported controlled stage: {stage}")
    return f"oml-{run_id}-{stage}"


def _walltime(minutes: int) -> str:
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:00"


def render_env(
    runtime: Mapping[str, str | int],
    *,
    environment: Mapping[str, str],
    run_id: str,
    plan_digest: str,
) -> str:
    values: dict[str, str | int] = {
        **environment,
        "OML_RUN_ID": run_id,
        "OML_PLAN_DIGEST": plan_digest,
        "OML_PYTHON": runtime["python"],
        "OML_MPI_LAUNCHER": runtime["mpi_launcher"],
        "OML_ABACUS": runtime["abacus"],
        "OML_LIBRPA": runtime["librpa"],
        "OML_MPI_RANKS": runtime["mpi_ranks"],
        "OML_PYATB_MPI_RANKS": runtime["pyatb_mpi_ranks"],
        "OML_OMP_THREADS": runtime["omp_threads"],
        "python3_exec": runtime["python"],
        "mpirun_exec": runtime["mpi_launcher"],
        "abacus_work": runtime["abacus"],
        "librpa_work": runtime["librpa"],
        "mpi_ranks": runtime["mpi_ranks"],
        "libri_mpi_ranks": runtime["mpi_ranks"],
        "pyatb_mpi_ranks": runtime["pyatb_mpi_ranks"],
        "omp_threads": runtime["omp_threads"],
    }
    return "".join(f"export {key}={shlex.quote(str(value))}\n" for key, value in values.items())


def _stage_body(stage: str) -> str:
    bodies = {
        "scf": """
cp -- "KPT_scf" "KPT"
cp -- "INPUT_scf" "INPUT"
"$OML_MPI_LAUNCHER" -np "$OML_MPI_RANKS" "$OML_ABACUS" > "abacus.${SLURM_JOB_ID:-manual}.out" 2>&1
test -s "OUT.ABACUS/vxc_out.dat"
cp -- "OUT.ABACUS/vxc_out.dat" "vxc_out"
""",
        "pyatb": """
OML_CONTROLLED_EXECUTION=1 bash -- "perform.sh" > "pyatb.${SLURM_JOB_ID:-manual}.out" 2>&1
""",
        "nscf": """
cp -- "KPT_nscf" "KPT"
cp -- "INPUT_nscf" "INPUT"
"$OML_MPI_LAUNCHER" -np "$OML_MPI_RANKS" "$OML_ABACUS" > "nscf.${SLURM_JOB_ID:-manual}.out" 2>&1
""",
        "preprocess": """
"$OML_PYTHON" "preprocess_abacus_for_librpa_band.py" > "preprocess.${SLURM_JOB_ID:-manual}.out" 2>&1
""",
        "librpa": """
OMP_NUM_THREADS="$OML_OMP_THREADS" "$OML_MPI_LAUNCHER" -np "$OML_MPI_RANKS" "$OML_LIBRPA" > "LibRPA.${SLURM_JOB_ID:-manual}.out" 2>&1
""",
    }
    try:
        return bodies[stage].lstrip()
    except KeyError as exc:
        raise ValueError(f"unsupported controlled stage: {stage}") from exc


def render_stage_script(
    stage: str,
    *,
    run_id: str,
    resources: Mapping[str, str | int],
) -> str:
    if stage not in CONTROLLED_PERIODIC_STAGES:
        raise ValueError(f"unsupported controlled stage: {stage}")
    job_name = stage_job_name(run_id, stage)
    return f"""#!/usr/bin/env bash
#SBATCH --partition={resources['partition']}
#SBATCH --nodes={resources['nodes']}
#SBATCH --ntasks-per-node={resources['ntasks_per_node']}
#SBATCH --cpus-per-task={resources['cpus_per_task']}
#SBATCH --mem={resources['memory_mb']}M
#SBATCH --time={_walltime(int(resources['walltime_minutes']))}
#SBATCH --job-name={job_name}

set -euo pipefail
run_dir="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/../.." && pwd)"
cd "$run_dir"
source ".oml/env.sh"
export OMP_NUM_THREADS="$OML_OMP_THREADS"
export PYTHONDONTWRITEBYTECODE=1
: "${{OML_ATTEMPT_ID:?missing controlled attempt identity}}"
mkdir -p ".oml/stage-results"
printf 'RUNNING:%s\n' "$OML_ATTEMPT_ID" > ".oml/stage-results/{stage}.status"
trap 'status=$?; if [[ $status -eq 0 ]]; then printf "COMMAND_COMPLETED:%s\\n" "$OML_ATTEMPT_ID"; else printf "COMMAND_FAILED:%s:%s\\n" "$status" "$OML_ATTEMPT_ID"; fi > ".oml/stage-results/{stage}.status"' EXIT

{_stage_body(stage)}"""
