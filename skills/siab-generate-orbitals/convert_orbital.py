#!/usr/bin/env python3
"""Convert SIAB ORBITAL_RESULTS.txt to ABACUS .orb format.

Reads C4 coefficients from ORBITAL_RESULTS and spherical Bessel basis
functions from jle.orb, reconstructs radial orbitals.

Usage:
    python3 convert_orbital.py \\
        --results ORBITAL_RESULTS_level3.txt \\
        --jle OUT.As-10-2.0/jle.orb \\
        --ecut 150 --rcut 10 --element As --lmax 2 \\
        --norb "3 3 2" \\
        --output As_gga_10au_150Ry_3s3p2d.orb
"""

import argparse
import numpy as np
import sys


def parse_orbitals_block(lines, start_idx):
    """Parse the <Coefficient> block to extract C4 coefficients per orbital."""
    orbitals = []
    i = start_idx

    # Read total number of orbitals
    while i < len(lines):
        s = lines[i].strip()
        if 'Total number of radial orbitals' in s:
            n_orb = int(s.split()[0])
            i += 1
            break
        i += 1

    # Read each orbital
    orb_count = 0
    while orb_count < n_orb and i < len(lines):
        s = lines[i].strip()
        if s.startswith('Type'):
            # Format: Type L Zeta-Orbital
            parts = s.split()
            # Find Type, L, Zeta-Orbital positions
            try:
                type_idx = parts.index('Type')
                l_idx = parts.index('L')
                z_idx = parts.index('Zeta-Orbital')
            except ValueError:
                i += 1
                continue

            i += 1
            vals = lines[i].split()
            L = int(vals[l_idx])
            N = int(vals[z_idx])
            i += 1

            # Read C4 coefficients until next "Type" or block end
            coeffs = []
            while i < len(lines):
                s2 = lines[i].strip()
                if s2.startswith('Type') or s2.startswith('</Coefficient') or s2.startswith('<Mkb'):
                    break
                vals = s2.split()
                if len(vals) > 0:
                    try:
                        coeffs.extend([float(v) for v in vals])
                    except ValueError:
                        break
                i += 1

            orbitals.append({
                'L': L, 'N': N - 1,  # N is 1-based in ORBITAL_RESULTS
                'C4': np.array(coeffs)
            })
            orb_count += 1
        else:
            i += 1

    return orbitals, i


def parse_jle_orb(filepath):
    """Parse jle.orb file containing spherical Bessel basis functions jl(q[ie], r)."""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    # Parse header
    ecut = None
    rcut = None
    lmax = None
    n_orbitals = {}
    mesh = None
    dr = None

    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith('Energy Cutoff'):
            ecut = float(s.split()[-1])
        elif s.startswith('Radius Cutoff'):
            rcut = float(s.split()[-1])
        elif s.startswith('Lmax'):
            lmax = int(s.split()[-1])
        elif s.startswith('Number of Sorbital'):
            n_orbitals[0] = int(s.split('-->')[-1])
        elif s.startswith('Number of Porbital'):
            n_orbitals[1] = int(s.split('-->')[-1])
        elif s.startswith('Number of Dorbital'):
            n_orbitals[2] = int(s.split('-->')[-1])
        elif s.startswith('Number of Forbital'):
            n_orbitals[3] = int(s.split('-->')[-1])
        elif s.startswith('Number of Gorbital'):
            n_orbitals[4] = int(s.split('-->')[-1])
        elif s.startswith('Mesh'):
            mesh = int(s.split()[-1])
        elif s.strip().startswith('dr'):
            dr = float(s.split()[-1])
        elif s.startswith('Type'):
            # Mesh/dr already read, data section starts
            break
        i += 1

    # Parse orbital data (each stores jl(q[ie], r) for one eigenvalue)
    jle_orbs = []
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith('Type'):
            parts = s.split()
            type_idx = parts.index('Type')
            l_idx = parts.index('L')
            n_idx = parts.index('N')
            i += 1
            parts2 = lines[i].split()
            L_jle = int(parts2[l_idx])
            N_jle = int(parts2[n_idx])
            i += 1

            data = []
            while len(data) < mesh and i < len(lines):
                vals = lines[i].split()
                if len(vals) == 0:
                    break
                try:
                    data.extend([float(v) for v in vals])
                except ValueError:
                    break
                i += 1

            jle_orbs.append({
                'L': L_jle, 'N': N_jle,
                'data': np.array(data[:mesh])
            })
        else:
            i += 1

    return {
        'ecut': ecut, 'rcut': rcut, 'lmax': lmax,
        'n_orbitals': n_orbitals, 'mesh': mesh, 'dr': dr,
        'orbitals': jle_orbs
    }


def reconstruct_orbital(C4, L, jle_orbs, mesh, dr):
    """Reconstruct r*phi(r) = sum_{ie} C4[ie] * jl(q[ie], r)."""
    r = np.arange(mesh) * dr
    rphi = np.zeros(mesh)

    # Find jl basis functions for this L
    jl_basis = [o for o in jle_orbs if o['L'] == L]
    jl_basis.sort(key=lambda x: x['N'])

    n_coeff = min(len(C4), len(jl_basis))
    for ie in range(n_coeff):
        jl_data = jl_basis[ie]['data']
        # Ensure same mesh size
        n_mesh = min(mesh, len(jl_data))
        rphi[:n_mesh] += C4[ie] * jl_data[:n_mesh]

    return rphi


