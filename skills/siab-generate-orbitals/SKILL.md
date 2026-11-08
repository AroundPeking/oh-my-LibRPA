---
name: siab-generate-orbitals
description: Use when generating or regenerating ABACUS numerical atomic orbitals (.orb) with the SIAB workflow (ABACUS PW dimer calculations, Simulated Annealing optimization, .orb conversion), especially when changing rcut or ecut for existing pseudopotentials on the df server.
---

# SIAB Generate Orbitals

Generate ABACUS numerical atomic orbitals (.orb) using SIAB workflow:
ABACUS PW dimer calculations → SA (Simulated Annealing) optimization → .orb conversion.

## When to Use

When user asks to generate or regenerate numerical orbitals for ABACUS LCAO calculations,
especially when changing cutoff radius (rcut) or energy cutoff (ecut) for existing
pseudopotentials.

## Prerequisites (pre-configured on df server)

- ABACUS built with PW + spillage output support
- SIA_s.exe compiled and available
- oneAPI 2024.2 environment
- partition: 48cp2 (1 node, 1 core is sufficient for SA)

## Key Paths

```
ABACUS=/data/home/df_iopcas_ghj/app/abacus/builds/abacus-gw-symmetry-final-20260508-115644/build/abacus_3p
SIA=/data/home/df_iopcas_ghj/app/abacus/builds/abacus-gw-symmetry-final-20260508-115644/tools/SIAB/SimulatedAnnealing/source/SIA_s.exe
MPIRUN=/data/app/intel/oneapi-2024.2/mpi/2021.13/bin/mpirun
```

## Parameters

| Param | Description | Example |
|-------|-------------|---------|
| element | Element symbol | As, Ga |
| z | Atomic number | 33 (As), 31 (Ga) |
| pseudo | Path to .upf file | /path/to/As_ONCV_PBE-1.0.upf |
| ecut | Energy cutoff (Ry) for PW and Bessel | 150 |
| rcut | Radius cutoff (a.u.) for orbital | 10 |
| maxL | Max angular momentum | 2 |
| orbs | Channel counts per L (l=0,1,2,...) | "3 3 2" → 3s3p2d |
| bands | Number of bands for reference PW calc | 12 |
| ref_bands | Reference bands for spillage | 5 |
| bl_list | Bond lengths for As₂ dimer | "2.0 2.1 2.5 3.0 3.5" |
| sa_spillage_temps | SA spillage temperatures | 50 |
| sa_spillage_steps | SA spillage steps per temp | 600 |
| sa_kinetic_temps | SA kinetic temperatures | 40 |
| sa_kinetic_steps | SA kinetic steps per temp | 600 |
| outdir | Output directory | /data/home/df_iopcas_ghj/gw/GaAs_pp_research/siab_As_5e_150Ry_10au |

## Workflow

### Step 1: Create directory and STRU files

```bash
mkdir -p $WORKDIR && cd $WORKDIR
```

For each bond length BL, create dimer STRU:
```
ATOMIC_SPECIES
{ELEMENT} 1 {PSEUDO_FILENAME}
LATTICE_CONSTANT 20
LATTICE_VECTORS: 1 0 0 / 0 1 0 / 0 0 1
ATOMIC_POSITIONS: Cartesian_angstrom, 2 atoms at (0,0,0) and (0,0,BL)
```

KPOINTS: Gamma 1 1 1 0 0 0

### Step 2: ABACUS PW (per bond length)

INPUT template:
```
INPUT_PARAMETERS
suffix              {ELEMENT}-{RCUT}-{BL}
stru_file           {ELEMENT}-dimer-{BL}.stru
pseudo_dir          {PSEUDO_DIR}
kpoint_file         KPOINTS
calculation         scf
ks_solver           dav
nspin               1
lmaxmax             {MAXL}
bessel_nao_ecut     {ECUT}
bessel_nao_tolerence 1e-12
bessel_nao_rcut     {RCUT}
bessel_nao_smooth   1
bessel_nao_sigma    0.1
symmetry            0
nbands              {BANDS}
ecutwfc             {ECUT}
scf_thr             1e-5
scf_nmax            9000
smearing_method     gauss
smearing_sigma      0.01
mixing_type         pulay
mixing_beta         0.4
mixing_ndim         8
out_spillage        2
spillage_outdir     OUT.{ELEMENT}-{RCUT}-{BL}
```

Run: `$MPIRUN -np 1 $ABACUS`

Expected output: `OUT.{ELEMENT}-{RCUT}-{BL}/orb_matrix.0.dat` and `jle.orb`

