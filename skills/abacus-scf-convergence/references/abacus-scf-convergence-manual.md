# ABACUS SCF Convergence Manual Reference

This reference is distilled from `~/Downloads/ABACUS收敛性问题解决手册.md` by Zhou Weiqing, AISI, last updated 2025-02-21. It applies to ABACUS v3.5.0 and later unless a version gate is stated below.

Load this file when a task needs parameter defaults, version gates, or detailed convergence options beyond the main `SKILL.md`.

## Parameter Defaults And Use

| Parameter | Default | Use | Notes |
|---|---:|---|---|
| `mixing_type` | `broyden` | charge-density mixing method | Options include `broyden`, `pulay`, `plain`. Do not change without a specific reason. |
| `mixing_ndim` | `8` | number of saved densities in DIIS history | Larger values can improve convergence but increase memory roughly linearly. |
| `mixing_beta` | `0.8` for `nspin=1`; `0.4` for `nspin=2/4` | charge-density mixing coefficient | Larger is faster but less stable; smaller is slower but safer. |
| `mixing_gg0` | `1.0` | Kerker preprocessing strength for charge density | Useful for metals. For atoms, molecules, and sometimes insulators, set `0.0` if Kerker hurts convergence. |
| `mixing_gg0_min` | `0.1` | lower bound in Kerker preprocessing | Usually leave unchanged. |
| `mixing_beta_mag` | `4*mixing_beta`, capped at `1.6` | magnetic-density mixing coefficient for `nspin=2/4` | Same stability tradeoff as `mixing_beta`; often reduce along with charge mixing. |
| `mixing_gg0_mag` | `0.0` | Kerker preprocessing for magnetic density | Usually keep off; physical meaning is less clear. |
| `mixing_angle` | `0.0` | angle mixing for noncollinear `nspin=4` | Use when DIIS has noncollinear magnetic convergence problems or converges to a wrong magnetic state. |
| `mixing_tau` | `false` | kinetic-energy density mixing for metaGGA | Turning it on often helps metaGGA convergence and cases where `EDIFF` lags behind `DRHO`. |
| `mixing_dmr` | `false` | density-matrix mixing for DFT+U/EXX/DeePKS | Requires `mixing_restart`; supported from ABACUS v3.6.0. |
| `mixing_restart` | `0` | clear mixing history after `drho < mixing_restart` | Often try `1e-3`, but this can make convergence worse if the restart point is poorly chosen. Supported from ABACUS v3.6.0. |
| `smearing_method` | `gaussian` | occupation smearing method | `gaussian` is general; `fixed` for insulators; `mp` for metals. |
| `smearing_sigma` | `0.015 Ry` | smearing width | Larger values can stabilize SCF but may produce the wrong ground state. |
| `scf_nmax` | `100` | maximum SCF iterations | Increase only when `drho` is still decreasing. |
| `scf_thr` | `1e-6` | density convergence threshold | For hard cases slightly above `1e-6`, a modest relaxation may be acceptable for intermediate steps. |
| `scf_ene_thr` | `1` | energy-difference threshold | With default `1`, this criterion is effectively off. If set, both `scf_ene_thr` and `scf_thr` must pass. |
| `scf_stop_os` | `0` | early stop after long density oscillation | Saves machine time when `drho` oscillates for more than `scf_stop_ndim` steps; it does not solve convergence. |

## Scenario Playbook

### Nonmagnetic `nspin=1`

Start with these changes, in order:

1. Reduce `mixing_beta`.
2. Increase `smearing_sigma`.
3. Increase `mixing_ndim`.

Then branch by system:

- Atom or molecule: set `mixing_gg0 0.0`.
- Semiconductor or insulator: Kerker is usually safe, but `mixing_gg0 0.0` can be tested.
- Metal: tune `mixing_gg0` and `mixing_gg0_min`.
- metaGGA: set `mixing_tau true`.
- Bad initial geometry: use loose relax steps first, then tighten `scf_thr`.

### Collinear Magnetic `nspin=2`

Start with these changes, in order:

1. Reduce `mixing_beta` and reduce `mixing_beta_mag` proportionally.
2. Increase `smearing_sigma`.
3. Increase `mixing_ndim`.

For atom/molecule magnetic failures, use:

```text
mixing_beta      0.4
mixing_beta_mag  0.4
mixing_gg0       0.0
mixing_gg0_mag   0.0
```

For magnetic metals, use:

```text
mixing_beta       0.2
mixing_gg0        1.0
mixing_beta_mag   0.8
mixing_gg0_mag    0.0
```

If this still fails, reduce `mixing_beta` and `mixing_beta_mag` further.

For metaGGA with magnetic systems, also set:

```text
mixing_tau true
```

### DFT+U

Escalate in levels:

Level I:

```text
mixing_beta  0.2
```

Level II:

```text
mixing_beta     0.2
mixing_restart  1e-3
mixing_dmr      1
```

Interpret `mixing_restart` failures carefully:

- If the run was slow but convergent before, and becomes non-convergent after adding `mixing_restart`, the restart point may be based on a bad density. Try a smaller value such as `1e-4`.
- If the run still fails after adding `mixing_restart`, the restart may be too late. Use the `drho` curve to restart earlier.

Level III:

```text
mixing_beta     0.2
mixing_restart  5e-4
mixing_dmr      1
uramping        1.0
```

Version gates:

- `mixing_restart` and `mixing_dmr`: ABACUS v3.6.0+.
- `uramping`: ABACUS v3.6.1+.

### EXX And DeePKS

Because these also depend on density-matrix-like quantities, consider the DFT+U Level I and Level II logic when ordinary density mixing fails. Verify version support and output behavior in the actual ABACUS build.

### Noncollinear `nspin=4`

If traditional DIIS uses `mixing_angle 0.0`, use the collinear magnetic strategy first. If it remains difficult or reaches the wrong magnetic state, set:

```text
mixing_angle     1.0
mixing_beta      0.2
mixing_beta_mag  1.0
```

### Relax

For difficult magnetic relaxations, use multiple relax stages. Each stage can reuse the magnetic moments from the previous SCF, which often improves both convergence and magnetic-state stability.

## Practical Cautions

- `mixing_restart` is not a harmless convergence knob; choose it from the actual `drho` curve.
- `smearing_sigma` should not be increased without checking the final occupation and physical state.
- `scf_stop_os` saves time when oscillation is clear, but it only stops early; it is not a convergence solution.
- `scf_thr` relaxation can be useful for intermediate geometry cleanup, but a downstream producer should still meet the target convergence standard.
- `NUPDOWN` can help only when the desired total spin is known.
- Explicit initial magnetic moments in `STRU` are still preferred even when ABACUS can auto-assign moments from v3.5.0 onward.
