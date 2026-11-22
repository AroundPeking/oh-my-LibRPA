# BSE Route

Use this reference after `oh-my-librpa` has already classified the task as BSE
(GW plus Bethe-Salpeter excitons). Entry condition: the user asks for optical
spectra, exciton binding energies, exciton envelope or transition dipoles on
top of a LibRPA GW calculation.

**There are two independent BSE implementations behind ABACUS + LibRPA. Pick
the route before writing a single input line, because their files, their
stages and their success criteria do not overlap:**

| | route A: in-ABACUS `ESolver_BSE` | route B: standalone LibBSE |
| --- | --- | --- |
| how selected | ABACUS `esolver_type lr` + `xc_kernel bse` | a separate `LibBSE` executable reading `libbse.in` |
| stage 4 lives in | the same ABACUS binary | `LibBSE` from <https://github.com/HGAQ/LibBSE> |
| screening handed over as | `librpa.d/Wc_iR_*_ifreq_0.mtx` on disk | `librpa.d/Wc_Mu_*_ifreq_0.mtx` blocks, in memory |
| stage-3 task | `g0w0` — writes `GW_band_spin_*` whenever `band_kpath_info` is present | the same; `g0w0_band` is only an alias that forwards to it |
| multi-grid | `bse_use_fine_kgrid` on the ABACUS side | `bse_use_fine_kgrid` in `libbse.in`, plus an `energy_qp_fine` table |
| sections below | "Four stages" … "Exciton density plots" | "LibBSE route" onward |

Everything from "Four stages" to "Exciton density plots" describes **route A**.
If the user names LibBSE, works from `examples/07_abacus_librpa_libbse_interpolate_333_444`,
or asks for a dual-grid (`333 -> 444`, `777 -> 14 14 14`) interpolated spectrum,
jump to the **LibBSE route** section instead; route-A inputs will not run there.

Upstream recipe for route A: <https://fisherd99.github.io/abacus-librpa-bse-tutorial>
(companion to arXiv:2607.05853). The upstream example bundle
`example-k555-f666.tar.gz` is a silicon `5x5x5 -> 6x6x6` tutorial case and is
the only end-to-end validation of the four-stage chain.

## Hard capability boundary

The ABACUS BSE implementation reached through this route solves **only
zero-exciton-momentum states**. Before promising any momentum-resolved result,
check these two facts in the source you intend to run:

- the two-particle basis index is built as
  `ik * nocc * nvirt + i * nvirt + a` (`source/source_lcao/module_bse/hamilt_bse.cpp`),
  so the electron `a` and the hole `i` always carry the *same* k;
- the full input set for BSE contains no centre-of-mass momentum keyword. The
  only `bse_q_*` entries are `bse_q_approx_mode` and `bse_q_approx_threshold`,
  which control the auxiliary-basis q-to-k-pair mapping inside the kernel, not
  the exciton momentum.

Consequences to state plainly to the user:

- an exciton band structure along a Q path (`E_exc(Q)`), and therefore any
  claim about exciton dispersion, group velocity, or momentum-space spin
  texture of excitons, is **not** reachable with this code path;
- what is reachable is the Q = 0 spectrum at whatever k grid you solve, plus
  the spin channel structure (`singlet`, `triplet`, `rpa`, `ipa`) at Q = 0.

A second boundary applies to spin. `check_lr_parameters` admits `nspin` 1 and
2, but the grid-based Hartree kernel hardcodes
`const int is = 0; // NOTE: only support 1 spin now`
(`HamiltBSE<T>::cal_V_by_grid`). Do not claim a spin-resolved e(up)h(down)
exciton block on the strength of `nspin = 2` alone; validate the channel
actually emitted in `OUT.bse/trans_dipole_*` before interpreting it.

## Four stages

1. `scf` — ground state plus LibRPA producer files. Required: `rpa 1`,
   `rpa_out_vel 1`, `rpa_outdir OUT.librpa`, `out_mat_xc 1`,
   `exx_singularity_correction massidda`, `exx_pca_threshold 10`,
   `out_unshrinked_v 1`, `shrink_abfs_pca_thr 1e-6`, `shrink_lu_inv_thr 1e-3`.
   Afterwards copy `OUT.scf/vxc_out.dat` to `OUT.librpa/vxc_out.txt`.

   On `exx_pca_threshold 10`: what actually switches to the preset auxiliary
   basis is the STRU `ABFS_ORBITAL` block, which fills `files_abfs`
   (`source_cell/read_atom_species.cpp`), and `exx_lri.hpp` then *prepends* the
   file's functions to the PCA-constructed set. The threshold itself only
   controls how aggressively PCA truncates the constructed part. In practice
   `10` is used so that the constructed part contributes essentially nothing
   and the preset file dominates — but it is not, on its own, "read the preset
   file". A run with a preset `ABFS_ORBITAL` and a small threshold keeps both,
   with more functions than intended. Keep `10` and the preset file together.

   Why `out_unshrinked_v` and `shrink_abfs_pca_thr` travel together: with shrink
   on, `output_cut_coulomb_cs` writes only `Cs_shrinked_data_`, and the
   unshrunk `Cs_data_` that BSE reads comes from `out_large_Cs`
   (`rpa_lri_overlap.cpp`), which only runs when `shrink_abfs_pca_thr >= 0`.
   But the matching `coulomb_unshrinked_cut_*` is gated separately on
   `out_unshrinked_v`. Turn shrink on without `out_unshrinked_v` and BSE pairs
   large-basis `Cs` with small-basis `coulomb_cut_*`; the LibRI contraction
   asserts only tensor rank, not the contracted extent, so this is a bad memory
   read rather than a clean error. Turning shrink off entirely is also
   self-consistent (the in-tree regression `tests/08_RI/bse_lr_multik` does
   that) — mix the two and it breaks.
2. `nscf` — dense k grid for the exciton solve: `out_mat_xc 1`,
   `out_wfc_lcao 1`, `init_chg file`, `read_file_dir OUT.scf`. Run
   `preprocess_abacus_for_librpa_band.py -i OUT.nscf -o OUT.librpa` to write
   `band_kpath_info`, `band_KS_eigenvalue_k_*.txt`,
   `band_KS_eigenvector_k_*.txt`, `band_vxc_k_*.txt`.
   Skipping this stage is allowed only with `bse_use_fine_kgrid 0`. ABACUS's own
   description of the switch says modes **1 and 2** both require
   `band_kpath_info`, `band_KS_eigenvector_k_{index}.txt`, `KS_band_spin_{index}.txt`
   and `GW_band_spin_{index}.txt` (`source_io/module_parameter/read_inp_bse.cpp`);
   mode 1 is a uniform fine grid, mode 2 a non-uniform one.
3. LibRPA GW — must write the band tables and the static screened interaction in
   the auxiliary basis, because stage 4 reads both. `task = g0w0` does both; see
   the section below.
4. BSE — `esolver_type lr` together with `xc_kernel bse`.

## Stage 3 writes the band tables

BSE stage 4 reads, via `read_energy_qp_from_band_files`, per-k point band files
named `GW_band_spin_<n>.txt`, `KS_band_spin_<n>.txt` and the dense-grid
eigenvectors. **`task = g0w0` writes all of them** whenever
`band_kpath_info` is present in `input_dir`; `g0w0_band` is now only an alias
whose body is a deprecation warning plus a call to `task_g0w0()`. Unify on
`g0w0` — the OML-wide default applies here.

Verify this in the tree you will run, and check which source file is compiled
before grepping it. Some trees carry a stale `driver/task_gw.cpp` that defines a
different `task_g0w0` yet is absent from `CMakeLists.txt`; grepping that file
gives the opposite answer.

```bash
R=~/app/librpa/<tree>
grep -n 'tasks/g0w0'       $R/driver/CMakeLists.txt   # the compiled source
grep -c 'band_kpath_info'  $R/driver/tasks/g0w0.cpp   # expect >= 1
grep -c 'GW_band_spin'     $R/driver/tasks/g0w0.cpp   # expect >= 1
grep -n 'task_gw.cpp'      $R/driver/CMakeLists.txt   # empty = dead file
```

An end-to-end confirmation: a run that printed
`Loaded band k-path file OUT.librpa/band_kpath_info, starting band calculation`
under `task = g0w0` and produced the three `*_band_spin_1.dat` tables.

If `band_kpath_info` is absent, the driver prints
`Band k-path file ... is not found under ..., skip band calculation`, writes
`energy_qp` and returns. **A missing band table therefore means a missing
`band_kpath_info`, not the wrong task name** — which is the trap the older
version of this note fell into: it blamed the task name, so a project could
spend a rerun switching names while the real cause was an `input_dir` that
never received the preprocessed file.

