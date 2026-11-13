from __future__ import annotations

import shlex
from typing import Mapping


CONTROLLED_PERIODIC_STAGES = ("scf", "pyatb", "nscf", "preprocess", "librpa")

# Buffering for the Fortran producer stage.
#
# FHI-aims writes its Coulomb export one complex number per WRITE. At 128 atoms
# that is about 9.7e8 calls, and an unbuffered runtime turns each one into a
# file-system operation. Measured on fisherd with ifx, writing 3e7 values one
# per WRITE: 36.4 s unbuffered, 20.6 s with FORT_BUFFERED=TRUE (1.77x). The
# reported end-to-end effect at 128 atoms is 19 min -> under 2 min for the same
# files, byte for byte.
#
# The two vendor runtimes spell the switch differently and setting the wrong one
# is not harmless: gfortran already buffers by default, and
# GFORTRAN_UNBUFFERED_ALL=1 turns buffering off - measured 33.2 s -> 50.7 s on
# the same payload. So the pair below sets ifx/ifort on and asserts gfortran's
# default rather than leaving either to chance.
#
# Scope, stated plainly: every stage OML can currently execute launches ABACUS,
# LibRPA or python - all C++ or CPython, none of which reads either variable. So
# inside OML today these exports are a no-op, and they are here for two reasons
# only: the FHI-aims signatures live in a skill that ships a run_aims.sh recipe
# for a human to run, and an aims stage added later inherits the right setting
# instead of the wrong default. Do not read their presence as evidence that OML
# runs a Fortran producer.
#
# ABACUS needs none of this. It is C++, its CSC writer formats into an
# std::ofstream and flushes once per matrix block (`single_r_io.cpp` has no
# per-value std::endl), and std::ofstream is buffered by default: strace counts
# 2 write syscalls for 2e5 formatted values. Both directions of "fixing" it are
# slower: pubsetbuf(nullptr, 0) - explicitly unbuffered - took 29.9 s against
# 6.7 s, and a 1 MiB pubsetbuf buffer took 7.3 s against 6.7 s, so replacing the
# default buffer is a pessimisation. There is no C++ equivalent to set here.
FORTRAN_BUFFERED_ENVIRONMENT = {
    "FORT_BUFFERED": "TRUE",
    "GFORTRAN_UNBUFFERED_ALL": "0",
}


def render_fortran_environment(
    environment: Mapping[str, str] | None = None,
) -> str:
    """Return the ``export`` lines a Fortran producer stage needs.

    Added underneath a profile's own environment so a profile may still override
    a value deliberately; the defaults here are the measured ones.
    """
    merged = dict(FORTRAN_BUFFERED_ENVIRONMENT)
    if environment:
        merged.update(environment)
    return "".join(f"export {key}={shlex.quote(str(value))}\n" for key, value in merged.items())



def stage_job_name(run_id: str, stage: str) -> str:
    if stage not in CONTROLLED_PERIODIC_STAGES:
        raise ValueError(f"unsupported controlled stage: {stage}")
    return f"oml-{run_id}-{stage}"


def _walltime(resources: Mapping[str, object]) -> str:
    """Return the ``#SBATCH --time`` line, or nothing when no limit is set.

    Production GW stages on a shared debug partition have no useful upper bound:
    the runtime of a 512-q LibRPA stage is set by the physics, and a guessed
    walltime only converts "still running" into "died at 96%". A profile that
    omits ``walltime_minutes`` (or sets it to 0) asks Slurm for no limit.
    """
    minutes = resources.get("walltime_minutes")
    if minutes is None or int(minutes) <= 0:
        return ""
    hours, minute = divmod(int(minutes), 60)
    return f"#SBATCH --time={hours:02d}:{minute:02d}:00\n"


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
        "python3_exec": runtime.get("pyatb_python", runtime["python"]),
        "mpirun_exec": runtime["mpi_launcher"],
        "abacus_work": runtime["abacus"],
        "librpa_work": runtime["librpa"],
        "mpi_ranks": runtime["mpi_ranks"],
        "libri_mpi_ranks": runtime["mpi_ranks"],
        "pyatb_mpi_ranks": runtime["pyatb_mpi_ranks"],
        "omp_threads": runtime["omp_threads"],
    }
    return "".join(f"export {key}={shlex.quote(str(value))}\n" for key, value in values.items())


def stage_body(stage: str) -> str:
    """Return the shell body that performs one controlled stage.

    Public wrapper so login-node execution can reuse the exact same commands
    the scheduled path runs; keeping one body avoids the two paths drifting.
    """
    return _stage_body(stage)


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
    _fortran_env = render_fortran_environment().rstrip("\n")
    return f"""#!/usr/bin/env bash
#SBATCH --partition={resources['partition']}
#SBATCH --nodes={resources['nodes']}
#SBATCH --ntasks-per-node={resources['ntasks_per_node']}
#SBATCH --cpus-per-task={resources['cpus_per_task']}
#SBATCH --mem={resources['memory_mb']}M
{_walltime(resources)}#SBATCH --job-name={job_name}

set -euo pipefail
run_dir="$(pwd -P)"
cd "$run_dir"
source ".oml/env.sh"
export OMP_NUM_THREADS="$OML_OMP_THREADS"
{_fortran_env}
export PYTHONDONTWRITEBYTECODE=1
: "${{OML_ATTEMPT_ID:?missing controlled attempt identity}}"
mkdir -p ".oml/stage-results"
printf 'RUNNING:%s\n' "$OML_ATTEMPT_ID" > ".oml/stage-results/{stage}.status"
trap 'status=$?; if [[ $status -eq 0 ]]; then printf "COMMAND_COMPLETED:%s\\n" "$OML_ATTEMPT_ID"; else printf "COMMAND_FAILED:%s:%s\\n" "$status" "$OML_ATTEMPT_ID"; fi > ".oml/stage-results/{stage}.status"' EXIT

{_stage_body(stage)}"""
