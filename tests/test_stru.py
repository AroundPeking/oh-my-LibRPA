import unittest

from oml_mcp.stru import (
    StruError,
    atom_counts,
    rewrite_assets,
    sections,
    species,
    structure_fingerprint,
)


STRU = """ATOMIC_SPECIES
Ga 69.723 Ga.upf
N 14.007 N.upf

NUMERICAL_ORBITAL
Ga_gga_8au_100Ry_6s6p4d2f.orb
N_gga_8au_100Ry_3s3p2d.orb

LATTICE_CONSTANT
1.8897162

LATTICE_VECTORS
3.2 0.0 0.0
0.0 3.2 0.0
0.0 0.0 5.2

ATOMIC_POSITIONS
Direct
Ga
0.0
1
0.0 0.0 0.0 0 0 0

N
0.0
1
0.25 0.25 0.25 0 0 0
"""

STRU_REORDERED = STRU.replace(
    """Ga
0.0
1
0.0 0.0 0.0 0 0 0

N
0.0
1
0.25 0.25 0.25 0 0 0""",
    """N
0.0
1
0.25 0.25 0.25 0 0 0

Ga
0.0
1
0.0 0.0 0.0 0 0 0""",
)


class StruParseTest(unittest.TestCase):
    def test_sections_and_species(self):
        block = sections(STRU)
        self.assertIn("ATOMIC_SPECIES", block)
        self.assertEqual(species(STRU)[0], ("Ga", 69.723, "Ga.upf"))
        self.assertEqual(species(STRU)[1], ("N", 14.007, "N.upf"))

    def test_atom_counts(self):
        self.assertEqual(atom_counts(STRU), {"Ga": 1, "N": 1})

    def test_missing_positions_is_rejected(self):
        with self.assertRaises(StruError):
            atom_counts("ATOMIC_SPECIES\nGa 1 Ga.upf\n")


class StructureFingerprintTest(unittest.TestCase):
    def test_digest_is_stable_across_site_order(self):
        first, _ = structure_fingerprint(STRU, dimension="3d")
        second, _ = structure_fingerprint(STRU_REORDERED, dimension="3d")
        self.assertEqual(first, second)

    def test_digest_changes_with_the_cell(self):
        other = STRU.replace("3.2 0.0 0.0", "3.3 0.0 0.0")
        first, _ = structure_fingerprint(STRU, dimension="3d")
        second, _ = structure_fingerprint(other, dimension="3d")
        self.assertNotEqual(first, second)

    def test_digest_quantizes_sub_microangstrom_changes(self):
        nudged = STRU.replace("0.25 0.25 0.25 0 0 0", "0.250000001 0.25 0.25 0 0 0")
        first, _ = structure_fingerprint(STRU, dimension="3d")
        second, _ = structure_fingerprint(nudged, dimension="3d")
        self.assertEqual(first, second)

    def test_invalid_dimension_is_rejected(self):
        with self.assertRaises(StruError):
            structure_fingerprint(STRU, dimension="1d")


class StruRewriteTest(unittest.TestCase):
    def test_replaces_pp_nao_and_abf(self):
        text = STRU.rstrip("\n") + "\n\nABFS_ORBITAL\nGa_abfs.abfs\nN_abfs.abfs\n"
        rewritten = rewrite_assets(
            text,
            pp={"Ga": "Ga_new.upf"},
            nao={"N": "N_new.orb"},
            abfs={"Ga": "Ga_new.abfs", "N": "N_new.abfs"},
        )
        self.assertIn("Ga 69.723 Ga_new.upf", rewritten)
        self.assertIn("Ga_gga_8au_100Ry_6s6p4d2f.orb", rewritten)
        self.assertIn("N_new.orb", rewritten)
        self.assertIn("Ga_new.abfs", rewritten)
        self.assertIn("N_new.abfs", rewritten)

    def test_inserts_abfs_block_when_absent(self):
        rewritten = rewrite_assets(STRU, abfs={"Ga": "Ga.abfs", "N": "N.abfs"})
        self.assertIn("ABFS_ORBITAL\nGa.abfs\nN.abfs", rewritten)
        # The numerical orbital block is preserved.
        self.assertIn("Ga_gga_8au_100Ry_6s6p4d2f.orb", rewritten)

    def test_missing_numerical_orbital_block_is_rejected(self):
        text = STRU.replace("NUMERICAL_ORBITAL", "SOMETHING_ELSE")
        with self.assertRaises(StruError):
            rewrite_assets(text, nao={"Ga": "x.orb"})

    def test_incomplete_abfs_mapping_is_rejected(self):
        with self.assertRaises(StruError):
            rewrite_assets(STRU, abfs={"Ga": "Ga.abfs"})


if __name__ == "__main__":
    unittest.main()