## Stage-3/4 contract: the W(R) sidecar

Stage 4 does not recompute screening. `ESolver_BSE::lri_init` calls
`LR_IO::read_Ws`, which opens
`librpa.d/Wc_iR_<iR>_ifreq_0.mtx` and throws
`<name> not found!` when absent.

So stage 3 must enable the W(R) dump. Three separate things have to line up,
and each of them has bitten this route:

### 0. Route A parses TEXT, so it cannot share the route-B producer

`ESolver_BSE` reads `Cs_data_*` and `coulomb_unshrinked_cut_*` through
`LRI_CV_Tools::read_Cs_ao_all` and `LR_IO::read_coulomb_mat_k`
(`source_esolver/esolver_lr_lcao_bse.cpp`, `lri_init`), and both use `>>` on a
plain `ifstream`. reader-v1 writes **binary** `v1_*`, so pointing route A at a
reader-v1 directory aborts with

```text
Error in read_coulomb_mat_k: cannot find the atom for given auxiliary basis set range
```

Fix by producing a **separate** reader-v1-OFF SCF for route A
(`velocity_matrix` survives, since `out_velocity` is gated on `rpa_out_vel`
alone). The two routes therefore need two producer runs; do not try to serve
both from one `OUT.librpa`.

Two more layout facts specific to route A:

- the band tables must be named `KS_band_spin_1.txt` etc. (ABACUS appends
  `.txt`), while LibRPA writes `.dat`. Put the symlinks **inside**
  `OUT.librpa` — that is the directory ABACUS prefixes, not the run directory;
- `KPT` must be the **coarse** mesh. ABACUS derives its Born-von-Karman period
  from its own k list and then reads `Wc_iR_<iR>_ifreq_0.mtx` for
  `iR = 0 .. nk^3-1`. Feeding the dense `4x4x4` KPT therefore asks for 64 cells
  while LibRPA wrote only the `3x3x3` = 27, which aborts with
  `librpa.d/Wc_iR_27_ifreq_0.mtx not found`. The dense mesh still reaches the
  BSE through `band_kpath_info` + `bse_use_fine_kgrid 1`.

### 1. The switch exists, under the right name

| LibRPA vintage | option | note |
| --- | --- | --- |
| tutorial-era | `output_wc_rf = t` plus `ifreq_output_wc_end = 1` | `ifreq_output_wc_end 1` means "lowest frequency only", which is what BSE needs |
| later trees | `output_Wc_Rf_mat = 1` | `ifreq_output_wc_end` no longer exists; `1` already means "frequency 0 only", so the frequency window cannot be chosen |

Choose the spelling from the binary you will run, not from memory.

### 2. The writer emits the filename ABACUS reads

This is the trap that survives a successful switch. Two filename families exist
in LibRPA history:

- `Wc_iR_<iR>_ifreq_<ifreq>.mtx` — the whole W(R) block per R;
- `Wc_Mu_<Mu>_Nu_<Nu>_iR_<iR>_ifreq_<ifreq>.mtx` — per atom pair, emitted by
  the `output_wc_rf_atom_pair` branch.

ABACUS hardcodes `librpa.d/Wc_iR_<iR>_ifreq_0.mtx` with no glob and no
fallback (`LR_IO::read_Ws`, identical to upstream develop). Consequences:

- if the chosen LibRPA build only writes the `Wc_Mu_*` family, stage 4 cannot
  read it, whatever the switch says;
- the per-R family is the one to want, so leave `output_wc_rf_atom_pair`
  disabled when that option exists;
- **zero padding differs between vintages**: some builds write
  `Wc_iR_00000_ifreq_00000.mtx`, while ABACUS asks for `Wc_iR_0_ifreq_0.mtx`.
  Compare the actual filenames against the exact string ABACUS builds before
  launching stage 4; symlink or rename if they disagree.

### 3. The path is relative to the working directory

ABACUS opens the literal path `librpa.d/Wc_iR_...`, not a path assembled from
`rpa_outdir`. So the LibRPA `output_dir` must be `librpa.d` and stage 4 must run
in the directory that contains it. `rpa_outdir` is for the other stage-1/2/3
files; it does not redirect this one.

### Probe before trusting any build

```bash
B=~/app/librpa/<build>/chi0_main.exe
for k in output_wc_rf output_Wc_Rf_mat output_wc_rf_atom_pair \
         ifreq_output_wc_end band_kpath_info; do
  printf "%-28s %s\n" "$k" "$(grep -c "$k" "$B")"
done
```

A zero on `band_kpath_info` or on the three `output_wc_rf*` switches means the
build cannot run this route at all — the band tables and the screening sidecar
are the two things it must produce. Confirm the probe is meaningful by also
probing a key you know that build predates.

Then confirm the writer, not just the switch — in the source tree that built
that binary:

```bash
R=~/app/librpa/<tree>
grep -rn 'Wc_iR_\|Wc_Mu_' $R/src/          # epsilon.cpp is in src/ or src/core/
```

Both families appearing means the atom-pair branch is still selectable; only
`Wc_Mu_` appearing means this build cannot feed ABACUS BSE. That second case is
not hypothetical — it is the state of the current LibRPA development line, whose
`epsilon.cpp` emits only the per-atom-pair names. Treat "which side is ahead"
as something to measure, not to assume.

Also copy the GW results into the shared directory before stage 4:
`energy_qp -> OUT.librpa/energy_qp.txt`, `KS_band_spin_1.dat ->
OUT.librpa/KS_band_spin_1.txt`, `GW_band_spin_1.dat ->
OUT.librpa/GW_band_spin_1.txt`.

## Stage-4 inputs

| parameter | value | meaning |
| --- | --- | --- |
| `esolver_type` | `lr` | puts you in the linear-response branch; without it BSE is never reached |
| `xc_kernel` | `bse` | inside that branch, this alone selects `ESolver_BSE` over `ESolver_LR` |
| `rpa_outdir` | `OUT.librpa` | where stages 1-3 left their files |
| `read_file_dir` | `OUT.bse` | where `lr_solver spectrum`/`plot` and `bse_continue` read earlier eigenvector and matrix files from |
| `lr_solver` | `elpa` | full diagonalisation. `spectrum` and `plot` only read earlier results |
| `lr_nstates` | `-1` | solve all pairs |
| `nocc`, `nvirt` | e.g. `4`, `4` | valence/conduction bands entering the pairs |
| `bse_tda` | `tda` / `full` / `both` | `both` doubles the cost |
| `bse_spin_types` | `singlet` | also `triplet`, `rpa`, `ipa` |
| `bse_use_fine_kgrid` | `1` | use the dense grid from stage 2 |
| `bse_q_approx_mode` | `0` | exact q mapping (0 exact, 1 coarse, 2 mixed, 3 truncate) |
| `bse_ri_hartree` | `1` | LocalRI for the exchange kernel |
| `out_wfc_lr` | `1` | needed for later spectrum or density plotting |
| `bse_continue` | `0` | 1..4 resume from saved V_A/W_A/V_B/W_B; needs `out_bse_ab 1` |
| `bse_mem_save` | `0` | `1` folds V and W into the matrix, forces `bse_continue 0` |
| `abs_gauge` | `velocity` | `length` is only reliable for molecules centred in the cell (upstream guidance, not a code guard) |

`esolver_type lr` puts you in the linear-response branch; inside it,
`xc_kernel` alone decides which solver is built (`esolver_factory.cpp`): any
value other than `bse` gives `ESolver_LR` (LR-TDDFT), and `bse` gives
`ESolver_BSE`. So the pairing matters in one direction only — `xc_kernel bse`
without `esolver_type lr` never reaches this code, while `esolver_type lr` with
any other kernel silently runs LR-TDDFT instead of BSE.

`ESolver_BSE` is also compiled only when ABACUS was built with `ENABLE_LIBRI=ON`;
otherwise the factory aborts with "BSE requires ENABLE_LIBRI=ON". The LR branch
itself is inside a `__LCAO` guard, so a PW-only build never reaches it. Check the
build, not just the input.

Two spellings are involved and both are fine: input `esolver_type lr` is
normalized to the internal name `lr_lcao` (`esolver_factory.cpp`), which is what
the factory compares against.

Resume caveats worth knowing before relying on `bse_continue`:

- the saved matrices are `A_V_matrix_<rank>.dat` etc. in `read_file_dir`, using
  the **zero-based** MPI rank — unlike the LibRPA producer files mentioned
  above, which count from 1;
- they exist only if the earlier run had `out_bse_ab 1`;
- `bse_mem_save 1` silently resets `bse_continue` to 0 and forces
  `bse_ri_hartree 1`, so a memory-saving run cannot also be resumed.

