---
name: abacus-scf-convergence
description: Use when diagnosing or stabilizing ABACUS SCF convergence failures, oscillating drho, scf_nmax exits, magnetic/noncollinear/DFT+U/metaGGA convergence problems, or ABACUS producer runs whose SCF quality and occupations must be verified before LibRPA RPA/GW use.
---

# ABACUS SCF Convergence

Use this skill to diagnose ABACUS SCF non-convergence without changing the physical target. The core rule is: read the real logs first, identify the intended charge/spin/occupation state, then change one convergence control at a time.

This skill distills the ABACUS convergence manual `~/Downloads/ABACUS收敛性问题解决手册.md` by Zhou Weiqing, for ABACUS v3.5.0 and later. For parameter defaults and the full scenario table, read `references/abacus-scf-convergence-manual.md`.

## Required Evidence First

Before changing inputs, inspect the actual run:

- `OUT.*/running_scf.log`
- `OUT.*/warning.log`
- stdout such as `abacus*.out` or scheduler output
- `eig_occ.txt`, `band_out`, Mulliken output, and final magnetic moments when available
- `INPUT`, `STRU`, `KPT`, pseudopotential/orbital choices, and ABACUS version

Record these facts:

- final `Electron density deviation` or `drho`, and whether `#SCF IS CONVERGED#` appears
- whether `drho` is monotonic, oscillating, or jumping after partial improvement
- `nspin`, `nupdown`, atom-level `mag`, total magnetism, and absolute magnetism
- final occupation pattern and whether it matches the intended integer state
- calculation class: nonmagnetic, collinear magnetic, noncollinear, metaGGA, DFT+U, EXX, DeePKS, relax, or ABACUS+LibRPA producer
- system class: atom/molecule, semiconductor/insulator, or metal

Do not diagnose from generic advice alone. If logs are unavailable, say that the diagnosis is provisional and ask for the missing files.

## Preserve The Physical Target

Decide the intended electron count and spin before tuning SCF.

- Do not remove spin polarization just to make SCF converge if that changes the reference state.
- For open-shell atoms, prefer explicit `nspin 2`, atom-level `mag`, and, when justified, `nupdown`.
- For closed-shell molecules such as equilibrium H2, `nspin 1` is normally the correct reference.
- For charged or localized spin states, explicitly check `nelec`, `nelec_delta`, `nupdown`, symmetry settings, and atom-level `mag`.
- A reasonable `nupdown` can stabilize magnetic SCF, but use it only when the target spin is known.
- ABACUS v3.5.0+ can assign nonzero atomic moments when all STRU moments are zero, but still prefer explicit initial magnetic moments for speed and correctness.

For downstream RPA/GW work, require both gates:

- `scf_ok`: ABACUS SCF converged cleanly.
- `integer_ok`: final occupations match the intended physical occupation.

For periodic systems with k-point weights, interpret integer occupations after accounting for spin and k/star weights. Do not mechanically require every printed occupation weight to be exactly 0, 1, or 2.

## Stabilization Sequence

Use this order unless the logs point to a more specific case:

1. Lower `mixing_beta`.
2. Increase `smearing_sigma`, keeping in mind that too-large smearing can converge to the wrong state.
3. Increase `mixing_ndim` if memory allows.
4. Apply the `nspin` and system-specific settings below.
5. Increase `scf_nmax` only when `drho` is still clearly decreasing.
6. Loosen `scf_thr` only for intermediate stabilization or difficult relax steps, not as proof that a producer is clean.

Keep a compact evidence table with input changes, final `drho`, convergence status, magnetic moment, and occupation status. Change one major variable at a time.

## Common Presets

### Nonmagnetic `nspin 1`

General order: reduce `mixing_beta`, increase `smearing_sigma`, then increase `mixing_ndim`.

- Atom or molecule: disable Kerker preprocessing with `mixing_gg0 0.0`.
- Semiconductor or insulator: Kerker is usually safe, but `mixing_gg0 0.0` can be tested if it appears harmful.
- Metal: tune `mixing_gg0` and `mixing_gg0_min`; do not blindly disable Kerker.
- metaGGA: set `mixing_tau true`, especially when energy convergence is slower than density convergence.
- Bad initial geometry: first run a few loose relax steps, then tighten `scf_thr`.

### Collinear Magnetic `nspin 2`

General order: reduce `mixing_beta` and `mixing_beta_mag` together, increase `smearing_sigma`, then increase `mixing_ndim`.

For isolated atoms or molecules with magnetic SCF failure, make charge and magnetic mixing identical and disable Kerker for both:

```text
mixing_beta      0.4
mixing_beta_mag  0.4
mixing_gg0       0.0
mixing_gg0_mag   0.0
```

For magnetic metals, start with:

```text
mixing_beta       0.2
mixing_gg0        1.0
mixing_beta_mag   0.8
mixing_gg0_mag    0.0
```

If still difficult, reduce `mixing_beta` and `mixing_beta_mag` further.

### DFT+U, EXX, Or DeePKS

For calculations where the Hamiltonian depends on a density matrix, escalate carefully:

1. Level I: ordinary DIIS with smaller mixing:

```text
mixing_beta  0.2
```

2. Level II: density-matrix mixing:

```text
mixing_beta     0.2
mixing_restart  1e-3
mixing_dmr      1
```

`mixing_restart` is useful but dangerous. If the run becomes worse, the restart point may be too early and based on a bad density; try a smaller value such as `1e-4`. If the run still fails after already running away, the restart may be too late; choose an earlier point based on the `drho` curve.

3. Level III: U-ramping:

```text
mixing_beta     0.2
mixing_restart  5e-4
mixing_dmr      1
uramping        1.0
```

Version gates: `mixing_restart` and `mixing_dmr` require ABACUS v3.6.0+; `uramping` requires ABACUS v3.6.1+.

### Noncollinear `nspin 4`

Start with the same logic as collinear magnetic calculations when `mixing_angle 0.0`. If it still fails or converges to the wrong magnetic state, use angle mixing:

```text
mixing_angle     1.0
mixing_beta      0.2
mixing_beta_mag  1.0
```

### Relax Calculations

For magnetic relaxations, split the job into several relax stages so each stage can reuse the previous SCF magnetic moments. This often stabilizes the next ionic step better than forcing one long run.

## ABACUS + LibRPA Producer Rules

For RPA/GW producer runs, do not move to LibRPA until the producer is clean. Smearing is acceptable for stabilization only if final occupations remain physically correct.

Report these values before trusting the result:

- `E_KohnSham`
- `E_xc`
- `rpa_lcao_exx(Ha)` when using RPA@PBE
- final `Electron density deviation`
- final occupation table
- LibRPA `Total EcRPA`

For RPA@PBE totals, keep units explicit:

```text
E_RPA@PBE = E_PBE - E_xc_PBE + E_EXX + E_c_RPA
```

ABACUS energy table values are often printed in Ry; convert to Ha by dividing by 2 before combining with `rpa_lcao_exx(Ha)` and `EcRPA(Ha)`.

## Output To The User

Answer in an evidence-first format:

- current state: running/converged/not converged, and exact supporting log values
- physical target: whether charge, spin, and occupation settings match the intended state
- smallest change attempted or recommended, with reason
- `scf_ok` and `integer_ok`
- remaining uncertainty and the next log/input needed

Avoid claiming that a setting “fixes” the case until a real rerun shows clean SCF and valid occupations.
