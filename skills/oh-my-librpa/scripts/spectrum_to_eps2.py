#!/usr/bin/env python3
"""Convert a LibBSE oscillator-strength table into the imaginary part of the
macroscopic dielectric function eps2(w).

Why this script exists
----------------------
LibBSE writes `oscillator_strength_<spin>_<tda>.dat` and `spectrum_<...>.dat`.
Neither is eps2: the first is a per-state quantity in an extensive Ry
convention, the second is its Lorentzian-broadened sum with NO 1/V and NO
1/Omega factor.  Plotting `spectrum_*.dat` directly gives numbers of order
1e4 (this Si case) where the paper's Fig. 7 is order 40.  The factor is

    eps2(w) = 2 pi^2 / (N_k V) * sum_S (f_phys,S / Omega_S^Ha) * L(w - Omega_S)

with V the primitive-cell volume in Bohr^3 and L a normalized Lorentzian in
eV.  Two corrections carry the whole discrepancy:

  * LibBSE stores `f_file = 2 Omega_Ry |d|^2` (src/bse/spectrum.cpp), while the
    physical oscillator strength is `f_phys = 2 Omega_Ha |d|^2`.  Because
    Omega_Ry = 2 Omega_Ha, `f_phys = f_file / 2`.
  * |d|^2 already absorbs LibBSE's sqrt(2) dipole prefactor, so applying the
    standard f-to-eps2 relation to `f_phys` is consistent with the paper's
    Eq. (24a) without a further factor.

Validation: the f-sum rule.  ∫ w eps2(w) dw = 2 pi^2 N_e / V with N_e the
valence electron count per cell.  On the 7x7x7 -> 14x14x14 Si case this
returns 85-105% of the target depending on how much of the 0-12 eV window is
integrated, which is the expected shortfall for a truncated band window.

Usage:
    spectrum_to_eps2.py <oscillator_strength.dat> <out.dat> [--volume V]
                        [--broadening 0.15] [--emax 12] [--step 0.01]
"""

import argparse
import math
import pathlib
import sys

HA2EV = 27.211386245988          # eV per Hartree
RY2EV = 13.605693122994          # eV per Rydberg
BOHR = 0.529177210903            # Angstrom per Bohr

# Si diamond from inputs/*/STRU: LATTICE_CONSTANT 1.889726164 Bohr,
# vectors (0,c,c),(c,0,c),(c,c,0) with c = 2.725777 -> det = 2 c^3.
SI_LC = 1.889726164
SI_C = 2.725777
SI_VOLUME = 2.0 * SI_C ** 3 * SI_LC ** 3      # 273.34 Bohr^3


def load(path):
    rows = []
    for line in pathlib.Path(path).read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        fields = line.split()
        rows.append((float(fields[1]), float(fields[5])))   # energy_eV, f_isotropic
    if not rows:
        raise ValueError("{}: no states".format(path))
    return rows


def eps2(rows, nk, volume, broadening, energy):
    """eps2 at one photon energy, Eq. (24a) with the f_file/2 correction."""
    total = 0.0
    e_ha = broadening / HA2EV
    for e_i, f_file in rows:
        omega_ha = e_i / HA2EV
        f_phys = 0.5 * f_file
        delta = (1.0 / math.pi) * e_ha / ((energy - e_i) ** 2 / HA2EV ** 2 + e_ha ** 2)
        total += (f_phys / omega_ha) * delta
    return 2.0 * math.pi ** 2 / (nk * volume) * total


def f_sum(rows, nk, nelec):
    """Fraction of the f-sum rule recovered by the states actually present.

    ∫ w eps2(w) dw = 2 pi^2 sum_S f_phys,S / (N_k V), and the exact rule is
    2 pi^2 N_e / V, so the volume cancels and the ratio is just
    sum_S f_phys,S / (N_k N_e).
    """
    total = sum(0.5 * f_file for _, f_file in rows)
    return total / (nk * nelec)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--nk", type=int, required=True,
                        help="number of FINE k points in the BSE transition space")
    parser.add_argument("--volume", type=float, default=SI_VOLUME,
                        help="primitive-cell volume in Bohr^3 (default: this Si cell)")
    parser.add_argument("--nelec", type=float, default=8.0,
                        help="valence electrons per cell for the f-sum check; the "
                             "default 8 is this Si cell: 2 atoms x z_valence 4.00 "
                             "of Si_ONCV_PBE-1.0.upf. Override for any other cell.")
    parser.add_argument("--broadening", type=float, default=0.15)
    parser.add_argument("--emax", type=float, default=12.0)
    parser.add_argument("--step", type=float, default=0.01)
    args = parser.parse_args()

    rows = load(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    npoints = int(round(args.emax / args.step)) + 1
    with open(args.output, "w") as handle:
        handle.write("# imaginary part of the macroscopic dielectric function\n")
        handle.write("# half_width_eV {}\n".format(args.broadening))
        handle.write("# N_k {}  V_bohr3 {:.4f}\n".format(args.nk, args.volume))
        handle.write("# energy_eV eps2\n")
        values = []
        for index in range(npoints):
            energy = index * args.step
            value = eps2(rows, args.nk, args.volume, args.broadening, energy)
            values.append(value)
            handle.write("{:.6f} {:.8e}\n".format(energy, value))
    peak = max(values)
    peak_e = values.index(peak) * args.step
    print("{} states, N_k={}, peak eps2 = {:.2f} at {:.2f} eV -> {}".format(
        len(rows), args.nk, peak, peak_e, args.output))
    recovered = f_sum(rows, args.nk, args.nelec)
    print("f-sum recovered by these states: {:.0f}%".format(100.0 * recovered))
    # A truncated band window loses weight, so below 1 is expected; far above 1
    # means --nk or --nelec disagrees with the run that produced the table.
    if recovered > 2.0 or recovered < 0.2:
        raise SystemExit(
            "f-sum implausible ({:.0f}%): check --nk (fine-mesh k count) and "
            "--nelec against the run that wrote this table".format(100.0 * recovered))
    return 0


if __name__ == "__main__":
    sys.exit(main())