## Reading the result

Judge success from artifacts, not from a grep for a friendly word:

- `OUT.bse/trans_dipole_<spin>_<tda|full>.dat` — transition dipoles
- `OUT.bse/trans_analysis_<spin>_<tda|full>.dat` — per-state table of the
  occupied/empty orbital pairs carrying each excitation, plus a k-resolved
  contribution summary
- `OUT.bse/Excitation_Energy_<label>.dat` — eigenvalues
- the BSE log prints `Excition binding energies (eV):` (the misspelling is in
  the source; do not "fix" it when grepping) and a total oscillator strength
  that should approach 1 under the f-sum rule for a complete solve.

## Exciton density plots

Set `lr_solver plot` and reuse the same `nocc`, `nvirt`, `bse_spin_types`,
`bse_use_fine_kgrid` as the BSE run that produced the eigenvectors, plus
`plot_istate`, `exciton_plot_type`, `exciton_plot_format`,
`exciton_slice_plane`, `exciton_slice_pos`, `exciton_slice_npoints`,
`exciton_slice_range`, and for conditional density `exciton_fixed_coordinate`
(6 numbers in Bohr, hole then electron). Conditional density supports only
`exciton_plot_format slice`.

Known wart to report rather than silently accept: the BvK header written into
the slice file comes from the sparse grid and must be corrected by hand for a
dense-grid run. The header key is `# bvk <nk_u> <nk_v>`, filled from
`kv.nmp[...]` in `make_slice_geometry`.

**Filenames differ by vintage — read the directory, do not assume.** Check
this before promising a specific file to a plotting script:

| build | slice file |
| --- | --- |
| tutorial-era (e.g. ABACUS v3.11.0-beta8, commit `45e51655f`) | `Exciton_{avg\|cond}_{elec\|hole}_slice_state<index>.dat`, state indexing from 0 |
| current develop (`exciton_plotter.cpp`) | `exc_{elec\|hole}_slice_st<n>.dat` and `exc_cond_{elec\|hole}_slice_st<n>.dat`, with `n` from 1; the cube form is `exc_{elec\|hole}_st<n>_s<spin>.cube` |

The tutorial bundle's `ref/` directory carries the first family, so a script
copied from it will not find files produced by a current build.

`plot_average_slice` asserts a single spin channel (`nspin_x == 1`), which is
the same limitation as the kernel-side spin note above.

Also: exciton density plotting handles the **TDA** eigenvectors only.

## Cost and parallel layout

Upstream Si `k555 -> f666`, 1 process x 48 threads: scf 16 min, nscf 4 s, GW
4 h 32 min, BSE 9 min. GW dominates; BSE is cheap at this size.

Two limits govern larger grids:

- keep the 2D block-cyclic local part of the BSE matrix below 2^31 - 1
  matrix elements, otherwise ScaLAPACK and ELPA break;
- more threads is not monotonically better — large thread counts were observed
  to abort with `std::bad_alloc` inside the Coulomb-vertex contraction even
  with ample free memory. Upstream reports `16 x 16` as the working shape for
  `k = 21x21x21` with `nocc = nvirt = 4`.

## Assets

The tutorial case is Si and its PP/NAO/ABFS triple is present in the bundled
library (`assets/abacus_abfs_nao_pp_gw/Si/sg15`). The enlarged auxiliary basis
`Si_3s3p2d1f1g_pca1e-6.abfs` is the one to use, because it lowers the LRI
error of the kernel.

Before starting a new material, check the ABFS presence explicitly. The preset
`.abfs` enters through the STRU `ABFS_ORBITAL` block, so a PP/NAO pair with no
matching `.abfs` cannot use this recipe: there is nothing to put in that block,
and with `exx_pca_threshold 10` the PCA-constructed remainder is truncated
toward zero. That is a hard stop, not a slow fallback — do not "fix" it by
lowering the threshold, because that silently changes the auxiliary basis the
whole GW+BSE chain was validated on.

## Reporting rules

- report the stage-4 numerical result only if stage 3 demonstrably wrote the
  screened-interaction sidecar the chosen route reads — `librpa.d/Wc_iR_*_ifreq_0.mtx`
  for route A, `librpa.d/Wc_Mu_*_ifreq_0.mtx` for LibBSE; otherwise BSE is
  reading stale or absent screening and the number is meaningless;
- state the exciton momentum explicitly (`Q = 0`) in every reported exciton
  energy or spectrum, since the code cannot produce anything else;
- do not present a Q = 0 spectrum as a check of an exciton-dispersion claim.

---

# LibBSE route (route B)

Standalone <https://github.com/HGAQ/LibBSE>. Its own reference case is
`examples/07_abacus_librpa_libbse_interpolate_333_444` (coarse `3x3x3` RI,
fine `4x4x4` BSE, `nocc = nvirt = 4`, matrix dimension 1024). Everything below
was verified on M9 on 2026-11-18 with a `7x7x7 -> 14x14x14` Si case
(dimension 43904); the run folder is `~/ghj_ml_gw/bse_si/si_case`.

## The four stages, as LibBSE actually needs them

`scf` -> `nscf` -> `LibRPA g0w0` -> `LibBSE`, all four driven by separate
executables. Stage 4 reads a *file* contract, not ABACUS input keywords.

**The Q = 0 boundary above applies to route B unchanged**, and for the same
reason: the transition space is built as `qp.nk * nocc * nvirt`
(`src/bse/bse_calculation.cpp`), i.e. one electron-hole pair per fine k point
with both carriers on the same k, and the only q-related keyword is
`bse_q_approx_mode`, which LibBSE *hard-requires* to be 0
(`this LibBSE path currently requires bse_q_approx_mode 0`). Do not claim a
finite-Q spectrum or exciton dispersion from a LibBSE run either.

1. **scf on the COARSE grid** — produces the RI coefficients, the Coulomb
   matrices, the velocity matrix and `stru_out`/`band_out` for the coarse mesh.
2. **nscf on the FINE grid** — `read_file_dir OUT.scf`, `init_chg file`,
   `out_wfc_lcao 1`, `out_mat_xc 1`. Then run
   `preprocess_abacus_for_librpa_band.py -i OUT.nscf -o OUT.librpa`, which
   writes `band_kpath_info`, `band_KS_eigenvalue_k_*`, `band_KS_eigenvector_k_*`
   and `band_vxc_k_*` into the *coarse* OUT.librpa directory. The two grids then
   coexist in one directory, which is exactly what `bse_use_fine_kgrid 1` wants.
3. **LibRPA `task = g0w0`** — this is where the route-B contract is easiest to
   get wrong; see the next section.
4. **`libbse.in` + the `LibBSE` executable.** `dimension = nk_fine * nocc * nvirt`.

## Stage-3 file-name contract (the biggest trap)

`LibRPA`'s driver was written against the **FHI-aims** naming (`Cs_data`,
`coulomb_mat`, `coulomb_cut`, `stru_out`, `band_out`) and exposes an
`input_preset = abacus` that only patches `fn_stru` / `fn_eigocc_scf` /
`fn_vxc_scf` to their `.txt` spellings. It does **not** rename the reader-v1
families. ABACUS in reader-v1 mode writes:

| what ABACUS writes | what the driver / LibBSE looks for by default |
| --- | --- |
| `v1_Cs_data_N.txt` | `Cs_data_N.txt` |
| `v1_Cs_shrinked_data_N.txt` | `Cs_shrinked_data_N.txt` |
| `v1_shrink_sinvS_N.txt` | `shrink_sinvS_N.txt` |
| `v1_coulomb_full_iq_N_rankR.dat` | `coulomb_mat` |
| `v1_coulomb_cut_iq_N_rankR.dat` | `coulomb_cut` |
| `stru_out.txt` / `band_out.txt` | `stru_out` / `band_out` (LibBSE side) |

The failures are not silent, but they come in sequence and each one costs a
queue wait:

- `read_shrink_sinvS: No shrink_sinvS files found with prefix shrink_sinvS_`
- `No Coulomb files found with prefix coulomb_mat`
- `LibRPA file reader 'coulomb_unshrinked_cut' failed: ... Naux=334 does not
  match basis_aux.nb_total=794`

Two independent fixes are needed, and they are not interchangeable:

**(a) For the LibRPA driver**, either symlink `v1_*` to the default names, or
spell every prefix out in `librpa.in`:

```text
prefix_lri_coeff         = v1_Cs_data_
prefix_lri_coeff_shrink  = v1_Cs_shrinked_data_
prefix_shrink_sinvS      = v1_shrink_sinvS_
prefix_coul_cut          = v1_coulomb_cut_iq_
prefix_coul_full         = v1_coulomb_full_iq_
```

