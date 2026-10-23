import math
import csv
import json
import pathlib
import struct
import tempfile
import unittest

import numpy as np

from oml_mcp.band_unfolding import (
    apply_translation,
    build_overlap_k,
    folded_primitive_points,
    primitive_translation_maps,
    projector_weight,
    projector_weights,
    read_abacus_wfc_binary,
    read_kpt_info_direct,
    read_stru_positions,
    resolve_abacus_wfc_binary,
    unfold_path,
)


class FoldedPrimitivePointTest(unittest.TestCase):
    def test_inverse_fold_contains_requested_primitive_point(self):
        primitive_k = np.array([0.375, 0.375, 0.75])
        factors = np.array([2, 2, 2])
        supercell_k = np.mod(factors * primitive_k, 1.0)

        folded = folded_primitive_points(supercell_k, factors)

        self.assertEqual(len(folded), 8)
        self.assertTrue(
            any(np.allclose(point, primitive_k) for _, point in folded)
        )

    def test_rejects_invalid_diagonal_factors(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            folded_primitive_points([0.0, 0.0, 0.0], [2, 0, 2])


class TranslationProjectorTest(unittest.TestCase):
    def setUp(self):
        self.positions = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0]])
        self.species = ["C", "C"]
        self.factors = np.array([2, 1, 1])
        self.maps = primitive_translation_maps(
            self.positions,
            self.species,
            self.factors,
        )

    def test_translation_maps_are_structure_derived_atom_permutations(self):
        mapping = next(
            item for item in self.maps if item.translation == (1, 0, 0)
        )

        np.testing.assert_array_equal(mapping.target_atoms, [1, 0])
        np.testing.assert_array_equal(
            mapping.cell_shifts,
            [[0, 0, 0], [1, 0, 0]],
        )

    def test_translation_wraps_with_supercell_bloch_phase(self):
        mapping = next(
            item for item in self.maps if item.translation == (1, 0, 0)
        )
        supercell_k = np.array([0.2, 0.0, 0.0])
        coefficients = np.array([1.0 + 0.0j, 0.0 + 0.0j])

        translated_once = apply_translation(
            coefficients,
            mapping,
            supercell_k,
            orbitals_per_atom=1,
        )
        translated_twice = apply_translation(
            translated_once,
            mapping,
            supercell_k,
            orbitals_per_atom=1,
        )

        expected = np.exp(-2j * math.pi * supercell_k[0]) * coefficients
        np.testing.assert_allclose(translated_twice, expected, atol=1.0e-13)

    def test_nonorthogonal_projector_selects_one_folded_sector(self):
        supercell_k = np.array([0.2, 0.0, 0.0])
        primitive_k = np.array([0.1, 0.0, 0.0])
        coefficients = np.array(
            [1.0, np.exp(2j * math.pi * primitive_k[0])],
            dtype=np.complex128,
        )
        overlap = np.array(
            [[1.2, 0.15 + 0.05j], [0.15 - 0.05j, 0.9]],
            dtype=np.complex128,
        )

        selected = projector_weight(
            coefficients,
            overlap,
            supercell_k,
            primitive_k,
            self.maps,
            orbitals_per_atom=1,
        )
        rejected = projector_weight(
            coefficients,
            overlap,
            supercell_k,
            [0.6, 0.0, 0.0],
            self.maps,
            orbitals_per_atom=1,
        )

        self.assertAlmostEqual(selected, 1.0, places=12)
        self.assertAlmostEqual(rejected, 0.0, places=12)

    def test_folded_sector_weights_sum_to_one(self):
        supercell_k = np.array([0.2, 0.0, 0.0])
        coefficients = np.array(
            [
                [1.0, 0.3 + 0.2j],
                [-0.1j, 0.8],
            ],
            dtype=np.complex128,
        )
        overlap = np.eye(2, dtype=np.complex128)
        sectors = folded_primitive_points(supercell_k, self.factors)

        weights = projector_weights(
            coefficients,
            overlap,
            supercell_k,
            [point for _, point in sectors],
            self.maps,
            orbitals_per_atom=1,
        )

        np.testing.assert_allclose(weights.sum(axis=1), 1.0, atol=1.0e-12)

    def test_nonperiodic_structure_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "candidates"):
            primitive_translation_maps(
                [[0.0, 0.0, 0.0], [0.49, 0.0, 0.0]],
                ["C", "C"],
                self.factors,
            )


