#!/bin/bash
# SIAB Orbital Generation Script (complete workflow)
# Usage: Set variables below, then: sbatch run_siab.sh
#
# Required variables to set before submitting:
#   ELEMENT, Z, PSEUDO, PSEUDO_DIR, ECUT, RCUT, MAXL, BANDS, REF_BANDS
#   ORB_CONFIG (e.g., "3 3 2" for 3s3p2d)
#   BL_LIST (e.g., "2.0 2.1 2.5 3.0 3.5")
#   WORKDIR (output directory)
#   ORB_OUT (output .orb filename)

#SBATCH -p 48cp2
#SBATCH -N 1
#SBATCH --cpus-per-task=1
#SBATCH --ntasks-per-node=1
#SBATCH -J siab_gen
#SBATCH --mem=4000
#SBATCH --time=24:00:00

set -euo pipefail

# ===== CONFIGURATION =====
ELEMENT="${ELEMENT:-As}"
Z="${Z:-33}"
PSEUDO="${PSEUDO:-As_ONCV_PBE-1.0.upf}"
PSEUDO_DIR="${PSEUDO_DIR:-/data/home/df_iopcas_ghj/gw/GaAs_pp_research/case_13e_5e_k888}"
ECUT="${ECUT:-150}"
RCUT="${RCUT:-10}"
MAXL="${MAXL:-2}"
BANDS="${BANDS:-12}"
REF_BANDS="${REF_BANDS:-5}"
ORB_CONFIG="${ORB_CONFIG:-3 3 2}"  # nchi per L for final level
BL_LIST="${BL_LIST:-2.0 2.1 2.5 3.0 3.5}"
WORKDIR="${WORKDIR:-/data/home/df_iopcas_ghj/gw/GaAs_pp_research/siab_${ELEMENT}_${ECUT}Ry_${RCUT}au}"
ORB_OUT="${ORB_OUT:-${ELEMENT}_gga_${RCUT}au_${ECUT}Ry_${ORB_CONFIG// /s}.orb}"

# SA parameters
SA_SPILLAGE_TEMPS=50
SA_SPILLAGE_STEPS=600
SA_KINETIC_TEMPS=40
SA_KINETIC_STEPS=600

# Tools
ABACUS="/data/home/df_iopcas_ghj/app/abacus/builds/abacus-gw-symmetry-final-20260508-115644/build/abacus_3p"
SIA="/data/home/df_iopcas_ghj/app/abacus/builds/abacus-gw-symmetry-final-20260508-115644/tools/SIAB/SimulatedAnnealing/source/SIA_s.exe"
MPIRUN="/data/app/intel/oneapi-2024.2/mpi/2021.13/bin/mpirun"
PYTHON="/data/home/df_iopcas_ghj/app/miniconda3/bin/python3"

SKILL_DIR="${SKILL_DIR:-$HOME/.claude/skills/siab-generate-orbitals}"
CONVERT_SCRIPT="${SKILL_DIR}/convert_orbital.py"
PLOT_SCRIPT="${SKILL_DIR}/plot_orbital.py"

# Environment
module load oneapi/2024.2
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export MKL_DYNAMIC=FALSE
ulimit -s unlimited
export LD_LIBRARY_PATH="/data/home/df_iopcas_ghj/app/elpa-build/lib:/data/app/libxc/6.2.2-intel/lib:/data/app/intel/oneapi-2024.2/compiler/2024.2/lib:/data/app/intel/oneapi-2024.2/compiler/2024.2/opt/compiler/lib:/data/app/intel/oneapi-2024.2/mpi/2021.13/lib:/data/app/intel/oneapi-2024.2/mpi/2021.13/opt/mpi/libfabric/lib:/data/app/intel/oneapi-2024.2/mkl/2024.2/lib"

echo "============================================================"
echo "SIAB Orbital Generation"
echo "============================================================"
echo "Element:       ${ELEMENT} (Z=${Z})"
echo "Pseudo:        ${PSEUDO}"
echo "ECut:          ${ECUT} Ry"
echo "RCut:          ${RCUT} a.u."
echo "Lmax:          ${MAXL}"
echo "Orb config:    ${ORB_CONFIG}"
echo "Bond lengths:  ${BL_LIST}"
echo "Work dir:      ${WORKDIR}"
echo "Output:        ${ORB_OUT}"
echo "============================================================"