All **five** are needed. `prefix_coul_cut` is the one most often forgotten, and
omitting it stops the run at `No Coulomb files found with prefix coulomb_cut`
because the driver reads two independent bare-Coulomb families. Prefer the
explicit prefixes; symlinks survive only as long as somebody recreates them
after every SCF re-run.

**(b) For LibBSE (stage 4)** prefixes cannot be configured — its
`FileReaderOptions` is filled from `src/interface/librpa_api.cpp` with hardcoded
LibRPA defaults. So `stru_out`, `band_out`, `Cs_data_N.txt`,
`Cs_shrinked_data_N.txt` and `coulomb_unshrinked_cut_*` must exist under
*those* names. Symlinks are the only mechanism; create them once at the end of
stage 1.

## `out_unshrinked_v` and the basis-size gate

LibBSE reads `basis_aux_out` (the **large** 794-function set) together with the
bare cut Coulomb, and validates `Coulomb v1 Naux == basis_aux.nb_total`. The
`v1_coulomb_cut_iq_*` family is written from the *RPA-level* cut Coulomb, which
is already shrunk to 334, so pointing LibBSE at it aborts with the Naux
mismatch above.

`out_unshrinked_v 1` additionally exports the large-basis cut Coulomb under the
plain legacy name `coulomb_unshrinked_cut_*` (text, 794), which is the one to
symlink. Consequences worth planning for:

- it is large: for a 2-atom Si cell with a 794-function auxiliary basis the
  `7x7x7` case produced 7.7 GiB (8.27 GB decimal) across 8 q-point files, but
  **only three of them (iq 1, 3, 7) carry real data, 2.57 GiB each** — the rest are near-empty
  because symmetry leaves them with no blocks on this rank. Size the quota by
  the populated q points, not by `nk_coarse`;
- it does **not** appear at all unless `out_unshrinked_v 1`, and the shrink
  basis files assume `shrink_abfs_pca_thr >= 0`, so the pair
  `out_unshrinked_v 1` + `shrink_abfs_pca_thr 1e-6` is mandatory;
- **reader-v1 is needed for the basis files, not for `velocity_matrix`.**
  Verified in `source_io/module_ctrl/ctrl_scf_lcao.cpp`: `out_velocity` is gated
  only on `inp.rpa_out_vel`. The basis writers (`out_librpa_basis_v1`) sit inside
  the `out_librpa_reader_version == 1` branches, so with reader-v1 off ABACUS
  emits `coulomb_cut_*` / `coulomb_mat_*` / `Cs_data_*` but **no**
  `basis_aux_out`. LibRPA's reader then falls back to
  `read_basis_from_Cs` (`driver/reader/reader_lri.cpp`), which recovers sizes
  only — enough for the reader, not enough to hand LibBSE a basis file it looks
  for by name.
  Upstream example 07 leaves reader-v1 off and gets away with it: it has
  `out_unshrinked_v 1`, `velocity_matrix` appears because `rpa_out_vel 1`, and
  the missing basis falls back to the Cs route. Turning reader-v1 **on**, as this
  recipe does, costs the `v1_` prefix work but gives real basis files; turning it
  off means reproducing upstream's fallback, and LibBSE must then be content with
  a basis reconstructed from `Cs_data_*` rather than read from `basis_aux_out`.

## Stage-3 `librpa.in` that actually worked

```text
task = g0w0
input_dir = OUT.librpa_band
input_preset = abacus
fn_vxc_scf = ../OUT.scf/vxc_out.dat      # .dat, not .txt, for ABACUS SCF output
output_dir = librpa_band.d
prefix_lri_coeff         = v1_Cs_data_
prefix_lri_coeff_shrink  = v1_Cs_shrinked_data_
prefix_shrink_sinvS      = v1_shrink_sinvS_
# LibRPA's own cut Coulomb is the SHRINK-basis family; do not point this at the
# large-basis coulomb_unshrinked_cut_* that LibBSE consumes.
prefix_coul_cut          = v1_coulomb_cut_iq_
prefix_coul_full         = v1_coulomb_full_iq_
i_state_low = 0
i_state_high = 8
nfreq = 16
tfgrids_type = minimax
parallel_routing = libri
option_dielect_func = 3
replace_w_head = t
use_scalapack_gw_wc = t
vq_threshold = 0
sqrt_coulomb_threshold = 0
use_shrink_abfs = t
use_shrink_chi = f
output_energy_qp = t
output_wc_rf = t
ifreq_output_wc_end = 1
```

Notes that cost time to rediscover:

- `fn_vxc_scf` must point at `OUT.scf/vxc_out.**dat**`; ABACUS writes `.dat`
  even though the reader-v1 family is `.txt`.
- `output_wc_rf t` + `ifreq_output_wc_end 1` is what emits
  `Wc_Mu_<Mu>_Nu_<Nu>_iR_<iR>_ifreq_0.mtx`. Without it LibBSE finds no
  screening.
- `input_dir = OUT.librpa_band` is the path-sampled directory from stage 2, and
  the run prints `Loaded band k-path file OUT.librpa_band/band_kpath_info,
  starting band calculation`. Without that file the driver says
  `Band k-path file ... is not found`, writes `energy_qp` and returns — no band
  table. The task name is never the cause; see "Stage 3 writes the band tables".
- keep `mpirun -np 1` for LibRPA and give it the cores as OpenMP threads; the
  compressed-Wc export is only validated single-rank.
- **all five `v1_` prefixes are needed.** Omitting `prefix_coul_cut` alone stops
  the run at `No Coulomb files found with prefix coulomb_cut`, because the
  driver reads two independent bare-Coulomb families and `input_preset = abacus`
  patches neither of them.

## QP-table conversion (`energy_qp_fine`)

`band_to_energy_qp.py` converts `GW_band_spin_1.dat` + `KS_band_spin_1.dat`
into the `energy_qp` block format. The upstream script hardcodes
`qp.shape == (64, 20)` and the `4x4x4` grid, so it cannot be reused on any other
mesh. When rewriting it (or if numpy is unavailable, which is the case on M9's
system python), keep all four gates:

1. KS and QP tables cover the same k points in the same order
   (`atol 1e-7` on the coordinates);
2. every k point lies exactly on one unshifted `NxNxN` grid (`atol 1e-6`) and
   appears exactly once, with `N` inferred from the data rather than assumed;
3. occupations are four filled and four empty at every k point — but the
   historical band writer stored them k-weighted (`2/nk`), so test for that and
   multiply back before validating;
4. the output is sorted by grid key, one `K_point` block per point, energies in
   Hartree.

The rewrite is checkable against the original: generate a synthetic `4x4x4`
table, run both scripts, `diff` the two outputs. Anything that is not
byte-identical is a behaviour change.

## Cost

`7x7x7 -> 14x14x14`, Si, `nocc = nvirt = 4`, dimension 43904, on M9:

| stage | resources | wall time |
| --- | --- | --- |
| scf + producer export | 8 ranks / 56 cores, 150 GB | 30 min (11 GB of OUT.librpa) |
| nscf `14x14x14` | 8 ranks, 120 GB | 26 s |
| `preprocess` on 2744 k points | 1 core | 21 s |
| LibRPA g0w0 (16 minimax x2 tau, 2744 band k points) | 1 rank x 32 threads, 120 GB | 1 h 55 min |
| `band_to_energy_qp` | 1 core | 2 s |
| LibBSE, whole run | 32 ranks, 600 GB | 3 h 28 min (8 ranks: >8 h, abandoned) |
| — of which Hartree A | | 1792 s |
| — of which screened A | | 8884 s |
| — of which ELPA `43904^2` | | 820 s |
| — of which velocity + spectrum | | 139 s |

The GW stage splits roughly evenly between the 32 time-grid self-energy
evaluations (~150 s each) and the fine-band self-energy (29 s of wall time for
2744 k points once W(R) is built).

Disk is the other constraint nobody budgets for. Two consumers dominate, and
they behave in opposite ways:

- the large-basis cut Coulomb looks like `nk_coarse` files but only the
  symmetry-allowed q points carry data — three real 2.57 GiB files out of eight
  for a 2-atom Si cell, 7.7 GiB in total;
- the TDA amplitude dump writes one file per excitation and dwarfs everything
  else: 59.3 GiB for 43904 states. Set `out_bse_eigenvectors 0` (it defaults to
  `true`, see `src/parameter/parameter.h`) unless the amplitude files are needed
  for a later `spectrum` restart or density plot.

**GiB and GB are not interchangeable here**: `du -h` and `ls -l` report
GiB while `sacct` memory and quota figures are decimal GB, so the same export
shows up as 7.7 GiB and 8.27 GB. Label every size with its unit and convert once
before feeding a quota calculation.

