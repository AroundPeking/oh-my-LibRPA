#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path


def parse_stru(path: Path):
    lines = [line.strip() for line in path.read_text().splitlines()]

    lattice_constant = None
    lattice_vectors = []
    atoms = []

    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith('#'):
            index += 1
            continue
        if line == 'LATTICE_CONSTANT':
            lattice_constant = float(lines[index + 1].split()[0])
            index += 2
            continue
        if line == 'LATTICE_VECTORS':
            lattice_vectors = [list(map(float, lines[index + 1 + offset].split()[:3])) for offset in range(3)]
            index += 4
            continue
        if line == 'ATOMIC_POSITIONS':
            coord_mode = lines[index + 1].strip().lower()
            index += 2
            while index < len(lines):
                if not lines[index]:
                    index += 1
                    continue
                species = lines[index]
                index += 1
                if index >= len(lines):
                    break
                _mag = lines[index]
                index += 1
                count = int(lines[index].split()[0])
                index += 1
                for _ in range(count):
                    parts = lines[index].split()
                    atoms.append((species, list(map(float, parts[:3])), coord_mode))
                    index += 1
            continue
        index += 1

    if lattice_constant is None or len(lattice_vectors) != 3 or not atoms:
        raise ValueError('Failed to parse STRU: lattice or atom section is incomplete')

    lat_bohr = [[value * lattice_constant for value in row] for row in lattice_vectors]
    return lat_bohr, atoms


def inverse_3x3(matrix):
    a, b, c = matrix[0]
    d, e, f = matrix[1]
    g, h, i = matrix[2]
    det = (
        a * (e * i - f * h)
        - b * (d * i - f * g)
        + c * (d * h - e * g)
    )
    if abs(det) < 1e-14:
        raise ValueError('Lattice matrix is singular')
    inv = [
        [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
        [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
        [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
    ]
    return inv


def reciprocal_from_lat(lat_bohr):
    inv = inverse_3x3(lat_bohr)
    twopi = 2.0 * math.pi
    return [[twopi * inv[col][row] for col in range(3)] for row in range(3)]


def frac_to_cart(frac, lat_bohr):
    return [
        frac[0] * lat_bohr[0][axis] + frac[1] * lat_bohr[1][axis] + frac[2] * lat_bohr[2][axis]
        for axis in range(3)
    ]


def parse_kpt_grid(path: Path):
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3:
            try:
                return [int(parts[0]), int(parts[1]), int(parts[2])]
            except ValueError:
                continue
    raise ValueError(f'Failed to parse k-grid from {path}')


def parse_abacus_kpoints(path: Path, recip_bohr):
    kpts_cart = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].isdigit():
            frac = [float(parts[1]), float(parts[2]), float(parts[3])]
            cart = [
                frac[0] * recip_bohr[0][axis] + frac[1] * recip_bohr[1][axis] + frac[2] * recip_bohr[2][axis]
                for axis in range(3)
            ]
            kpts_cart.append(cart)
    if not kpts_cart:
        raise ValueError(f'Failed to parse k-points from {path}')
    return kpts_cart


def main():
    parser = argparse.ArgumentParser(description='Generate a LibRPA-compatible stru_out from ABACUS STRU + kpoints')
    parser.add_argument('--stru', default='STRU')
    parser.add_argument('--kpt', default='KPT')
    parser.add_argument('--kpoints', default='OUT.ABACUS/kpoints')
    parser.add_argument('--output', default='stru_out')
    args = parser.parse_args()

    stru_path = Path(args.stru)
    kpt_path = Path(args.kpt)
    kpoints_path = Path(args.kpoints)
    output_path = Path(args.output)

    lat_bohr, atoms = parse_stru(stru_path)
    recip_bohr = reciprocal_from_lat(lat_bohr)
    k_grid = parse_kpt_grid(kpt_path)
    kpts_cart = parse_abacus_kpoints(kpoints_path, recip_bohr)

    with output_path.open('w', encoding='utf-8') as handle:
        for row in lat_bohr:
            handle.write(f'{row[0]:.10f} {row[1]:.10f} {row[2]:.10f}\n')
        for row in recip_bohr:
            handle.write(f'{row[0]:.10f} {row[1]:.10f} {row[2]:.10f}\n')
        handle.write(f'{len(atoms)}\n')
        for atom_index, (_species, coords, coord_mode) in enumerate(atoms, start=1):
            cart = coords if coord_mode.startswith('cart') else frac_to_cart(coords, lat_bohr)
            handle.write(f'{cart[0]:.6f} {cart[1]:.6f} {cart[2]:.6f} {atom_index}\n')
        handle.write(f'{k_grid[0]} {k_grid[1]} {k_grid[2]}\n')
        for cart in kpts_cart:
            handle.write(f'{cart[0]:.9f} {cart[1]:.9f} {cart[2]:.9f}\n')
        for mapping in range(1, len(kpts_cart) + 1):
            handle.write(f'{mapping}\n')


if __name__ == '__main__':
    main()
