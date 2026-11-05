"""The band figure is the acceptance artifact for the periodic GW routes."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from oml_mcp.band_analysis import ACCEPTANCE_RULE, analyze_band_set
from oml_mcp.band_figure import DEFAULT_FIGURE_NAME, render_band_figure


def write_band(path: pathlib.Path, rows, *, occupations) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index, (kx, ky, kz, energies) in enumerate(rows, start=1):
            cells = [f"{index:5d}", f"{kx:.7f}", f"{ky:.7f}", f"{kz:.7f}"]
            for energy, occupation in zip(energies, occupations):
                cells.extend([f"{occupation:.5f}", f"{energy:.5f}"])
            handle.write("  ".join(cells) + "\n")


class BandFigureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        occupations = (2.0, 2.0, 0.0, 0.0)
        grid = [(0.0, 0.0, 0.0), (0.25, 0.0, 0.0), (0.5, 0.0, 0.5)]
        ks = [(-1.0, -0.5, 0.6, 1.2), (-1.2, 0.2, 0.9, 1.5), (-0.9, 0.5, 1.1, 1.8)]
        exx = [(-2.0, 0.0, 3.0, 4.2), (-2.2, 0.8, 3.4, 4.6), (-1.9, 1.1, 3.6, 4.9)]
        gw = [(-1.4, -0.1, 1.8, 3.0), (-1.6, 0.5, 2.1, 3.4), (-1.3, 0.9, 2.3, 3.7)]
        for name, table in (("KS", ks), ("EXX", exx), ("GW", gw)):
            write_band(
                self.root / f"{name}_band_spin_1.dat",
                [(kx, ky, kz, energies) for (kx, ky, kz), energies in zip(grid, table)],
                occupations=occupations,
            )
        self.paths = {
            "ks": self.root / "KS_band_spin_1.dat",
            "exx": self.root / "EXX_band_spin_1.dat",
            "gw": self.root / "GW_band_spin_1.dat",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_render_writes_a_png_and_reports_each_layer(self) -> None:
        target = self.root / "figure" / DEFAULT_FIGURE_NAME
        report = render_band_figure(self.paths, target, occupied_bands=2)
        self.assertTrue(target.is_file())
        self.assertGreater(target.stat().st_size, 5000)
        self.assertEqual(report["layers"], ["ks", "exx", "gw"])
        self.assertEqual(report["occupied_bands"], 2)
        self.assertAlmostEqual(report["gaps_ev"]["gw"], 1.8 - 0.9, places=6)

    def test_acceptance_rule_names_the_figure_and_advisory_gap(self) -> None:
        self.assertIn("band figure", ACCEPTANCE_RULE)
        self.assertIn("advisory", ACCEPTANCE_RULE)

    def test_qp_correction_gate_rejects_a_collapsed_sigma_c(self) -> None:
        # Empty states move by -500 eV while occupied states stay put: the
        # signature of an over-counted star sum in Sigma_c.
        write_band(
            self.root / "GW_band_spin_1.dat",
            [
                (0.0, 0.0, 0.0, [-1.5, -0.6, -120.0, -110.0]),
                (0.25, 0.0, 0.0, [-1.7, 0.1, -200.0, -180.0]),
                (0.5, 0.0, 0.5, (-1.4, 0.4, -553.0, -520.0)),
            ],
            occupations=(2.0, 2.0, 0.0, 0.0),
        )
        report = analyze_band_set(self.paths, occupied_bands=2)
        self.assertFalse(report["accepted"])
        self.assertFalse(report["qp_correction"]["accepted"])
        reasons = " ".join(report["reasons"])
        self.assertIn("GW correction reaches", reasons)
        self.assertIn("over-counted star sum", reasons)

    def test_gap_collapse_check_rejects_a_negative_gw_gap(self) -> None:
        write_band(
            self.root / "GW_band_spin_1.dat",
            [
                (0.0, 0.0, 0.0, [-1.4, -1.0, -3.0, -2.0]),
                (0.25, 0.0, 0.0, [-1.6, -0.9, -2.8, -2.1]),
                (0.5, 0.0, 0.5, (-1.3, -0.95, -2.9, -2.2)),
            ],
            occupations=(2.0, 2.0, 0.0, 0.0),
        )
        report = analyze_band_set(self.paths, occupied_bands=2)
        self.assertFalse(report["accepted"])
        self.assertIn("collapsed against the KS gap", " ".join(report["reasons"]))

    def test_gap_delta_is_advisory_inside_the_gross_limit(self) -> None:
        base = analyze_band_set(self.paths, occupied_bands=2)
        gw_gap = base["gaps"]["gw"]["indirect_gap_ev"]
        off = analyze_band_set(self.paths, occupied_bands=2, gap_reference_ev=gw_gap - 0.4)
        self.assertFalse(off["gap_check"]["pass"])
        self.assertEqual(off["gap_check"]["status"], "ADVISORY")
        self.assertTrue(off["accepted"])


if __name__ == "__main__":
    unittest.main()