## Disk: the amplitude files are the whole bill

`out_bse_eigenvectors` defaults to `true` (`parameter/parameter.h`), and the
fine-grid amplitudes are enormous: Si `7x7x7 -> 14x14x14` with `nocc = nvirt = 4`
wrote 32 files of 1.9 GiB each, **59.2 GiB in total**, against 10.6 GiB for
`OUT.librpa` and 10.6 GiB for `librpa.d`. Set `out_bse_eigenvectors = false`
unless you actually need the amplitudes: the write is gated by
`if (options.out_bse_eigenvectors)` in `bse/bse_calculation.cpp`, and pairing it
with `bse_memory_optimized` still emits the energies and the spectrum
(`write_tda_block_cyclic_outputs`), so the optical result costs nothing.

## Plotting the spectrum: `spectrum_*.dat` is NOT eps2

Both the tutorial and this reference case produce
`spectrum_<spin>_<tda>.dat`, whose column 5 is a **broadened oscillator-strength
density in eV^-1**, not the imaginary part of the dielectric function.
`broaden_oscillator_spectrum` sums `f_i * gamma/(pi((E-E_i)^2+gamma^2))` with no
`1/N_k` and no `1/V`, so raw values run to 1e4 where the paper's Fig. 7 is ~40.
Two factors carry the whole difference:

```text
eps2(w) = 2 pi^2 / (N_k V) * sum_S (f_phys,S / Omega_S^Ha) * L(w - Omega_S)
f_phys  = f_file / 2
```

- `f_file/2`: the factor is a net of two effects, not one. `transition_dipole_slice`
  builds `d = i sqrt(2) sum vX/gap`, so `|d|^2 = 2|sum|^2`, and
  `calculate_oscillator_strengths` then uses `f = 2 Omega_Ry |d|^2` against a
  physical `2 Omega_Ha |d|^2` with `Omega_Ry = 2 Omega_Ha`. Pinned by two
  anchors: dividing once gives the paper's peak (38.4 vs ~39) and an f-sum of
  85%; dividing twice drops the peak to 19 and breaks both.
- `2 pi^2/(N_k V)`: neither `1/N_k` nor the cell volume `V` (Bohr^3) is applied.

Verified on Si `7x7x7 -> 14x14x14`: peak `eps2 = 38.4` at 4.09 eV against the
paper's `~39` at 4.1 eV, and the f-sum `∫w eps2 dw` recovers 85% of
`2 pi^2 N_e/V` (the shortfall is the truncated band window). The reference
`3x3x3 -> 4x4x4` case gives 143 at 3.10 eV — that is **not** an error, it is
coarse-grid concentration: 44.6% of the oscillator strength sits in one 3.0 eV
bin versus 6.3% on the dense mesh. Never judge correctness from the raw height.

## Exciton wavefunction: LibBSE cannot give a density

LibBSE's whole input surface has 26 keys and none of them is
`lr_solver`/`plot_istate`/`exciton_slice_*`; it writes no density and no slice.
What it does give is `Excitation_Amplitude_<spin>_<tda>_<rank>.dat` (one line per
state, complex X over the owned pairs) plus
`trans_kweight_<spin>_<tda>.dat` (`weight1(k) = sum_{vc}|X_kvc|^2`). Reassembling
all ranks reproduces `sum|X|^2 = 1` exactly and yields the per-k weights; on Si
state 0 that is 94% on Gamma, consistent with an indirect-gap semiconductor.

Getting an actual `|Psi(r_h, r_e)|^2` slice requires route A's `lr_solver plot`,
which reads the amplitudes route A itself wrote. Two caveats found on M9:

- route A's numerical result was **wrong** in the one configuration that ran
  (binding energy 4.29 eV against a 3.25 eV gap, lowest excitation -1.05 eV),
  while LibBSE on the same mesh and gap gave 0.1515 eV. The suspicion is the
  `read_Ws` convention `W = V + Wc`: if LibRPA's `Wc_iR_*` already contains the
  bare Coulomb, V is double counted. `Wc_iR_0_ifreq_0.mtx` is indeed nearly
  dense (630434 nonzeros out of 794^2), which supports that reading but does not
  prove it;
- the slice files it produced were all zeros.

The real cause turned out to be an **upstream defect, not the kernel**. Every
amplitude read and write sits inside an `assert`:

```cpp
// source_esolver/esolver_lr_lcao_bse.cpp -- 5 writes and 5 reads, all of them
213:  assert(nst == LR_Util::write_value(efile_out(label), prec, e, nst));
215:  assert(nst * dim == LR_Util::write_value(vfile_out(label), prec, v, nst, dim));
```

A Release build (`-O3 -DNDEBUG`) compiles the calls away entirely, so `X` stays
at its zero-initialised value and every slice comes out as `0.00000000e+00`.
Three checks pin it down: `nm -D` finds no `__assert_fail`; the plot log claims
`finish reading OUT.bse/Excitation_Energy_singlet.dat` for a file that does not
exist (`DONE(...)` sits outside the assert, so it still prints); and
`OUT.bse/Excitation_Amplitude_*` is never created. Both
`deepmodeling/abacus-develop:develop` and `Fisherd99/abacus-BSE:develop` carry
the identical lines, and their `exciton_plotter.cpp` files are byte-identical
(815 lines). Fix by moving the five writes and five reads out of `assert`, or
build with `-DCMAKE_BUILD_TYPE=Debug`.

The earlier suspicion — that ABACUS's `Ws = Vs + Wc` double counts the bare
Coulomb — is **refuted**. LibRPA's `epsilon.cpp` computes
`Wc = sqrtV (eps^-1 - I) sqrtV = W - V`, and LibBSE's legacy reader adds `V`
back with the same convention (`io/bse_files.cpp`), so `W = V + Wc` is correct.
What is still unexplained is route A's 4.29 eV binding energy against a 3.25 eV
gap; ruled out so far are the basis size (794 both times), `use_shrink_abfs`
(worse with `f`, -97 eV) and the `Wc` semantics above.

**Do not port the plotter into LibBSE.** It is not a self-contained module: the
header pulls in `LCAO_Orbitals` radial data, `UnitCell`, `K_Vectors`, `psi::Psi`
AO coefficients, `Grid_Driver`, `Parallel_Grid`, `PW_Basis`, `Parallel_2D`,
`DensityMatrix` and `ModuleGint::cal_gint_rho`, i.e. 336 source files across five
ABACUS subtrees, while LibBSE is 70 files with no `UnitCell` and no spherical
harmonics. The slice path alone is 679 of the plotter's 815 lines. Keep the
density in ABACUS and the spectrum and amplitudes in LibBSE; if a LibBSE-side
density is ever truly needed, scope it as a small standalone reader of
`band_KS_eigenvector_k_*.txt` plus the `.orb` radial tables, not as a port.

## Two working ways to get an exciton density

Both are implemented and cross-checked; keep both.

**Way 1 — ABACUS `lr_solver plot`, after the assert fix.** Apply
`patches/esolver_lr_lcao_bse.assert_io.patch` (move 5 writes and 5 reads out of
`assert`), rebuild only `abacus_std_para` (26 s with the object cache), then run
`lr_solver elpa` once to write the amplitudes and `lr_solver plot` once to read
them back. The two steps must share `read_file_dir`; `plot` on a directory with
no `Excitation_Energy_singlet.dat` now throws instead of silently reading zeros.
It writes `Exciton_avg_{hole,elec}_slice_state0.dat` **and** two `.cube` files —
**use the slice, not the cube**: the cube integrates to 0 and roughly half its
grid points are negative, so the effective density matrix is being fed to
`cal_gint_rho` in the wrong index order.

**Way 2 — rebuild from the amplitudes in ~400 lines of Python**
(`exciton_density_from_amplitudes.py`). Needs `wfk<ik>_nao.txt` (ABACUS NSCF),
`Excitation_Amplitude_singlet_<rank>.dat`, the `.orb` file and `stru_out`; it
links against neither code. It reproduces ABACUS's own slice with correlation
1.000000 for both when fed ABACUS amplitudes, then runs unchanged
on LibBSE amplitudes — which is why it is worth keeping even though ABACUS's
plotter now works.

Four conventions must be right or the density comes out negative or rotated:

| item | fact | how it was pinned |
|---|---|---|
| `.orb` radial | stores `R(r)`, **not** `r*R` | `int R^2 r^2 dr` = 1.01 for every shell; `int f^2 dr` ranges 0.23 to 4.47 |
| AO m ordering | `iw2_ylm = L*L + j`, j running straight through the block | `source_cell/atom_spec.cpp` |
| `wfk` k vectors | Cartesian in units of `2*pi/lat0`; convert before the Bloch phase | `k_d = k_c.(latvec/lat0)^T` lands on integer multiples of 1/nk |
| LibBSE ranks | amplitudes split contiguously over the global pair index | 8 ranks x 128 = 1024 and `sum|X|^2 = 1.000000` |