def write_orb_file(filepath, element, ecut, rcut, lmax, n_orb_per_l, orbitals):
    """Write ABACUS .orb format file."""
    mesh = 1001  # standard for dr=0.01, rcut=10au
    dr = 0.01

    lines = []
    lines.append('---------------------------------------------------------------------------\n')
    lines.append(f'Element                     {element}\n')
    lines.append(f'Energy Cutoff(Ry)           {int(ecut)}\n')
    lines.append(f'Radius Cutoff(a.u.)         {int(rcut)}\n')
    lines.append(f'Lmax                        {lmax}\n')

    l_names = ['S', 'P', 'D', 'F', 'G']
    for l in range(lmax + 1):
        n = n_orb_per_l[l] if l < len(n_orb_per_l) else 0
        lines.append(f'Number of {l_names[l]}orbital-->       {n}\n')

    lines.append('---------------------------------------------------------------------------\n')
    lines.append('SUMMARY  END\n')
    lines.append('\n')
    lines.append(f'Mesh                        {mesh}\n')
    lines.append(f'dr                          {dr}\n')

    for orb in orbitals:
        L = orb['L']
        N = orb['N']
        data = orb['data']

        lines.append(f'                Type                   L                   N\n')
        lines.append(f'                   0                   {L}                   {N}\n')

        # Write data, 4 values per line
        for j in range(0, mesh, 4):
            chunk = data[j:j+4]
            line_str = '  '.join(f'{v:.14e}' for v in chunk)
            lines.append(f'  {line_str}\n')

    with open(filepath, 'w') as f:
        f.writelines(lines)

    print(f'Wrote: {filepath}')
    return mesh


def main():
    parser = argparse.ArgumentParser(description='Convert SIAB results to ABACUS .orb')
    parser.add_argument('--results', required=True, help='ORBITAL_RESULTS_levelN.txt')
    parser.add_argument('--jle', required=True, help='jle.orb file from ABACUS PW')
    parser.add_argument('--ecut', type=float, required=True, help='Energy cutoff (Ry)')
    parser.add_argument('--rcut', type=float, required=True, help='Radius cutoff (a.u.)')
    parser.add_argument('--element', required=True, help='Element symbol')
    parser.add_argument('--lmax', type=int, required=True, help='Max angular momentum')
    parser.add_argument('--norb', required=True,
                        help='Space-separated nchi per L, e.g. "3 3 2" for 3s3p2d')
    parser.add_argument('--output', required=True, help='Output .orb file path')
    args = parser.parse_args()

    # Parse norb
    n_orb_per_l = [int(x) for x in args.norb.split()]

    # Read ORBITAL_RESULTS
    with open(args.results, 'r') as f:
        lines = f.readlines()

    # Find <Coefficient> block
    coeff_start = None
    for i, line in enumerate(lines):
        if line.strip() == '<Coefficient>':
            coeff_start = i
            break

    if coeff_start is None:
        print('ERROR: <Coefficient> block not found in results file')
        sys.exit(1)

    # Parse C4 coefficients
    orbitals, _ = parse_orbitals_block(lines, coeff_start + 1)

    print(f'Found {len(orbitals)} orbitals in ORBITAL_RESULTS:')
    for orb in orbitals:
        print(f'  L={orb["L"]}, N={orb["N"]}, C4 length={len(orb["C4"])}')

    # Read jle.orb
    jle_data = parse_jle_orb(args.jle)
    print(f'\njle.orb: ecut={jle_data["ecut"]}, rcut={jle_data["rcut"]}, '
          f'lmax={jle_data["lmax"]}, mesh={jle_data["mesh"]}, dr={jle_data["dr"]}')
    print(f'  jl basis functions per L: {jle_data["n_orbitals"]}')

    # Reconstruct orbitals
    mesh_out = int(args.rcut / 0.01) + 1  # 1001 for 10au
    dr_out = 0.01

    for orb in orbitals:
        L = orb['L']
        C4 = orb['C4']
        rphi = reconstruct_orbital(C4, L, jle_data['orbitals'],
                                    max(mesh_out, jle_data['mesh']), dr_out)
        # Truncate to output mesh
        orb['data'] = rphi[:mesh_out]

    # Write .orb file
    write_orb_file(args.output, args.element, args.ecut, args.rcut,
                   args.lmax, n_orb_per_l, orbitals)

    # Quick stats
    print(f'\nOrbital file written: {args.output}')
    print(f'  Mesh points: {mesh_out}, dr={dr_out}')
    print(f'  R_max: {mesh_out * dr_out:.2f} a.u.')
    for orb in orbitals:
        data = orb['data']
        r = np.arange(len(data)) * dr_out
        norm = np.trapz(data**2, r)
        print(f'  L={orb["L"]} N={orb["N"]}: norm^2={norm:.6f}, '
              f'max={np.max(np.abs(data)):.4f}')


if __name__ == '__main__':
    main()