class AbacusInputTest(unittest.TestCase):
    def test_zero_nnz_csr_record_and_abacus_positive_fourier_phase(self):
        content = """STEP: 0
Matrix Dimension of S(R): 2
Matrix number of S(R): 3
-1 0 0 1
 2.5000000000000000e-01
 1
 0 1 1
0 0 0 2
 1.0000000000000000e+00 1.0000000000000000e+00
 0 1
 0 1 2
2 0 0 0
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "srs1_nao.csr"
            path.write_text(content, encoding="ascii")

            overlap = build_overlap_k(path, [0.25, 0.0, 0.0])

        expected = np.array(
            [[1.0, 0.25 * np.exp(-0.5j * math.pi)], [0.0, 1.0]],
            dtype=np.complex128,
        )
        np.testing.assert_allclose(overlap, expected)

    def test_reads_complex_lcao_wavefunction_binary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "wfs1k1_nao.dat"
            write_wavefunction(
                path,
                supercell_k=[0.25, 0.0, 0.5],
                eigenvalues_ry=[-0.5],
                occupations=[2.0],
                coefficients=[[1.0 + 2.0j, 3.0 + 4.0j]],
            )

            supercell_k, eigenvalues, occupations, coefficients = (
                read_abacus_wfc_binary(path)
            )

        np.testing.assert_allclose(supercell_k, [0.25, 0.0, 0.5])
        np.testing.assert_allclose(eigenvalues, [-0.5])
        np.testing.assert_allclose(occupations, [2.0])
        np.testing.assert_allclose(
            coefficients,
            [[1.0 + 2.0j, 3.0 + 4.0j]],
        )

    def test_resolves_current_or_legacy_wavefunction_name_but_not_both(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            legacy = root / "wfk3_nao.dat"
            legacy.write_bytes(b"x")
            self.assertEqual(resolve_abacus_wfc_binary(root, 3), legacy)

            (root / "wfs1k3_nao.dat").write_bytes(b"x")
            with self.assertRaisesRegex(FileNotFoundError, "expected one"):
                resolve_abacus_wfc_binary(root, 3)

    def test_reads_direct_kpoints_and_rejects_cartesian_stru(self):
        kpt_content = """K-POINTS DIRECT COORDINATES
KPOINTS DIRECT_X DIRECT_Y DIRECT_Z WEIGHT
1 0.00000000 0.00000000 0.00000000 1.0000
2 0.05000000 0.00000000 0.05000000 1.0000
"""
        stru_content = """ATOMIC_POSITIONS
Cartesian
C
0.0
1
0.0 0.0 0.0
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            kpt = root / "KPT.info"
            stru = root / "STRU"
            kpt.write_text(kpt_content, encoding="ascii")
            stru.write_text(stru_content, encoding="ascii")

            points = read_kpt_info_direct(kpt)
            with self.assertRaisesRegex(ValueError, "Direct"):
                read_stru_positions(stru)

            cartesian_kpt = root / "KPT_cartesian.info"
            cartesian_kpt.write_text(
                """K-POINTS CARTESIAN COORDINATES
KPOINTS CARTESIAN_X CARTESIAN_Y CARTESIAN_Z WEIGHT
1 0.00000000 0.00000000 0.00000000 1.0000
""",
                encoding="ascii",
            )
            with self.assertRaisesRegex(ValueError, "Direct"):
                read_kpt_info_direct(cartesian_kpt)

        np.testing.assert_allclose(
            points,
            [[0.0, 0.0, 0.0], [0.05, 0.0, 0.05]],
        )


def write_wavefunction(
    path,
    *,
    supercell_k,
    eigenvalues_ry,
    occupations,
    coefficients,
):
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    with pathlib.Path(path).open("wb") as handle:
        handle.write(struct.pack("=i", 1))
        np.asarray(supercell_k, dtype=np.float64).tofile(handle)
        handle.write(struct.pack("=i", len(eigenvalues_ry)))
        handle.write(struct.pack("=i", coefficients.shape[1]))
        for band, (energy, occupation, row) in enumerate(
            zip(eigenvalues_ry, occupations, coefficients, strict=True),
            start=1,
        ):
            handle.write(struct.pack("=i", band))
            np.asarray([energy, occupation], dtype=np.float64).tofile(handle)
            interleaved = np.empty(2 * len(row), dtype=np.float64)
            interleaved[0::2] = row.real
            interleaved[1::2] = row.imag
            interleaved.tofile(handle)