**ABACUS's amplitudes are NOT contiguous**: each rank holds
`[all nk][its 2 pairs]`, and recovering the pair index needs the `paraX_`
2D block-cyclic descriptor, which the file does not carry. To rebuild from
ABACUS amplitudes, run that BSE serially (`nloc_per_state = nk*nocc*nvirt`,
so the layout is plain `[k][v][c]`).

Cost: 64 k at 79x79 for both kinds is 4.7 min single-core; 2744 k the same size
is 33 min. Preview with `--kstride 4` or `--npoints 16` before committing.

## What an SCF mesh can and cannot sample

A Gamma-centred **odd** mesh contains none of the fcc special points:

```text
7^3   ->  only Gamma
8^3   ->  L, X, W, K all present
14^3  ->  L, X
```

This matters twice. First, a band-figure's "dots mark path points that sit on
the SCF mesh" layer shows one dot on a 7x7x7 run and nineteen on an 8x8x8 one;
that is the mesh, not a missing archive, and it should be stated rather than
silently left looking broken. Second, when a path is meant to sample the mesh
too, pick the segment count from the mesh: with 7x7x7, `15` points per segment
puts only Gamma on the grid while `14` puts seven points there.

## What each BSE output actually carries

The three deliverables of one GW+BSE run come from different files, and it is
easy to archive the wrong one:

```text
f_S  = 2 Omega_S |d_S|^2
d_S  = sum_ai k  <i k|v|a k> / (E_a - E_i) * X_aik
                 ^velocity matrix        ^amplitude
```

| file | what it can rebuild | what it cannot |
|---|---|---|
| `oscillator_strength_*.dat` (4.2 MiB for 43904 states) | the absorption spectrum, exactly | any wavefunction |
| `Excitation_Amplitude_*.dat` (1.09 MiB **per state**) | the exciton density, average or conditional | the spectrum, because the velocity matrix and the energy denominator are contracted away |
| `eps2_*.dat` (28 KiB) | the plotted spectrum | the spectrum at another broadening |
| `velocity_matrix` (105 MB here) | nothing by itself; it is already folded into the f table | — |

So the amplitude really is required to *produce* the oscillator strength — it is
the only wavefunction-level object — but once the f table is archived the
spectrum is reproducible without it. What the f table does **not** give is the
exciton shape, which is why a wavefunction deliverable needs the amplitudes of
the specific states being plotted.

Practical archiving rule for a case with tens of thousands of states: keep the
full f table (MiB), the eps2, and the amplitudes of only the states whose
density appears in a figure. For Si's 14x14x14 case one state is 1.09 MiB, so
the first ten cost 5.3 MiB compressed against 59 GiB for the lot.

## Coulomb cutoff: match the key to the ABACUS build

`rpa_cut_coulomb` does **not** exist on `master_ghj`. It is on upstream
`develop` only, and `git grep '"rpa_cut_coulomb"' <master_ghj>` returns nothing.
ABACUS quits on an unrecognised key
(`THE PARAMETER NAME 'x' IS INCORRECT!` -> `WARNING_QUIT`), so putting the line
into an input for a `master_ghj` build stops the run before SCF, not WARN.

Check the binary you will actually run, not the tutorial:

```bash
B=~/app/abacus/<build>/abacus
strings "$B" | grep -c 'rpa_cut_coulomb'    # 0 on master_ghj, >=1 on develop
strings "$B" | grep -E '^rpa_[a-z_]+$' | sort -u   # what this build accepts
```

On a `master_ghj` build the accepted RPA keys are `rpa_abfs_preorth`,
`rpa_abfs_preorth_threshold`, `rpa_ccp_rmesh_times`, `rpa_handoff`,
`rpa_outdir` and `rpa_out_vel`. The Si dual-grid run reported here used that
family of build and therefore set **no** `rpa_cut_coulomb` line at all, which is
why its `INPUT_scf` has none. Do not add one "for consistency": on that build it
is a hard stop.

Where the line does belong is the `develop`-based build, whose default is
`hard` and whose `log_erfc` option smooths the truncated Coulomb tail. That is a
different numerical series and has to be reported as such.

## Reading the official tutorial's exciton plots

`https://fisherd99.github.io/abacus-librpa-bse-tutorial` ships
`example-k555-f666.tar.gz` (1.6 MB) with four reference slices. Compare against
those before concluding anything is wrong, and note the settings they use:

```text
KPT_scf 5x5x5 / KPT_nscf 6x6x6        (216 fine k points)
exciton_slice_plane   ca
exciton_slice_pos     0.0
exciton_slice_npoints 200
exciton_slice_range   -4 4 -4 4       -> res = 200//8 = 25, so 201x201
exciton_fixed_coordinate 2.5 2.5 2.5 2.5 2.5 2.5
```

Two things make their pictures look different from a naive reproduction, and
neither is a bug: the **plane** (`ca` slices the c-a diagonal, not a-b) and the
**fine-mesh density** (216 k versus 64 or 2744). Their `INPUT_plot` configures
`conditional` only, yet `ref/` holds average slices too, so they ran it twice.

Their build also explains a trap: their `cmake` line sets no
`CMAKE_BUILD_TYPE`, so CMake leaves `NDEBUG` undefined, `assert` stays live, and
the amplitude IO actually executes. A Release build silently deletes it — see
the assert-IO section above.

**A useful kernel check**: reproduce their plot settings exactly and measure the
lattice-constant period of the hole-density spots along u. The tutorial gives
0.50 primitive cells. LibBSE on 3x3x3 -> 4x4x4 also gives 0.50, while a
mis-assembled route-A kernel gave 1.00 — the same defect that shows up as a
binding energy larger than the gap.

### The conditional density is periodic on the k-mesh supercell, not the cell

This is the sharpest physical difference between the two modes and it decides how
wide a plot has to be:

```text
average      rho(r+a) = rho(r)                  one primitive cell, because each k
                                                 contributes |.|^2 and |e^{ika}|^2 = 1
conditional  rho(r+T) = rho(r) only when e^{ik.T} = 1 for every k in the mesh,
             i.e. T is a superlattice vector of the k mesh
                                                 the supercell spanned by the mesh
```

Measured on Si by translating the reconstructed slice and correlating:

| case | k mesh | supercell | shift 1 cell | shift 1 supercell |
|---|---|---|---|---|
| 3x3x3 -> 4x4x4 | 4x4x4 | 4 cells | 0.04 / 0.35 | **1.00000000** |
| 7x7x7 -> 14x14x14 | 14x14x14 | 14 cells | 0.65 / 0.82 | **1.000000** |
| reference: average | — | 1 cell | **1.000000** | — |

So a conditional plot smaller than the supercell looks aperiodic, and one that
shows only part of a period is misleading. Size the window from the mesh: at
least two supercells, which means 16 cells for a 4x4x4 mesh and 28 for 14x14x14.

**Record the period explicitly.** A dual-grid header keeps `bvk` = the coarse
mesh, so reading `bvk` puts the pinned particle's periodic images at the wrong
spacing. `exciton_density_from_amplitudes.py` therefore writes a separate
`# kpoints nx ny nz` line with the count that actually entered the coherent sum,
and `plot_exciton_slice.py` prefers it. On the 14x14x14 Si case `bvk` says 7 but
`kpoints` says 14, and only the latter reproduces the measured supercell.
For Si that took 7 minutes and 75 minutes respectively on one core at res 12 and
res 4.

Do **not** try to parallelise this by slicing the window into strips: the
home-cell cache in `plot_cond_slice` is built per invocation, so N strips cost N
cache builds and the total work grows. Eight Python strips on an 8-core machine
measured slower than one process doing the whole window.

### `average` vs `conditional`: two different objects

`exciton_plot_type` selects between them, and they are not interchangeable:

| value | what it gives | k-sum |
|---|---|---|
| `average` | the marginal density, one particle integrated out | incoherent: `sum_k sum_c |sum_v X phi_v|^2` |
| `conditional` | one particle pinned, the other left free | coherent: `|sum_k sum_c [sum_v X conj(phi_v(r_h))] phi_c(r)|^2` |

Only the conditional density shows interference and therefore the actual shape
of the exciton; the average one shows where each particle sits on average.

Two traps when running `conditional` (both hit in practice):

