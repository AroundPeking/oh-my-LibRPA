import pathlib
import tempfile
import unittest

from oml_mcp.band_analysis import (
    BandAnalysisError,
    analyze_band_set,
    gaps,
    load_layer,
    reorder_by_nearest,
    smoothness,
)


OCCUPATIONS = (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)


def write_band(path: pathlib.Path, rows, occupations=OCCUPATIONS) -> None:
    lines = []
    for index, kx, ky, kz, energies in rows:
        fields = [str(index), repr(kx), repr(ky), repr(kz)]
        for occupation, energy in zip(occupations, energies):
            fields.extend([repr(occupation), repr(energy)])
        lines.append(" ".join(fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def smooth_rows(offset: float) -> list:
    rows = []
    for k in range(5):
        shift = 0.01 * k
        energies = [-1.0 + shift, -0.8 + shift, -0.6 + shift, 1.0 + shift, 1.2 + shift, 1.4 + shift]
        rows.append((k + 1, k / 5.0, 0.0, 0.0, [energy + offset for energy in energies]))
    return rows


class BandAnalysisTest(unittest.TestCase):
    def _triple(self, root: pathlib.Path, *, gw_spike: bool = False) -> pathlib.Path:
        write_band(root / "KS_band_spin_1.dat", smooth_rows(0.0))
        write_band(root / "EXX_band_spin_1.dat", smooth_rows(0.5))
        gw_rows = smooth_rows(0.7)
        if gw_spike:
            index, kx, ky, kz, energies = gw_rows[2]
            energies = list(energies)
            energies[4] += 0.8
            gw_rows[2] = (index, kx, ky, kz, energies)
        write_band(root / "GW_band_spin_1.dat", gw_rows)
        return root

    def test_smooth_triple_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._triple(pathlib.Path(tmpdir))
            report = analyze_band_set(
                {
                    "ks": root / "KS_band_spin_1.dat",
                    "exx": root / "EXX_band_spin_1.dat",
                    "gw": root / "GW_band_spin_1.dat",
                },
                occupied_bands=3,
            )
        self.assertTrue(report["accepted"], report["reasons"])
        self.assertEqual(report["reasons"], [])
        self.assertEqual(report["localization"]["layer"], "none")

    def test_gw_spike_is_not_smooth_and_localizes_to_gw(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._triple(pathlib.Path(tmpdir), gw_spike=True)
            report = analyze_band_set(
                {
                    "ks": root / "KS_band_spin_1.dat",
                    "exx": root / "EXX_band_spin_1.dat",
                    "gw": root / "GW_band_spin_1.dat",
                },
                occupied_bands=3,
            )
        self.assertFalse(report["accepted"])
        self.assertFalse(report["smoothness"]["gw"]["smooth"])
        self.assertEqual(report["localization"]["layer"], "gw")
        self.assertIn("non-smooth bands", " ".join(report["reasons"]))

    def test_gap_reference_comparison(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = self._triple(pathlib.Path(tmpdir))
            paths = {
                "ks": root / "KS_band_spin_1.dat",
                "exx": root / "EXX_band_spin_1.dat",
                "gw": root / "GW_band_spin_1.dat",
            }
            first = analyze_band_set(paths, occupied_bands=3)
            gap = first["gaps"]["gw"]["indirect_gap_ev"]
            passing = analyze_band_set(paths, occupied_bands=3, gap_reference_ev=gap)
            failing = analyze_band_set(paths, occupied_bands=3, gap_reference_ev=gap + 0.5)
        self.assertTrue(passing["gap_check"]["pass"])
        self.assertFalse(failing["gap_check"]["pass"])
        self.assertFalse(failing["accepted"])
        self.assertIn("differs from the reference", " ".join(failing["reasons"]))

    def test_reorder_tracks_a_crossing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_band(
                root / "KS_band_spin_1.dat",
                [
                    (1, 0.0, 0.0, 0.0, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
                    (2, 0.1, 0.0, 0.0, [1.5, -0.5, 2.1, 3.1, 4.1, 5.1]),
                ],
                occupations=(1.0, 1.0, 1.0, 0.0, 0.0, 0.0),
            )
            layer = load_layer(root / "KS_band_spin_1.dat", quantity="ks")
        orders, rows = reorder_by_nearest(layer)
        self.assertEqual(orders[1][0], 1)  # the low band continues into the former column 1
        self.assertEqual(orders[1][1], 0)

    def test_gaps_from_occupations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_band(root / "GW_band_spin_1.dat", smooth_rows(0.0))
            layer = load_layer(root / "GW_band_spin_1.dat", quantity="gw")
        report = gaps(layer)
        self.assertEqual(report["occupied_bands"], 3)
        self.assertGreater(report["indirect_gap_ev"], 0)
        self.assertGreater(report["direct_gap_ev"], 0)

    def test_mismatched_state_counts_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_band(root / "KS_band_spin_1.dat", smooth_rows(0.0))
            write_band(root / "GW_band_spin_1.dat", smooth_rows(0.7))
            # Re-write EXX with a different band count.
            rows = [row[:4] + (row[4][:3],) for row in smooth_rows(0.5)]
            write_band(root / "EXX_band_spin_1.dat", rows, occupations=OCCUPATIONS[:3])
            with self.assertRaises(BandAnalysisError):
                analyze_band_set(
                    {
                        "ks": root / "KS_band_spin_1.dat",
                        "exx": root / "EXX_band_spin_1.dat",
                        "gw": root / "GW_band_spin_1.dat",
                    },
                    occupied_bands=2,
                )

    def test_smoothness_needs_three_kpoints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_band(root / "KS_band_spin_1.dat", smooth_rows(0.0)[:2], occupations=OCCUPATIONS)
            layer = load_layer(root / "KS_band_spin_1.dat", quantity="ks")
        report = smoothness(layer.energies)
        self.assertFalse(report["evaluated"])
        self.assertFalse(report["smooth"])


if __name__ == "__main__":
    unittest.main()
