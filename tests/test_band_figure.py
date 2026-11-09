"""The band figure is the acceptance artifact for the periodic GW routes."""

from __future__ import annotations

import pathlib
import tempfile
import unittest

from oml_mcp.band_analysis import ACCEPTANCE_RULE, analyze_band_set
from oml_mcp.band_figure import DEFAULT_FIGURE_NAME, SIDECAR_NAME, render_band_figure


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

    def test_render_writes_the_database_figure_set_and_reports_each_layer(self) -> None:
        # The acceptance artifact is the set the database record will carry:
        # one SVG per method plus the audit sidecars, not a single PNG.
        target = self.root / "figure" / DEFAULT_FIGURE_NAME
        report = render_band_figure(self.paths, target, occupied_bands=2)
        self.assertTrue(target.is_dir())
        for layer in ("ks", "exx", "gw"):
            figure = target / f"{layer}_frontier.svg"
            self.assertTrue(figure.is_file(), figure)
            text = figure.read_text(encoding="utf-8")
            self.assertGreater(len(text), 4000)
            self.assertIn("<svg", text)
            self.assertTrue((target / f"{layer}_frontier.json").is_file())
        self.assertTrue((target / SIDECAR_NAME).is_file())
        self.assertEqual(report["layers"], ["ks", "exx", "gw"])
        self.assertEqual(report["occupied_bands"], 2)
        self.assertAlmostEqual(report["gaps_ev"]["gw"], 1.8 - 0.9, places=6)
        self.assertEqual(report["render_standard"], "LibRPA-database scripts/plot_bands.py")

    def test_the_figure_is_vendored_at_a_recorded_upstream_commit(self) -> None:
        # The rendering rules come from the database; if that file is edited in
        # place the figures and the records they back can drift apart.
        from oml_mcp import band_frontier

        self.assertRegex(band_frontier.UPSTREAM_COMMIT, r"^[0-9a-f]{40}$")
        self.assertEqual(band_frontier.UPSTREAM_PATH, "scripts/plot_bands.py")
        self.assertEqual(band_frontier.METHOD_STYLE["GW"][0], "#E64B35")

    def test_a_legacy_png_path_lands_in_the_figure_directory(self) -> None:
        # Callers that still pass band_structure.png must not write a lone PNG
        # beside a figure set that no record can consume.
        legacy = self.root / "run" / "band_structure.png"
        report = render_band_figure(self.paths, legacy, occupied_bands=2)
        figure_dir = pathlib.Path(report["path"])
        self.assertTrue(figure_dir.is_dir())
        self.assertEqual(figure_dir.name, DEFAULT_FIGURE_NAME)
        self.assertTrue((figure_dir / "gw_frontier.svg").is_file())

    def test_scf_mesh_dots_mark_only_the_grid_coincident_path_points(self) -> None:
        # The fixture path is (0,0,0), (0.25,0,0), (0.5,0,0.5): all three sit on a
        # 4x4x4 Gamma-centred mesh (k*n integral), so all three carry mesh data and
        # all three must be dotted. An off-grid row would not be.
        (self.root / "KPT_scf").write_text(
            "K_POINTS\n0\nGamma\n4 4 4 0 0 0\n", encoding="utf-8"
        )
        target = self.root / "figure-dots" / DEFAULT_FIGURE_NAME
        report = render_band_figure(
            self.paths, target, occupied_bands=2, scf_kpt=self.root / "KPT_scf"
        )
        self.assertEqual(report["methods"]["GW"]["scf_grid_rows"], [1, 2, 3])
        self.assertEqual(report["methods"]["KS"]["scf_grid_rows"], [1, 2, 3])
        svg = (target / "gw_frontier.svg").read_text(encoding="utf-8")
        self.assertIn("GW-grid-dots", svg)

    def test_without_a_kpt_file_no_dots_are_claimed(self) -> None:
        target = self.root / "figure-nodots" / DEFAULT_FIGURE_NAME
        report = render_band_figure(self.paths, target, occupied_bands=2)
        self.assertIsNone(report["scf_grid"])
        self.assertEqual(report["methods"]["GW"]["scf_grid_rows"], [])
        svg = (target / "gw_frontier.svg").read_text(encoding="utf-8")
        self.assertNotIn("GW-grid-dots", svg)

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
