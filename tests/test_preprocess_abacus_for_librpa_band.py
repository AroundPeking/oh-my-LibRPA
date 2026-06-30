import importlib.util
import os
import pathlib
import tempfile
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "templates/abacus-librpa-gw/template/preprocess_abacus_for_librpa_band.py"


def load_preprocess_module():
    spec = importlib.util.spec_from_file_location("preprocess_abacus_for_librpa_band", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_vxc(outdir, nspin, nbands, nkpts):
    lines = [str(nkpts), str(nspin), str(nbands)]
    lines.extend("0.0" for _ in range(nspin * nbands * nkpts))
    (outdir / "vxc_out.dat").write_text("\n".join(lines) + "\n")


def write_wfc(path, nbands, nbasis, occupations):
    lines = ["# header", "# header", str(nbands), str(nbasis)]
    for ib, occ in enumerate(occupations, start=1):
        lines.extend([
            f"{ib} (band)",
            f"{float(ib):.8f} (Ry)",
            f"{occ:.16E} (Occupations)",
            "1.0 0.0",
        ])
    path.write_text("\n".join(lines) + "\n")


def read_band_occupations(path):
    occs = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 5:
            occs.append(float(parts[2]))
    return occs


class PreprocessBandOccupationsTest(unittest.TestCase):
    def run_process_wfc(self, nspin, use_soc, occupations_by_file):
        module = load_preprocess_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = pathlib.Path(tmpdir)
            outdir = tmp / "OUT.ABACUS"
            outdir.mkdir()
            nbands = 2
            nbasis = 1
            nkpts = len(next(iter(occupations_by_file.values())))
            write_vxc(outdir, nspin, nbands, nkpts)
            for filename, occupations_by_k in occupations_by_file.items():
                for ik, occupations in enumerate(occupations_by_k, start=1):
                    write_wfc(outdir / filename.format(ik=ik), nbands, nbasis, occupations)
            old_cwd = pathlib.Path.cwd()
            os.chdir(tmp)
            try:
                module.process_wfc(outdir, nkpts, nspin, use_soc=use_soc)
                return [
                    read_band_occupations(tmp / f"band_KS_eigenvalue_k_{ik:05d}.txt")
                    for ik in range(1, nkpts + 1)
                ]
            finally:
                os.chdir(old_cwd)

    def test_nspin2_weighted_band_occupations_are_written_as_integer_physical_occupations(self):
        occupations = self.run_process_wfc(
            nspin=2,
            use_soc=False,
            occupations_by_file={
                "wfs1k{ik}_nao.txt": [[0.25, 0.0], [0.75, 0.0]],
                "wfs2k{ik}_nao.txt": [[0.25, 0.0], [0.75, 0.0]],
            },
        )

        self.assertEqual(occupations, [[1.0, 0.0, 1.0, 0.0], [1.0, 0.0, 1.0, 0.0]])

    def test_soc_weighted_band_occupations_are_written_as_integer_physical_occupations(self):
        occupations = self.run_process_wfc(
            nspin=1,
            use_soc=True,
            occupations_by_file={
                "wfs12k{ik}_nao.txt": [[0.5, 0.0], [0.5, 0.0]],
            },
        )

        self.assertEqual(occupations, [[1.0, 0.0], [1.0, 0.0]])

    def test_nonspin_weighted_band_occupations_are_written_as_integer_physical_occupations(self):
        occupations = self.run_process_wfc(
            nspin=1,
            use_soc=False,
            occupations_by_file={
                "wfs1k{ik}_nao.txt": [[2.0 / 3.0, 0.0], [4.0 / 3.0, 0.0]],
            },
        )

        self.assertEqual(occupations, [[2.0, 0.0], [2.0, 0.0]])

    def test_fractional_physical_occupation_is_preserved_after_k_weight_removal(self):
        occupations = self.run_process_wfc(
            nspin=2,
            use_soc=False,
            occupations_by_file={
                "wfs1k{ik}_nao.txt": [[0.25, 0.125]],
                "wfs2k{ik}_nao.txt": [[0.25, 0.125]],
            },
        )

        self.assertEqual(occupations, [[1.0, 0.5, 1.0, 0.5]])


if __name__ == "__main__":
    unittest.main()
