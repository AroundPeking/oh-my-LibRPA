---
name: abacus-delta-st-solid-convergence
description: Use when preparing, submitting, auditing, comparing, or documenting periodic insulating-solid ABACUS Delta-Sternheimer plus LibRPA calculations, including actual-grid Ecut, GreenX frequency, auxiliary PCA, full-Coulomb metric, k/q mesh, analytic head/wing, FD8 atomic references, SOS comparators, cohesive energies, and conservative first-point screening of new materials.
---

# ABACUS Solid Delta-ST Convergence

Use this workflow for periodic insulating solids and their isolated atomic references. Keep solver completion, numerical convergence, and agreement with literature as separate conclusions.

Before submitting work, also apply:

- `research-hpc-orchestrator` for duplicate prevention, resource choice, provenance, and collection;
- `abacus-delta-st-efficient-production` for the measured 24-hour runtime gate and MPI/OpenMP layout;
- `abacus-librpa-version-guard` for the accepted producer/LibRPA contract;
- `ghj-aitp-tex-research-note` for project CSV, plots, TeX, PDF, and rendered-page checks;
- `abacus-delta-st-molecular-convergence` when an atomic box, spin, or occupation needs independent diagnosis.

Read [references/protocol.md](references/protocol.md) before writing inputs or Slurm files.

## Fixed Physical Contract

- Run no production physics locally.
- Require a positive insulating PBE gap. Stop before Delta-ST when the actual occupied/unoccupied spectrum is metallic, inverted, or fractionally occupied.
- Use explicit FD8 for every formal periodic-solid and isolated-atom response. Keep historical FD2 curves diagnostic and never mix them with FD8 convergence curves.
- Use a 20 Angstrom cubic Gamma-only box for isolated atomic references unless existing evidence proves that a larger box is required. Do not schedule routine 24 Angstrom atom-box checks.
- Treat the Si atomic reference as box-sensitive: run an independent fixed-spacing, fixed-grid-phase FD8 box scan before freezing 20 Angstrom. During this scan hold the frequency file, PCA threshold, occupations, and both atom `rmesh_times` settings fixed.
- Require integer atomic occupations in the final `eig_occ.txt`, with the intended spin-resolved electron counts. For isolated atoms set both `exx_ccp_rmesh_times=1` and `rpa_ccp_rmesh_times=1`; this atom-only convention must not be transferred to periodic solids.
- On server 66, request at most 10 nodes per job. Do not copy another server's node-count limits to server 66.
- Keep analytic q-average head/wing enabled for every formal solid point:
  `replace_w_head=true`, `option_dielect_func=3`, `rpa_headwing_mode=qavg`, `rpa_headwing_body_start=1`.
- The head/wing code must consume the actual Delta-ST `(ifreq, omega)` metadata. Never pair a separately generated SOS frequency grid by array index.
- Use full Coulomb, include q=0, and use `sqrt_coulomb_threshold=1e-5` unless a controlled test changes it.
- Do not apply the periodic q-average correction to an isolated Gamma-only atom.
- Define positive cohesive energy per atom before running:
  \[
  E_{\rm coh}=\frac{\sum_X n_X E_X-E_{\rm solid}}{N_{\rm atom}}.
  \]

## Choose One Lane

**Full convergence:** actual-grid Ecut, frequency, PCA, Coulomb metric, then k/q mesh. Change one parameter at a time. For the actual-grid gate, do not freeze a point from a near-identical adjacent grid: require an independent confirmation whose total `Ngrid` is at least 1.5 times the preceding candidate and whose absolute-energy change is still below 0.1 kcal/mol. Mark smaller-step plateaus `FALSE_PLATEAU_RISK`. Freeze the first endpoint that passes this robust grid gate and the corresponding per-atom energy gate.

**Conservative screening point:** use the safe endpoint in the protocol, label it `SCREENING_NOT_CONVERGED`, compare with matched SOS and literature, and expand convergence only when the discrepancy is scientifically important.

## Runtime Gate

Before a full canonical-q array, time one slow q on the finest planned grid with the exact production executable and inputs. Use the efficient-production skill's progress estimator. For a 24-hour queue, release the array only when the conservative projection is at most 18 hours. Fine grids should normally use nested frequency/k-point MPI (`NPROC = nfreq * kpoint_groups`) rather than one rank per frequency processing all k points serially.

## Acceptance

Accept a point only after scheduler `COMPLETED`, `ExitCode=0:0`, converged SCF occupations, positive gap, `status success`, `all_converged=yes`, complete response/partial/q-star/symmetry manifests, finite residuals, matching Coulomb and auxiliary provenance, Hermitian checks, and a successful finite LibRPA energy. Never equate `RUNNING`, an empty stderr, or a parser pass with a physical result.

Reuse completed producers for head/wing or SOS postprocessing. Never duplicate an existing job. Preserve every result and record binary hashes, inputs, jobs, wall time, actual grids, and final energy components.
