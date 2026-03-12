#!/usr/bin/env bash
set -euo pipefail

# Route template: molecule + GW + no NSCF + no pyatb + no shrink
# Fill these two paths before use.
abacus_work=<FILL_ABACUS_PATH>
librpa_work=<FILL_LIBRPA_PATH>

cp INPUT_scf INPUT
if [[ -f KPT_scf ]]; then
  cp KPT_scf KPT
fi

mpirun -np 1 "$abacus_work" >> abacus.srf.out

if [[ ! -f OUT.ABACUS/vxc_out.dat ]]; then
  echo 'Missing OUT.ABACUS/vxc_out.dat after SCF; stop before LibRPA.' >&2
  exit 1
fi
cp -a OUT.ABACUS/vxc_out.dat ./vxc_out

if ! ls coulomb_mat_*.txt >/dev/null 2>&1; then
  echo 'Missing coulomb_mat_*.txt after SCF; check exx_singularity_correction = massidda and stop before LibRPA.' >&2
  exit 1
fi

mpirun -np 1 "$librpa_work" >> librpa.srf.out
