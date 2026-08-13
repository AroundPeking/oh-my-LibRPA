import math
import pathlib
import tempfile
import unittest


from oml_mcp.scientific_bands import (
    ScientificBandError,
    inspect_qpe_diagnostics,
    load_band_bundle,
    parse_band_table,
    select_insulating_window,
)


KPOINTS = ((0.0, 0.0, 0.0), (0.5, 0.0, 0.5))
OCCUPATIONS = (2.0, 2.0, 2.0, 2.0, 0.0, 0.0, 0.0, 0.0)
GW_ENERGIES = (
    (-5.0, -4.0, -3.0, -2.0, 1.0, 2.0, 3.0, 4.0),
    (-4.5, -3.5, -2.5, -1.5, -0.25, 1.8, 2.8, 3.8),
)


def write_table(
    path: pathlib.Path,
    energies=GW_ENERGIES,
    occupations=(OCCUPATIONS, OCCUPATIONS),
    kpoints=KPOINTS,
    order=(0, 1),
) -> None:
    rows = []
    for row_index in order:
        tokens = [
            str(row_index + 1),
            *(f"{value:.8f}" for value in kpoints[row_index]),
        ]
        for occupation, energy in zip(
            occupations[row_index], energies[row_index], strict=True
        ):
            tokens.extend((f"{occupation:.8f}", str(energy)))
        rows.append(" ".join(tokens))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_bundle(root: pathlib.Path) -> None:
    write_table(
        root / "KS_band_spin_1.dat",
        energies=tuple(tuple(value - 0.5 for value in row) for row in GW_ENERGIES),
    )
    write_table(
        root / "EXX_band_spin_1.dat",
        energies=tuple(tuple(value - 0.2 for value in row) for row in GW_ENERGIES),
        order=(1, 0),
    )
    write_table(root / "GW_band_spin_1.dat", order=(1, 0))


class ScientificBandTest(unittest.TestCase):
    def test_bundle_matches_periodic_kpoints_and_selects_vbm_cbm_window(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_bundle(root)

            bundle = load_band_bundle(root)
            window = select_insulating_window(bundle, occupied_value=2.0, padding=3)

        self.assertEqual(bundle["spins"], [1])
        self.assertEqual(bundle["nkpoints"], 2)
        self.assertEqual(bundle["nbands"], 8)
        self.assertEqual(window["vbm_band"], 4)
        self.assertEqual(window["cbm_band"], 5)
        self.assertEqual(window["band_start"], 1)
        self.assertEqual(window["band_stop"], 8)
        self.assertEqual(window["state_count"], 16)
        self.assertAlmostEqual(window["fundamental_gw_gap_ev"], 1.25)
        self.assertEqual(window["vbm_state"]["band"], 4)
        self.assertEqual(window["cbm_state"]["band"], 5)

    def test_band_table_rejects_duplicate_periodic_kpoints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "GW_band_spin_1.dat"
            write_table(
                path,
                kpoints=((0.5, 0.0, 0.5), (-0.5, 0.0, -0.5)),
            )

            with self.assertRaises(ScientificBandError) as raised:
                parse_band_table(path, quantity="gw")

        self.assertEqual(raised.exception.code, "DUPLICATE_KPOINT")

    def test_band_table_rejects_inconsistent_width_and_nonfinite_energy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            width = root / "width_spin_1.dat"
            write_table(width)
            lines = width.read_text(encoding="utf-8").splitlines()
            width.write_text(lines[0] + "\n" + " ".join(lines[1].split()[:-2]) + "\n")
            with self.assertRaises(ScientificBandError) as width_error:
                parse_band_table(width, quantity="gw")

            nonfinite = root / "nonfinite_spin_1.dat"
            energies = (GW_ENERGIES[0], (*GW_ENERGIES[1][:-1], math.nan))
            write_table(nonfinite, energies=energies)
            with self.assertRaises(ScientificBandError) as finite_error:
                parse_band_table(nonfinite, quantity="gw")

        self.assertEqual(width_error.exception.code, "TABLE_SHAPE_INVALID")
        self.assertEqual(finite_error.exception.code, "NONFINITE_BAND_VALUE")

    def test_bundle_rejects_mismatched_state_sets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_bundle(root)
            write_table(
                root / "EXX_band_spin_1.dat",
                energies=tuple(tuple(value - 0.2 for value in row) for row in GW_ENERGIES),
                kpoints=(KPOINTS[0], (0.25, 0.0, 0.25)),
            )

            with self.assertRaises(ScientificBandError) as raised:
                load_band_bundle(root)

        self.assertEqual(raised.exception.code, "STATE_SET_MISMATCH")

    def test_state_window_rejects_partial_or_k_dependent_occupations(self):
        with tempfile.TemporaryDirectory() as partial_tmp, tempfile.TemporaryDirectory() as count_tmp:
            partial = pathlib.Path(partial_tmp)
            write_bundle(partial)
            partial_occ = (
                OCCUPATIONS,
                (*OCCUPATIONS[:3], 1.0, *OCCUPATIONS[4:]),
            )
            write_table(partial / "KS_band_spin_1.dat", occupations=partial_occ)
            with self.assertRaises(ScientificBandError) as partial_error:
                select_insulating_window(load_band_bundle(partial))

            changing = pathlib.Path(count_tmp)
            write_bundle(changing)
            changing_occ = (
                OCCUPATIONS,
                (*OCCUPATIONS[:3], 0.0, *OCCUPATIONS[4:]),
            )
            write_table(changing / "KS_band_spin_1.dat", occupations=changing_occ)
            with self.assertRaises(ScientificBandError) as count_error:
                select_insulating_window(load_band_bundle(changing))

        self.assertEqual(partial_error.exception.code, "UNSUPPORTED_OCCUPATION_PATTERN")
        self.assertEqual(count_error.exception.code, "UNSUPPORTED_OCCUPATION_PATTERN")

    def test_qpe_diagnostics_preserve_file_and_line_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            (root / "LibRPA.1.out").write_text(
                "start\nQPE failed for spin 1 k-point 2 state 5\nlibRPA finished successfully\n",
                encoding="utf-8",
            )
            (root / "librpa_para_nprocs_1_myid_0.out").write_text(
                "invalid Pade continuation at state 4\n",
                encoding="utf-8",
            )

            report = inspect_qpe_diagnostics(root)

        self.assertFalse(report["accepted"])
        self.assertEqual(report["failure_count"], 2)
        self.assertEqual(report["failures"][0]["line"], 2)
        self.assertIn("QPE failed", report["failures"][0]["excerpt"])
        self.assertIn("Pade", report["failures"][1]["excerpt"])


if __name__ == "__main__":
    unittest.main()