mkdir -p "${WORKDIR}"
cd "${WORKDIR}"

# ===== STEP 1: Generate STRU files =====
echo ""
echo "===== Step 1: Generate dimer STRU files ====="

cat > KPOINTS << 'KPTEOF'
K_POINTS
0
Gamma
1 1 1 0 0 0
KPTEOF

for BL in ${BL_LIST}; do
    SUFFIX="${ELEMENT}-${RCUT}-${BL}"
    cat > "${ELEMENT}-dimer-${BL}.stru" << STRUEOF
ATOMIC_SPECIES
${ELEMENT} 1 ${PSEUDO}
LATTICE_CONSTANT
20
LATTICE_VECTORS
1 0 0
0 1 0
0 0 1
ATOMIC_POSITIONS
Cartesian_angstrom
${ELEMENT}
0.0
2
0.0     0.0     0.0     0   0   0
0.0     0.0     ${BL}   0   0   0
STRUEOF
    echo "  Created: ${ELEMENT}-dimer-${BL}.stru"
done

# ===== STEP 2: ABACUS PW calculations =====
echo ""
echo "===== Step 2: ABACUS PW dimer calculations ====="

JLE_FILE=""
for BL in ${BL_LIST}; do
    SUFFIX="${ELEMENT}-${RCUT}-${BL}"
    OUTDIR="OUT.${SUFFIX}"
    echo ""
    echo "--- BL=${BL} ---"

    cat > INPUT << EOF
INPUT_PARAMETERS
suffix              ${SUFFIX}
stru_file           ${ELEMENT}-dimer-${BL}.stru
pseudo_dir          ${PSEUDO_DIR}
kpoint_file         KPOINTS
calculation         scf
ks_solver           dav
nspin               1
lmaxmax             ${MAXL}
bessel_nao_ecut     ${ECUT}
bessel_nao_tolerence 1e-12
bessel_nao_rcut     ${RCUT}
bessel_nao_smooth   1
bessel_nao_sigma    0.1
symmetry            0
nbands              ${BANDS}
ecutwfc             ${ECUT}
scf_thr             1e-5
scf_nmax            9000
smearing_method     gauss
smearing_sigma      0.01
mixing_type         pulay
mixing_beta         0.4
mixing_ndim         8
out_spillage        2
spillage_outdir     ${OUTDIR}
EOF

    ${MPIRUN} -np 1 ${ABACUS} 2>&1 | tail -3

    if [ -f "${OUTDIR}/orb_matrix.0.dat" ]; then
        echo "  SUCCESS: orb_matrix.0.dat"
        # Save first jle.orb for conversion
        if [ -z "${JLE_FILE}" ] && [ -f "${OUTDIR}/jle.orb" ]; then
            JLE_FILE="${OUTDIR}/jle.orb"
        fi
    else
        echo "  FAILED: orb_matrix.0.dat not found"
        exit 1
    fi
done

# ===== STEP 3: Collect orb_matrix paths =====
echo ""
echo "===== Step 3: Collect orb_matrix files ====="

ORB_FILES=""
NBL=0
for BL in ${BL_LIST}; do
    SUFFIX="${ELEMENT}-${RCUT}-${BL}"
    F="../OUT.${SUFFIX}/orb_matrix.0.dat"
    if [ -f "${F#../}" ]; then
        ORB_FILES="${ORB_FILES}${F}
"
        NBL=$((NBL+1))
    fi
done
echo "  Found ${NBL} orb_matrix files"

if [ -z "${JLE_FILE}" ]; then
    echo "ERROR: No jle.orb found"
    exit 1
fi
echo "  Using jle.orb: ${JLE_FILE}"

# ===== STEP 4: SA optimization =====
echo ""
echo "===== Step 4: SA optimization ====="

SA_WDIR="${WORKDIR}/sa_output"
rm -rf "${SA_WDIR}"
mkdir -p "${SA_WDIR}"
cd "${SA_WDIR}"