class UnfoldPathTest(unittest.TestCase):
    def test_writes_target_sector_weights_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            wfc_dir = root / "wfc"
            wfc_dir.mkdir()
            stru = root / "STRU"
            kpt_info = wfc_dir / "KPT.info"
            overlap = root / "srs1_nao.csr"
            path_table = root / "path.csv"
            output = root / "weights.csv"
            summary_path = root / "summary.json"

            stru.write_text(
                """ATOMIC_POSITIONS
Direct
C
0.0
2
0.0 0.0 0.0
0.5 0.0 0.0
""",
                encoding="ascii",
            )
            kpt_info.write_text(
                """K-POINTS DIRECT COORDINATES
KPOINTS DIRECT_X DIRECT_Y DIRECT_Z WEIGHT
1 0.20000000 0.00000000 0.00000000 1.0000
""",
                encoding="ascii",
            )
            overlap.write_text(
                """STEP: 0
Matrix Dimension of S(R): 2
Matrix number of S(R): 1
0 0 0 2
 1.0 1.0
 0 1
 0 1 2
""",
                encoding="ascii",
            )
            with path_table.open("w", newline="", encoding="ascii") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "distance",
                        "kx",
                        "ky",
                        "kz",
                        "Kx",
                        "Ky",
                        "Kz",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "distance": 0.0,
                        "kx": 0.1,
                        "ky": 0.0,
                        "kz": 0.0,
                        "Kx": 0.2,
                        "Ky": 0.0,
                        "Kz": 0.0,
                    }
                )
            coefficients = np.array(
                [[1.0, np.exp(2j * math.pi * 0.1)]],
                dtype=np.complex128,
            ) / math.sqrt(2.0)
            write_wavefunction(
                wfc_dir / "wfs1k1_nao.dat",
                supercell_k=[0.2, 0.0, 0.0],
                eigenvalues_ry=[-0.5],
                occupations=[2.0],
                coefficients=coefficients,
            )

            summary = unfold_path(
                path_table=path_table,
                stru=stru,
                overlap=overlap,
                wfc_dir=wfc_dir,
                factors=(2, 1, 1),
                orbitals_per_atom=1,
                output=output,
                summary=summary_path,
            )
            with output.open(encoding="ascii") as handle:
                rows = list(csv.DictReader(handle))
            stored_summary = json.loads(summary_path.read_text(encoding="ascii"))

        self.assertEqual(summary["n_path_points"], 1)
        self.assertEqual(summary["n_bands"], 1)
        self.assertAlmostEqual(float(rows[0]["target_weight"]), 1.0, places=12)
        self.assertAlmostEqual(summary["max_sector_sum_error"], 0.0, places=12)
        self.assertEqual(stored_summary, summary)

    def test_rejects_unsupported_spin_soc_and_equal_nao_contract(self):
        common = {
            "path_table": "path.csv",
            "stru": "STRU",
            "overlap": "srs1_nao.csr",
            "wfc_dir": "wfc",
            "factors": (2, 1, 1),
            "orbitals_per_atom": 1,
            "output": "weights.csv",
            "summary": "summary.json",
        }

        with self.assertRaisesRegex(ValueError, "nspin=1"):
            unfold_path(**common, nspin=2)
        with self.assertRaisesRegex(ValueError, "SOC"):
            unfold_path(**common, lspinorb=True)
        with self.assertRaisesRegex(ValueError, "orbitals_per_atom"):
            unfold_path(**{**common, "orbitals_per_atom": 0})

    def test_rejects_multispecies_basis_without_per_atom_nao_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            path_table = root / "path.csv"
            with path_table.open("w", newline="", encoding="ascii") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=(
                        "distance",
                        "kx",
                        "ky",
                        "kz",
                        "Kx",
                        "Ky",
                        "Kz",
                    ),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "distance": 0.0,
                        "kx": 0.0,
                        "ky": 0.0,
                        "kz": 0.0,
                        "Kx": 0.0,
                        "Ky": 0.0,
                        "Kz": 0.0,
                    }
                )
            stru = root / "STRU"
            stru.write_text(
                """ATOMIC_POSITIONS
Direct
C
0.0
1
0.0 0.0 0.0
Si
0.0
1
0.5 0.5 0.5
""",
                encoding="ascii",
            )

            with self.assertRaisesRegex(ValueError, "single-species"):
                unfold_path(
                    path_table=path_table,
                    stru=stru,
                    overlap=root / "missing.csr",
                    wfc_dir=root / "missing-wfc",
                    factors=(1, 1, 1),
                    orbitals_per_atom=1,
                    output=root / "weights.csv",
                    summary=root / "summary.json",
                )


if __name__ == "__main__":
    unittest.main()
