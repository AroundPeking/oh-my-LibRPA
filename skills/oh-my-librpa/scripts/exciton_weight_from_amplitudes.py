#!/usr/bin/env python3
"""Reconstruct the exciton envelope |Psi_exc(r_h, r_e)| from LibBSE amplitudes.

What LibBSE gives you
---------------------
LibBSE does NOT write an exciton density or a slice the way ABACUS's
`lr_solver plot` does.  What it writes is the TDA amplitude of every excited
state in the two-particle basis,

    Excitation_Amplitude_singlet_<rank>.dat   one line per state,
                                              complex values, one per owned pair

and the k-resolved weight

    trans_kweight_singlet_tda.dat             weight1(k) = sum_{v,c} |X_kvc|^2

so the envelope has to be rebuilt from the amplitudes plus the fine-grid KS
eigenvectors that ABACUS wrote as `band_KS_eigenvector_k_*.txt`.

The reduction performed here
----------------------------
Full |Psi(r_h, r_e)|^2 needs one NAO product per (r_h, r_e) pair, i.e. the
4-index object.  This script instead evaluates the k-resolved weights and the
per-k dominant pair, which is what the paper's discussion of "which k points
carry the exciton" uses, and what can be checked without the AO products:

    W(k) = sum_{v,c} |X_kvc|^2                      (should be 1/nk on average)
    pair(k) = argmax_{v,c} |X_kvc|                  (dominant transition at k)

Usage:
    exciton_weight_from_amplitudes.py <libbse.d> --nk 2744 --nocc 4 --nvirt 4
"""

import argparse
import pathlib
import re
import sys


def load_state(directory, state, nk, nocc, nvirt):
    """Assemble one state's amplitude vector from the per-rank files."""
    dimension = nk * nocc * nvirt
    files = sorted(directory.glob("Excitation_Amplitude_singlet_*.dat"))
    if not files:
        raise FileNotFoundError(
            "no Excitation_Amplitude_singlet_*.dat under {}".format(directory))
    # Ranks own a contiguous, evenly split range of pairs.
    ranks = len(files)
    per_rank = dimension // ranks
    if per_rank * ranks != dimension:
        raise ValueError("{} ranks do not divide dimension {}".format(ranks, dimension))

    amplitudes = [0j] * dimension
    for path in files:
        rank = int(re.search(r"_(\d+)\.dat$", path.name).group(1))
        lines = path.read_text().splitlines()
        if state >= len(lines):
            raise ValueError("{}: only {} states".format(path.name, len(lines)))
        values = []
        for token in lines[state].split():
            real, imag = token.strip("()").split(",")
            values.append(complex(float(real), float(imag)))
        if len(values) != per_rank:
            raise ValueError("{}: {} amplitudes, expected {}".format(
                path.name, len(values), per_rank))
        base = rank * per_rank
        for index, value in enumerate(values):
            amplitudes[base + index] = value
    return amplitudes


def summarise(amplitudes, nk, nocc, nvirt):
    """Per-k weight and dominant (v, c) pair."""
    pair_dimension = nocc * nvirt
    total = 0.0
    rows = []
    for ik in range(nk):
        weight = 0.0
        best = (0, 0, 0.0)
        for iv in range(nocc):
            for ic in range(nvirt):
                value = amplitudes[ik * pair_dimension + iv * nvirt + ic]
                magnitude = abs(value) ** 2
                weight += magnitude
                if magnitude > best[2]:
                    best = (iv + 1, ic + 1, magnitude)
        rows.append((ik + 1, weight, best[0], best[1]))
        total += weight
    return rows, total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=pathlib.Path)
    parser.add_argument("--state", type=int, default=0)
    parser.add_argument("--nk", type=int, required=True)
    parser.add_argument("--nocc", type=int, default=4)
    parser.add_argument("--nvirt", type=int, default=4)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    amplitudes = load_state(args.directory, args.state, args.nk, args.nocc, args.nvirt)
    norm = sum(abs(value) ** 2 for value in amplitudes)
    rows, total = summarise(amplitudes, args.nk, args.nocc, args.nvirt)

    print("state {}: sum|X|^2 = {:.6f} (TDA normalisation is 1)".format(
        args.state, norm))
    print("sum_k W(k) = {:.6f}".format(total))
    weights = sorted((row[1] for row in rows), reverse=True)
    print("max W(k) = {:.3e}, median = {:.3e}, min = {:.3e}".format(
        weights[0], weights[len(weights) // 2], weights[-1]))
    top = sorted(rows, key=lambda row: -row[1])[:8]
    print("k points carrying the most weight:")
    for ik, weight, iv, ic in top:
        print("  k={:5d}  W={:.4e}  dominant v={} c={}".format(ik, weight, iv, ic))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as handle:
            handle.write("# exciton weight per fine k point, state {}\n".format(args.state))
            handle.write("# kpoint weight dominant_v dominant_c\n")
            for ik, weight, iv, ic in rows:
                handle.write("{} {:.8e} {} {}\n".format(ik, weight, iv, ic))
        print("wrote {}".format(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