- **The slice plane must pass through the pinned point, and the offset is a
  distance, not a fraction.** `exciton_slice_pos` / `--slice-pos` is the
  perpendicular offset in **Bohr**, so for an `ab` slice it must equal the pinned
  point's component along c, not its fractional coordinate. Si pinned at
  (2.5755, 2.5755, 2.5755) means fractional (0.25, 0.25, 0.25) and
  `0.25 * |c| = 1.8211` Bohr. Writing `0.25` puts the plane 0.83 A away.
  The difference is visible: through the pin the density there is a genuine
  **node** (~1e-17 against a 1e-7 peak, ten orders down), because the free
  particle must be orthogonal to the pinned one; off the pin the node is
  smeared into a small but nonzero value and the plot looks as if nothing is
  pinned at all.
- **The printed value is not a density.** `phi ~ 1/Bohr^1.5`, so
  `psi_cond ~ 1/Bohr^3` and `|sum_k psi_cond|^2 ~ 1/Bohr^6`. The file therefore
  reads ~1e-6 where the average density reads ~1e-2. Divide by `rho_hole(r_h)`
  for the conditional density itself.

Sanity check on Si: the electron density at the pinned hole is 4.3e-10 against a
global peak of 1.05e-6 (ratio 1/2500) and the peak sits 2.98 A from the hole,
which is the right order for a Si exciton radius.

All four densities now reproduce ABACUS point for point (correlation
1.000000; largest relative difference 2e-7 to 1e-6, which is floating-point
accumulation order, not physics). Getting there needed four separate fixes,
every one of them locatable to a line:

| # | bug | effect |
|---|---|---|
| 1 | `np.vdot(ref, C)` must be `np.vdot(C, ref)` — ABACUS's gauge is `inner_product(psi(ik), psi(0)) = <ik|0>` | average electron 0.992 -> 1.000 |
| 2 | the hole-side effective density matrix must be transposed: `cal_effective_dmk_hole` uses `gemm_cm(adjoint, normal, ...)`, giving `X^H X`, not `X X^H` | average hole 0.951 -> 1.000 |
| 3 | the conditional translation index is the absolute `floor(u_frac)`, not one relative to the window start | conditional electron 0.32 -> 1.000 |
| 4 | the hole side evaluates `conj(phi)` and negates the translation phase | conditional hole 0.48 -> 1.000 |

Fixes 3 and 4 touch only the conditional path, because only it performs a
coherent k-sum; the average densities are blind to both. That asymmetry is why
the average densities agreed early while the conditional one kept failing, and
it is a useful diagnostic: when only the conditional density is wrong, suspect
the translation index and the hole-side conjugation before the gauge.

### The dual grid: which mesh is dense, and what it does to the table

`KPT_nscf` carries the dense regular mesh (for Si, `14 14 14` = 2744 points), so:

- `task = g0w0` writes the `KS_/EXX_/GW_band_spin_1.dat` tables with one row
  per **dense mesh point**, not per path node;
- LibBSE's `energy_qp_fine` is produced from that same table by
  `band_to_energy_qp.py`, so the mesh-shaped table is exactly what BSE needs.

A mesh-shaped table is therefore normal for the BSE grid, and it is not a band
figure. Two things to keep apart:

| want | what to do |
|---|---|
| band tables for BSE | leave `KPT_nscf` as the dense mesh; `task = g0w0` writes the table |
| a conventional band figure | a second run with a real path in `KPT_nscf`, so `band_kpath_info` holds the path |

**Plotting from mesh-shaped tables.** Concatenating 2744 mesh points in file
order gives a sawtooth, because `kx` wraps back to zero every 14 points. Two
honest options:

1. Extract the points that genuinely lie on a straight line. For Si's
   Γ-centred mesh, L, Γ and X all sit on the grid, so L–Γ–X yields 15 + 15
   points (29 after deduplicating Γ) that are real computed k-points, not
   interpolated. The GW gap read off that subset matches the mesh-wide gap.
2. Keep the mesh as a scatter or density plot and label it as a mesh.

The official tutorial's `plot_compare.py` does neither — it concatenates its
216-point `6x6x6` mesh in file order and labels the axis "kpath". Do not copy
that; the axis is not a path.

### Getting all three deliverables from one campaign

A published GW+BSE case needs three figures, and they come from two runs:

| figure | what it needs | which run |
|---|---|---|
| GW band structure | QP energies sampled **continuously along a path** | a separate `g0w0` pass with `KPT` in `Line` mode |
| absorption spectrum | `oscillator_strength_*.dat` | the dense-mesh BSE |
| exciton wavefunction | `Excitation_Amplitude_*.dat` | the dense-mesh BSE |

A band structure cannot be salvaged from the mesh-shaped table the BSE run
produces: concatenating mesh rows in file order gives a sawtooth, and picking
out the mesh points that happen to lie on a line gives scattered samples, not a
dispersion. Both were tried on Si and both are wrong. The dense-mesh table is
correct for its actual job, which is `energy_qp_fine` for LibBSE.

The wavefunction figures are different: they are evaluated on a real-space
slice, so the k-mesh is exactly what is wanted there. Do not convert those to a
path.

#### Standing up the path pass

1. `KPT` in `Line` mode. ABACUS wants a node count per node, and the **last
   node must have count 1**:

   ```text
   K_POINTS
   5
   Line
   0.5 0.5 0.5 15
   0.0 0.0 0.0 15
   0.0 0.5 0.5 15
   0.25 0.75 0.5 15
   0.375 0.375 0.75 1
   ```

   Symmetry must be off (`symmetry -1`). Run nscf with its own suffix so the
   dense-grid outputs stay untouched.

2. `preprocess_abacus_for_librpa_band.py -i OUT.nscf_band -o OUT.librpa_band`
   writes `band_kpath_info` plus the per-k band files.

3. **Symlink the RI and screening data** from the dense run into
   `OUT.librpa_band`. Every missing file is a hard stop; the ones encountered
   on a real ABACUS case were `band_out.txt`, `stru_out.txt` (the copy that
   carries the legacy k sampling), `bz_sampling_out`, `basis_out`,
   `basis_wfc_out`, `basis_aux_out`, `basis_aux_shrink_out`,
   `KS_eigenvector_0.dat`, the `v1_coulomb_full_iq_*` family, and
   `velocity_matrix`. Both Coulomb families are read, and which one each term
   sees is set by three independent switches:
   `use_fullcoul_exx` (exchange), `use_fullcoul_eps` (the chi0 metric) and
   `use_fullcoul_wc` (the screened interaction).

4. `librpa.in` with `task = g0w0`, `input_dir = OUT.librpa_band`,
   `output_dir = librpa_band.d`.

**Cost and operations**: the screening is recomputed, so budget a normal G0W0
wall time. Three mistakes cost hours on the first attempt:

1. launching a second `mpirun` while the first was alive (they share the node
   and neither finishes),
2. backgrounding with `nohup ... &` or even `setsid nohup ... & disown` on a
   login session — both were reaped within an hour or two. **Submit long runs
   with `sbatch`**; a batch job is not tied to the login session.
3. leaving BLAS threading on. 32 ranks each spawning BLAS threads prints
   `OpenBLAS Warning: Detect OpenMP Loop and this application may hang` and the
   job stalls. Export `OMP_NUM_THREADS=1` and `OPENBLAS_NUM_THREADS=1`. The
   dense-grid G0W0 avoids this only because it ran one rank with many threads.

Progress markers to watch: `chi0s for time point` appears `nfreq` times, then
`Computing Wc(q)` once per irreducible q point, then `Done converting Wc q -> R`.

The stage after `q_gamma` prints no progress for hundreds of lines, so judge
liveness from `/proc/<pid>/stat` utime deltas rather than from the log.

### The recipe: plotting an exciton wavefunction end to end

Two working routes. Use the first when ABACUS produced the amplitudes, the second
when LibBSE did; both feed the same tool.

**Route 1 — ABACUS `lr_solver plot` produces the slice itself.**

```text
# INPUT (calculation nscf, esolver_type lr, xc_kernel bse)
lr_solver                plot
plot_istate              0
exciton_plot_type        average        # or conditional
exciton_plot_format      slice          # conditional requires slice
exciton_slice_plane      ca             # ab | bc | ca
exciton_slice_pos        0.0            # perpendicular offset, Bohr
exciton_slice_npoints    200            # res = npoints//span, output is (span*res+1)^2
exciton_slice_range      -4 4 -4 4      # u_start u_end v_start v_end, in primitive cells
exciton_fixed_coordinate 2.5 2.5 2.5 2.5 2.5 2.5   # hole xyz then electron xyz, Bohr
```

Run `lr_solver elpa` first in the same directory: `plot` needs `OUT.bse` to already
hold the amplitudes. Build with assertions live, or patch the assert-wrapped IO.

**Route 2 — rebuild from amplitudes with this skill's script.**

