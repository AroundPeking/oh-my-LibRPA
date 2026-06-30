#!/usr/bin/env python3
"""Preprocess ABACUS output to generate database for LibRPA GW/EXX band calculation

Caveats:
    - can handle spin=1 and 2 and SOC
"""

import pathlib
import os
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from array import array

HA2EV = 27.211386245988
OCC_ZERO_TOL = 1e-12
OCC_INTEGER_TOL = 1e-8


def get_kpoints(kpoint_file):
    kpoints = []
    with open(kpoint_file, "r") as h:
        for line in h:
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                kpoints.append((float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                continue
    assert kpoints
    return kpoints


def cleanup():
    for p in pathlib.Path(".").glob("band_*_k_*.txt"):
        print("Removing {}".format(p))
        p.unlink()

    fn = "band_kpath_info"
    if os.path.exists(fn):
        print("Removing {}".format(fn))
        os.remove(fn)


def process_vxc(outdir, nkpts):
    fn = outdir / "vxc_out.dat"
    with open(fn, 'r') as h:
        lines_all = h.readlines()
    assert (nkpts == int(lines_all[0].strip()))
    nspins = int(lines_all[1].strip())
    nbands = int(lines_all[2].strip())
    lines_all = lines_all[3:]
    assert (len(lines_all) == nspins * nbands * nkpts)

    for ik in range(nkpts):
        lines_k = lines_all[nspins * nbands * ik:nspins * nbands * (ik + 1)]
        vxc = []
        for l in lines_k:
            vxc.append(float(l.split()[0]))

        with open("band_vxc_k_{:05d}.txt".format(ik + 1), 'w') as h:
            for ispin in range(nspins):
                for ib in range(nbands):
                    print("{:8d} {:7d} {:27.16E}"
                          .format(ispin + 1, ib + 1, vxc[ispin * nbands + ib]), file=h)
    return nspins


def resolve_wfc_file(outdir, ik, isp, nspin, use_soc):
    if use_soc:
        candidates = [
            outdir / "wfs12k{:d}_nao.txt".format(ik + 1),
            outdir / "wfk{:d}s4_nao.txt".format(ik + 1),
        ]
    else:
        candidates = []
        if nspin == 1:
            candidates.extend([
                outdir / "wfs1k{:d}_nao.txt".format(ik + 1),
                outdir / "wfs1_nao.txt",
                outdir / "wfk{:d}_nao.txt".format(ik + 1),
            ])
        elif nspin == 2:
            candidates.extend([
                outdir / "wfs{:d}k{:d}_nao.txt".format(isp + 1, ik + 1),
                outdir / "wfs{:d}_nao.txt".format(isp + 1),
                outdir / "wfk{:d}s{:d}_nao.txt".format(ik + 1, isp + 1),
            ])
        else:
            candidates.extend([
                outdir / "wfs{:d}k{:d}_nao.txt".format(isp + 1, ik + 1),
                outdir / "wfk{:d}s{:d}_nao.txt".format(ik + 1, isp + 1),
            ])

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            return candidate

    raise FileNotFoundError("Cannot find wavefunction file for k-point {} in {}".format(ik + 1, outdir))


def occupation_target(nspin, use_soc):
    return 1.0 if use_soc or nspin != 1 else 2.0


def normalize_band_occupations(occs, nspin, use_soc, source=""):
    """Convert ABACUS k-weighted wfc occupations to physical occupations.

    ABACUS writes wfs*_nao.txt occupations as internal k-weighted `wg`.
    LibRPA band inputs expect the physical occupation because the reader applies
    its own k-point normalization.
    """
    positive_occs = [occ for occ in occs if occ > OCC_ZERO_TOL]
    if not positive_occs:
        return occs

    max_occ = max(positive_occs)
    target = occupation_target(nspin, use_soc)
    if max_occ <= OCC_ZERO_TOL:
        scale = 1.0
    elif max_occ < target - OCC_INTEGER_TOL:
        scale = target / max_occ
    else:
        scale = 1.0

    normalized = []
    for occ in occs:
        value = 0.0 if abs(occ) <= OCC_ZERO_TOL else occ * scale
        if value < -OCC_INTEGER_TOL or value > target + OCC_INTEGER_TOL:
            detail = " in {}".format(source) if source else ""
            raise ValueError(
                "Out-of-range band occupation{} after removing ABACUS k-weight: "
                "{:.16E}; expected values between 0 and {:.1f}."
                .format(detail, value, target)
            )
        nearest = round(value)
        if abs(value - nearest) <= OCC_INTEGER_TOL:
            value = float(nearest)
        normalized.append(value)
    return normalized


def process_wfc(outdir, nkpts, nspin, use_soc = False):
    nbands = None
    nbasis = None
    for isp in range(nspin):
        for ik in range(nkpts):
            #isk = isp * nkpts + ik
            fn = resolve_wfc_file(outdir, ik, isp, nspin, use_soc)
            with open(fn, 'r') as h:
                lines = h.readlines()
            if nbands is None:
                nbands = int(lines[2].split()[0])
            if nbasis is None:
                nbasis = int(lines[3].split()[0])
            lines = lines[4:]
            indices_band = [i for i, l in enumerate(lines) if l.endswith("(band)\n")]
            assert (len(indices_band) == nbands)
            
            eigs = []
            occs = []
            vecs = []

            for i, index_band in enumerate(indices_band):
                if i != nbands - 1:
                    lines_band = lines[index_band:indices_band[i + 1]]
                else:
                    lines_band = lines[index_band:]
                eigs.append(float(lines_band[1].split()[0]))
                occs.append(float(lines_band[2].split()[0]))
                vecs.extend(map(float, " ".join(lines_band[3:]).replace("\n", " ").split()))

            # convert to numpy array
            eigs = [eig * 0.5 for eig in eigs]
            assert (len(eigs) == nbands)
            assert (len(occs) == nbands)
            assert (len(vecs) == nbands * nbasis * 2)
            occs = normalize_band_occupations(occs, nspin, use_soc, source=str(fn))

            mode = 'a'
            if isp == 0:
                mode = 'w'

            with open("band_KS_eigenvalue_k_{:05d}.txt".format(ik + 1), mode) as h:
                for ib in range(nbands):
                    print("{:8d} {:7d} {:27.16E} {:27.16E} {:27.16E}"
                          .format(isp + 1, ib + 1, occs[ib], eigs[ib], eigs[ib] * HA2EV), file=h)

            with open("band_KS_eigenvector_k_{:05d}.txt".format(ik + 1), mode + 'b') as h:
                array('d', vecs).tofile(h)

    return nbasis, nbands


def write_kpath_info(nspins, nbands, nbasis, kpoints):
    nkpts = len(kpoints)
    with open("band_kpath_info", "w") as h:
        print("{:6d} {:5d} {:5d} {:5d}".format(nbasis, nbands, nspins, nkpts), file=h)

        for kpt in kpoints:
            print("{:18.12f} {:17.12f} {:17.12f}".format(*kpt), file=h)


def _parser():
    p = ArgumentParser(description=__doc__, formatter_class=RawDescriptionHelpFormatter)
    p.add_argument("-d", dest="outdir", default="OUT.ABACUS", type=str)
    p.add_argument("--clean", dest="cleanup", action="store_true",
                   help="Clean up generated database")
    return p


def main():
    use_soc = False
    args = _parser().parse_args()

    if args.cleanup:
        cleanup()
        return

    outdir = pathlib.Path(args.outdir)

    kpoints = get_kpoints(outdir / "KPT.info")
    nkpts = len(kpoints)

    nspin = process_vxc(outdir, nkpts)
    nbasis, nbands = process_wfc(outdir, nkpts, nspin, use_soc)

    write_kpath_info(nspin, nbands, nbasis, kpoints)


if __name__ == '__main__':
    main()