# Parse ORB_CONFIG
read -ra NZ <<< "${ORB_CONFIG}"
NZ_S=${NZ[0]:-1}
NZ_P=${NZ[1]:-1}
NZ_D=${NZ[2]:-1}
NZ_F=${NZ[3]:-0}
LMAX_P=${MAXL}  # lmax for P channel (max in DZ+)
if [ ${MAXL} -ge 1 ]; then LMAX_P=2; fi
if [ ${MAXL} -ge 2 ]; then LMAX_D=2; fi

SA_HEADER="<PW_QS>
1
0
1
${NBL}
${ORB_FILES}</PW_QS>

<PARALLEL>
1
1
</PARALLEL>

<BLOCK_NE>
100
</BLOCK_NE>

<SCHEME_VALUE>
2
</SCHEME_VALUE>

<METROPOLIS>
1.0e-3
0.8
${SA_SPILLAGE_TEMPS}
${SA_SPILLAGE_STEPS}
1.0e-1
0.8
${SA_KINETIC_TEMPS}
${SA_KINETIC_STEPS}
0.01
50
100
0.4
0.2
100
0.01
1
</METROPOLIS>

<BANDS>
1
1
${REF_BANDS}
</BANDS>"

SA_FOOTER='<PLOT>
0.01
-6
1
0.01
6.0
</PLOT>'

for LEVEL in 1 2 3; do
    echo ""
    echo "--- SA Level ${LEVEL} ---"

    cat > INPUT << EOF
${SA_HEADER}
<OPTIMIZE>
${LEVEL}
label / na / skip / lmax / each L /
EOF

    case ${LEVEL} in
        1)
            cat >> INPUT << EOL1
${Z} 2 new 1 ${NZ_S} ${NZ_P}
</OPTIMIZE>
EOL1
            ;;
        2)
            cat >> INPUT << EOL2
${Z} 2 new 1 ${NZ_S} ${NZ_P}
${Z} 2 new 2 ${NZ_S} ${NZ_P} ${NZ_D}
</OPTIMIZE>
EOL2
            ;;
        3)
            LMAX_D_VAL=2
            if [ "${NZ_F}" != "0" ]; then LMAX_D_VAL=3; fi
            cat >> INPUT << EOL3
${Z} 2 new 1 ${NZ_S} ${NZ_P}
${Z} 2 new 2 ${NZ_S} ${NZ_P} ${NZ_D}
${Z} 2 new 2 ${NZ_S} ${NZ_P} ${NZ_D}
</OPTIMIZE>
EOL3
            ;;
    esac

    cat >> INPUT << EOF
${SA_FOOTER}
EOF

    echo "  Running SIA..."
    ${SIA} 2>&1 | tail -10

    if [ -f "ORBITAL_RESULTS.txt" ]; then
        cp ORBITAL_RESULTS.txt "${WORKDIR}/ORBITAL_RESULTS_level${LEVEL}.txt"
        echo "  Level ${LEVEL} completed!"
    else
        echo "  ERROR: Level ${LEVEL} failed"
        exit 1
    fi
done

cd "${WORKDIR}"

# ===== STEP 5: Convert to .orb =====
echo ""
echo "===== Step 5: Convert to .orb format ====="

${PYTHON} "${CONVERT_SCRIPT}" \
    --results ORBITAL_RESULTS_level3.txt \
    --jle "${JLE_FILE}" \
    --ecut ${ECUT} --rcut ${RCUT} \
    --element "${ELEMENT}" --lmax ${MAXL} \
    --norb "${ORB_CONFIG}" \
    --output "${ORB_OUT}"

# ===== STEP 6: Plot =====
echo ""
echo "===== Step 6: Plot radial functions ====="

${PYTHON} "${PLOT_SCRIPT}" "${ORB_OUT}" -o "${ORB_OUT%.orb}.png"

echo ""
echo "============================================================"
echo "SIAB Orbital Generation COMPLETE"
echo "============================================================"
echo "Orbital file: ${WORKDIR}/${ORB_OUT}"
echo "Plot:         ${WORKDIR}/${ORB_OUT%.orb}.png"