```bash
python3 scripts/exciton_density_from_amplitudes.py \
  --workdir   RUNDIR            # holds wfk*/  (or --nscf-dir) and stru_out
  --amplitudes DIR              # Excitation_Amplitude_singlet_*.dat
  --orb       Basis.orb
  --state 0
  --kind both                   # both | hole | elec | cond-elec | cond-hole
  --fixed-point X Y Z           # required for cond-*; the pinned particle, Bohr
  --plane ca --slice-pos 0.0
  --npoints 200 --range -4 4 -4 4
  --bvk 7 7 7                   # metadata only, copied into the header
  --out OUTPREFIX
```

`--kind both` gives the two average densities; `--kind cond-elec` pins the hole and
leaves the electron free, `cond-hole` the reverse. Pass `--gauge none` only when the
wavefunctions already carry ABACUS's `first_k` gauge elsewhere.

Then plot with `scripts/plot_exciton_slice.py DAT... --labels A B --out FIG.png`,
which understands the `# ABACUS_EXCITON_SLICE 1` header both routes write.

**Cost**: 64 k points at 79x79 takes 30 s for average and 4.3 min for conditional;
2744 k takes ~2.7 h per density. Run the two kinds as separate processes.

The tools travel with this skill and are ready to run:

| file | purpose |
|---|---|
| `scripts/exciton_density_from_amplitudes.py` | rebuild a density slice from BSE amplitudes |
| `scripts/plot_exciton_slice.py` | plot one or two slices side by side |
| `scripts/spectrum_to_eps2.py` | convert `spectrum_*.dat` to eps2 (see the section above) |
| `scripts/esolver_lr_lcao_bse.assert_io.patch` | the assert-IO fix for ABACUS route A |

Minimal invocations:

```bash
# way 2: rebuild from amplitudes (works with LibBSE amplitudes directly)
python3 scripts/exciton_density_from_amplitudes.py \
    --workdir <case> --nscf-dir OUT.nscf --amplitudes <libbse.d> \
    --orb Si_gga_8au_100Ry_3s3p2d.orb --state 0 --kind both \
    --plane ab --slice-pos 0.25 --npoints 80 --range -1 2 -1 2 --out out/exc

# compare the result against ABACUS
python3 scripts/plot_exciton_slice.py out/exc_hole_slice_state0.dat \
    <abacus>/Exciton_avg_hole_slice_state0.dat \
    --labels reconstruction ABACUS --out hole.png
```

**Budget the BSE kernel in `k_fine^2`-units, not `k_fine`.** LibBSE's
`bse_ri_batch_blocks` (default 64) sets how many k-pair blocks each rank holds,
so the collective batch count printed at the start of each kernel contraction,

```text
RI streaming: Hartree max 64 k-pair blocks/rank, <rounds> collective batches
```

is a direct proxy for the work: it scales as `nk_fine^2 / (64 * ranks)` and each
batch rebuilds the MO vertex on the fly. Going from the reference `4x4x4` to
`14x14x14` multiplies the batch count by ~900 at equal rank count — measured
`22` batches for `333 -> 444` at 8 ranks versus `20108` for `14x14x14` at 8
ranks (`4113` once raised to 32 ranks). That is why a reference case that
finishes in 22 s becomes hours. Check the printed number before committing a
large grid, and raise ranks (not batch size) to cut it.

## ELPA must be built with OpenMP, or LibBSE dies after the expensive part

LibBSE's `make_elpa_handle` unconditionally calls
`elpa_set(handle, "omp_threads", omp_get_max_threads(), &status)`. A
non-OpenMP ELPA rejects that key with `status -3`, and the check throws:

```text
LibBSE error on task N: ELPA failure in setting OpenMP threads: status -3
```

The trap is that ELPA's `configure.ac` accepts OpenMP only when the enable
value is literally `yes`:

```m4
[ if test x"$enableval" = x"yes"; then enable_openmp=yes; else enable_openmp=no; fi ]
```

so `--enable-openmp=1` silently builds **without** OpenMP. Two prefixes end up
needing to coexist: ABACUS and the LibRPA driver never set `omp_threads` (grep
`omp_threads` in LibRPA's `src/mpi/base_blacs.h` returns nothing), so they run
fine against the plain build, while LibBSE needs the OpenMP one. Select with
`LD_LIBRARY_PATH` per stage rather than trying to build a single ELPA for both.
Verified consequence:
a `14x14x14` run spent eight hours on the kernel and would then have aborted at
the diagonalisation. Configure with plain `--enable-openmp`, install to a
separate prefix (the library is `libelpa_openmp.so`, not `libelpa.so`), and build
a second LibBSE against it. Do not `make distclean` in a shared thirdparty ELPA
tree — extract a fresh copy from the source tarball instead.

## OpenMP inside the kernel is weak; rank count is the lever

Measured on the `14x14x14` run: with 8 ranks x `OMP_NUM_THREADS=3` on 80
allocated cores, each rank accumulated only `CPU/wall ≈ 1.12`, i.e. about one
core busy per rank regardless of the thread setting. The same case re-run as
32 ranks x `OMP_NUM_THREADS=1` reached `CPU/wall = 31/32`, i.e. full occupancy. LibRI's
`cal_cvc_mo_k_onthefly` does carry `#pragma omp parallel for collapse(3)` over
`q x I x J`, but per collective batch the block it hands that loop is small
(64 k-pair blocks), so the parallel region is dominated by serial setup and the
MPI exchange. Allocating 3 threads per rank therefore wastes roughly two thirds
of the cores; put the cores into ranks instead.

The two kernel contractions behave differently in wall time even when their
batch counts are close. The finished 32-rank run settles the ratio:

| contraction | batches | wall | s per batch |
| --- | --- | --- | --- |
| `Hartree A` | 4113 | 1792 s | 0.436 |
| `screened A` | 3921 | 8884 s | 2.266 |
| `ELPA` diagonalise `43904^2` | - | 820 s | - |
| fine-grid velocity + spectrum | - | 139 s | - |

**`screened` costs about 5x more per batch than `Hartree`**, not 2x: it has to
read the `.mtx` blocks and run the W(R) transform instead of the bare Coulomb
vertex. Budget route B with the screened numbers.

Memory is dominated by a per-rank copy of the Wc/Vs/Cs dataset: LibBSE
replicates it on every rank because `distribute_lri` is off for the
`librpa_wc` input format. `sacct` peak gives 333 GB for 32 ranks and 139 GB for 8 ranks,
i.e. **10.4 GB per rank at 32 ranks but 17.4 GB per rank at 8 ranks** — the
matrix is split across ranks, so per-rank memory falls as the rank count rises
while the total rises with it. Request `--mem` as `ranks x 18 GB` (the measured
8-rank figure, the conservative bound) and check the node limit before choosing
a rank count. A 32-rank job at `--mem=240 GB` was OOM-killed at 234 GB in
32 minutes; the same shape at 600 GB finished.

One more cost to plan for: after both TDA blocks are assembled, ELPA must
diagonalise the full `dimension x dimension` matrix. At `dimension = 43904`
that is 28.7 GB per complex matrix, and ELPA needs two to three of them.

## Reading the LibBSE result

- `libbse.d/oscillator_strength_singlet_tda.dat` — `state energy_eV f_x f_y f_z f_isotropic`
- `libbse.d/spectrum_singlet_tda.dat` — Lorentzian-broadened `energy_eV S_x S_y S_z S_isotropic`

**The spectrum is not normalised by the k-point count.** `broaden_oscillator_spectrum`
(`src/bse/spectrum.cpp`) sums `f_i * gamma / (pi * ((E-E_i)^2 + gamma^2))` over
every state of every fine k point, so the absolute height of `S` grows with
`nk_fine`. Comparing `S` between two meshes directly is wrong: measured Si
`3x3x3 -> 4x4x4` (64 k points) versus `7x7x7 -> 14x14x14` (2744) differ by ~12x
in peak height while `int S dE / nk` is 16.5 versus 12.6. Compare peak positions
and line shape, or divide both by `nk` first.
- `libbse.d/trans_dipole_*`, `trans_analysis_*`, `trans_kweight_*`
- the log prints `<spin_type> TDA binding energy (eV)` and, for the full solve,
  `<spin_type> full-BSE binding energy (eV)`. Grep the string rather than a line
  number — the prints sit in `src/bse/bse_calculation.cpp` and move between
  revisions. The value is `direct_gap - lowest_excitation`; verify it closes
  against the printed gaps and the first row of `oscillator_strength_*.dat`
  before quoting it.

LibBSE does **not** print `Excition binding energies (eV):` — that string
belongs to ABACUS's `ESolver_BSE` (route A). Grepping for it here will always
come up empty.
