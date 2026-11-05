# BSE Route

Use this reference after `oh-my-librpa` has already classified the task as BSE
(GW plus Bethe-Salpeter excitons). Entry condition: the user asks for optical
spectra, exciton binding energies, exciton envelope or transition dipoles on
top of a LibRPA GW calculation.

Upstream recipe: <https://fisherd99.github.io/abacus-librpa-bse-tutorial>
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
   Skipping this stage is allowed only with `bse_use_fine_kgrid 0`.
3. LibRPA GW — must run the **band channel** and must write the static screened
   interaction in the auxiliary basis, because stage 4 reads both. See the
   section below: with current LibRPA the channel is selected by the task name,
   and the OML-wide `task = g0w0` default does not produce it.
4. BSE — `esolver_type lr` together with `xc_kernel bse`.

## Stage 3 must be the band channel, not plain g0w0

This conflicts with the OML-wide rule that new inputs use `task = g0w0`, so it
needs the explicit reason here.

BSE stage 4 reads, via `read_energy_qp_from_band_files`, per-k point band files
named `GW_band_spin_<n>.txt`, `KS_band_spin_<n>.txt` and the dense-grid
eigenvectors. In LibRPA those files are written by one function only:
`task_g0w0_band` (`driver/task_gw_band.cpp` emits `GW_band_spin_<n>.dat`). The
plain `task_g0w0` path (`driver/task_gw.cpp`) writes `energy_qp` and the gap
print but never `GW_band_spin_*`, and it does not read `band_kpath_info`.

Verify this in the tree you will run rather than trusting either the tutorial
or this note:

```bash
R=~/app/librpa/<tree>
grep -rn '"GW_band_spin_' $R/driver/    # expect exactly one hit: task_gw_band.cpp
grep -rn 'task_lower == "g0w0_band"' $R/driver/   # the task-string dispatch
```

Quote the patterns and match the full dispatch expression. Looser forms mislead:
an unquoted `GW_band_spin` also matches `"QSGW_band_spin_"` in
`task_qsgw_band.cpp`, bare `"g0w0_band"` matches four `Profiler::start/stop`
labels, and `g0w0_band` unquoted additionally matches the function name
`task_g0w0_band`.

The dispatch lives in `driver/task.cpp` in some trees (`{"g0w0_band",
task_t::G0W0_band}`) and in `driver/main.cpp` in others
(`task_lower == "g0w0_band"`); try both forms, and a tree matching neither
cannot offer this route.

So for this route the LibRPA input keeps the band task name. Treat the
OML-wide `g0w0` preference as inapplicable here and say so in the run log,
rather than silently writing a task name that will leave stage 4 without its
GW band files.

## Stage-3/4 contract: the W(R) sidecar

Stage 4 does not recompute screening. `ESolver_BSE::lri_init` calls
`LR_IO::read_Ws`, which opens
`librpa.d/Wc_iR_<iR>_ifreq_0.mtx` and throws
`<name> not found!` when absent.

So stage 3 must enable the W(R) dump. Three separate things have to line up,
and each of them has bitten this route:

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
         ifreq_output_wc_end g0w0_band; do
  printf "%-28s %s\n" "$k" "$(grep -c "$k" "$B")"
done
```

A zero on `g0w0_band` means that build cannot run this route at all. Confirm
the probe is meaningful by also probing a key you know that build predates.

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

- report the stage-4 numerical result only if stage 3 demonstrably wrote
  `librpa.d/Wc_iR_*_ifreq_0.mtx`; otherwise BSE is reading stale or absent
  screening and the number is meaningless;
- state the exciton momentum explicitly (`Q = 0`) in every reported exciton
  energy or spectrum, since the code cannot produce anything else;
- do not present a Q = 0 spectrum as a check of an exciton-dispersion claim.