**IMPORTANT NOTES from debugging:**
- Do NOT include `printe`, `basis_type`, `bessel_nao_rcut` with comment, or `wannier_card` in INPUT
- `out_spillage 2` and `spillage_outdir` must be in main INPUT directly (not in separate INPUTw file)
- Each BL takes ~2-7 minutes (longer BL = slower SCF convergence)

### Step 3: SA optimization (3 levels)

For each level, write SA INPUT:

```
<PW_QS>
1           # calculate spillage
0           # restart
1           # output
{NBL}       # number of structures
../OUT.{ELEMENT}-{RCUT}-{BL1}/orb_matrix.0.dat
../OUT.{ELEMENT}-{RCUT}-{BL2}/orb_matrix.0.dat
...         # one per line!
</PW_QS>

<PARALLEL> 1 1 </PARALLEL>
<BLOCK_NE> 100 </BLOCK_NE>
<SCHEME_VALUE> 2 </SCHEME_VALUE>

<METROPOLIS>
1.0e-3  0.8  {SA_SPILLAGE_TEMPS}  {SA_SPILLAGE_STEPS}
1.0e-1  0.8  {SA_KINETIC_TEMPS}   {SA_KINETIC_STEPS}
0.01  50  100  0.4  0.2  100  0.01  1
</METROPOLIS>

<BANDS> 1  1  {REF_BANDS} </BANDS>

<OPTIMIZE>
{LEVEL}
label / na / skip / lmax / each L /
{Z} 2 new {LMAX_L0} {NZ0}
{Z} 2 new {LMAX_L1} {NZ0} {NZ1}
... (one line per level, cumulative)
</OPTIMIZE>

<PLOT> 0.01  -6  1  0.01  6.0 </PLOT>
```

**CRITICAL:** The `label / na / skip / lmax / each L /` comment line MUST be present
between the nlevel number and the actual orbital configuration lines. SA reads this
as a dummy/useless string to skip.

**Orbital levels** (cumulative):
- Level 1 (SZ): 1s1p → `{Z} 2 new 1 1 1`
- Level 2 (DZP): 2s2p1d → `{Z} 2 new 1 1 1` + `{Z} 2 new 2 2 2 1`
- Level 3 (TZDP): 3s3p2d → above + `{Z} 2 new 2 3 3 2`

Where format is: `atomic_number na state lmax nz(L=0) nz(L=1) ... nz(L=lmax)`

**Timing:** Level 1 ~15 min, Level 2 ~15 min, Level 3 ~45 min (with default SA params)

Run: `$SIA` (serial, single-core)

Output: `ORBITAL_RESULTS.txt` containing C4 coefficients.

### Step 4: Convert ORBITAL_RESULTS to .orb

Use the conversion script at `~/.claude/skills/siab-generate-orbitals/convert_orbital.py`:

```bash
python3 convert_orbital.py \
  --results ORBITAL_RESULTS_level3.txt \
  --jle jle.orb \
  --ecut {ECUT} --rcut {RCUT} \
  --element {ELEMENT} --lmax {MAXL} \
  --norb "{NZ_S} {NZ_P} {NZ_D} ..." \
  --output {ELEMENT}_{PSEUDO}_{RCUT}au_{ECUT}Ry_{ORBS}.orb
```

The script:
1. Reads C4 coefficients from ORBITAL_RESULTS
2. Reads jl(q,r) basis functions from jle.orb 
3. Reconstructs r·φ(r) = Σ C4[ie] · jl(q[ie], r)
4. Writes in ABACUS .orb format (header + radial mesh data)

### Step 5: Plot for inspection

```bash
python3 plot_orbital.py --orb output.orb
```

Generates PNG showing r·φ(r) for each orbital channel.

## Complete Submit Script Template

Save as `run_siab.sh` in work directory and submit with `sbatch`:

```bash
#!/bin/bash
#SBATCH -p 48cp2
#SBATCH -N 1 --cpus-per-task=1 --ntasks-per-node=1
#SBATCH -J siab_{ELEMENT} --mem=4000

module load oneapi/2024.2
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MKL_DYNAMIC=FALSE
export LD_LIBRARY_PATH=...

# [Step 1-3 as described above]

python3 ~/.claude/skills/siab-generate-orbitals/convert_orbital.py ...
python3 ~/.claude/skills/siab-generate-orbitals/plot_orbital.py ...
```

## Debugging Notes

- ABACUS PW: if "THE PARAMETER NAME 'X' IS INCORRECT", remove X from INPUT
- SA: if "id=0" error, ensure `label / na / skip / lmax / each L /` comment line exists after nlevel
- SA: orb_matrix paths must be one per line (not space-separated on one line)
- SA: atomic number (Z) must be used as id, NOT type index (0-based)
- If ABACUS PW kills with signal 9, reduce OMP_NUM_THREADS to 1 and use mpirun -np 1
