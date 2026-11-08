#!/usr/bin/env python3
"""Plot radial orbital functions from ABACUS .orb files for inspection."""

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import argparse
import sys
import os

l_labels = {0: 's', 1: 'p', 2: 'd', 3: 'f', 4: 'g'}
colors = plt.cm.tab10(np.linspace(0, 1, 10))


def parse_orb(filepath):
    """Parse an ABACUS .orb file."""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    element = None
    ecut = None
    rcut = None
    lmax = None
    n_orbitals = {}
    mesh = None
    dr = None

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('Element'):
            element = stripped.split()[-1]
        elif stripped.startswith('Energy Cutoff'):
            ecut = float(stripped.split()[-1])
        elif stripped.startswith('Radius Cutoff'):
            rcut = float(stripped.split()[-1])
        elif stripped.startswith('Lmax'):
            lmax = int(stripped.split()[-1])
        elif stripped.startswith('Number of Sorbital'):
            n_orbitals[0] = int(stripped.split('-->')[-1])
        elif stripped.startswith('Number of Porbital'):
            n_orbitals[1] = int(stripped.split('-->')[-1])
        elif stripped.startswith('Number of Dorbital'):
            n_orbitals[2] = int(stripped.split('-->')[-1])
        elif stripped.startswith('Number of Forbital'):
            n_orbitals[3] = int(stripped.split('-->')[-1])
        elif stripped.startswith('Number of Gorbital'):
            n_orbitals[4] = int(stripped.split('-->')[-1])
        elif stripped.startswith('Mesh'):
            mesh = int(stripped.split()[-1])
        elif stripped.startswith('dr '):
            dr = float(stripped.split()[-1])
        elif stripped.startswith('Type'):
            break
        i += 1

    orbitals = []
    r = np.arange(mesh) * dr

    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith('Type'):
            parts = stripped.split()
            type_idx = parts.index('Type')
            l_idx = parts.index('L')
            n_idx = parts.index('N')
            i += 1
            parts2 = lines[i].split()
            L = int(parts2[l_idx])
            N = int(parts2[n_idx])
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
            data = np.array(data[:mesh])
            orbitals.append({'L': L, 'N': N, 'data': data})
        else:
            i += 1

    return {
        'element': element, 'ecut': ecut, 'rcut': rcut, 'lmax': lmax,
        'n_orbitals': n_orbitals, 'mesh': mesh, 'dr': dr,
        'r': r, 'orbitals': orbitals
    }


def plot_orbital(data, output_path):
    """Plot all radial functions r*phi(r) from parsed orbital data."""
    fig, ax = plt.subplots(figsize=(12, 8))

    r = data['r']
    ci = 0
    for orb in data['orbitals']:
        L, N = orb['L'], orb['N']
        rphi = orb['data']
        l_name = l_labels.get(L, f'L={L}')
        ax.plot(r, rphi, color=colors[ci % 10], linewidth=1.2,
                label=f'{l_name}{N+1} (L={L}, zeta={N})')
        ci += 1

    ax.set_xlabel('r (a.u.)', fontsize=14)
    ax.set_ylabel('r·φ(r)', fontsize=14)
    ax.set_title(f'{data["element"]}: {data["ecut"]:.0f}Ry, {data["rcut"]:.0f}au, '
                 f'{int(sum(data["n_orbitals"].values()))} NAOs',
                 fontsize=14, fontweight='bold')
    ax.legend(fontsize=10, ncol=3, loc='upper right')
    ax.axhline(y=0, color='gray', linewidth=0.4, linestyle='--')
    ax.axvline(x=data['rcut'], color='red', linewidth=0.5, linestyle=':', alpha=0.5)
    ax.tick_params(labelsize=12)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f'Saved: {output_path}')

    # Print orbital info
    print(f'\n{data["element"]}: {data["ecut"]:.0f}Ry, {data["rcut"]:.0f}au, '
          f'Lmax={data["lmax"]}, Mesh={data["mesh"]}, dr={data["dr"]}')
    print(f'  Orbitals per L: {data["n_orbitals"]}')
    total = sum(data['n_orbitals'].get(l, 0) * (2*l+1) for l in range(data['lmax']+1))
    print(f'  Total basis size: {total}')
    for orb in data['orbitals']:
        rphi = orb['data']
        norm2 = np.trapz(rphi**2, r)
        print(f'  L={orb["L"]} N={orb["N"]} ({l_labels.get(orb["L"], "?")}{orb["N"]+1}): '
              f'norm²={norm2:.6f}, max|rφ|={np.max(np.abs(rphi)):.4f}')


def main():
    parser = argparse.ArgumentParser(description='Plot ABACUS .orb radial functions')
    parser.add_argument('orb_file', help='Path to .orb file')
    parser.add_argument('--output', '-o', help='Output PNG path (default: <orb_basename>.png)')
    args = parser.parse_args()

    if not os.path.exists(args.orb_file):
        print(f'ERROR: File not found: {args.orb_file}')
        sys.exit(1)

    data = parse_orb(args.orb_file)

    output = args.output or os.path.splitext(args.orb_file)[0] + '.png'
    plot_orbital(data, output)


if __name__ == '__main__':
    main()
