import pathlib
import tempfile
import unittest

from oml_mcp.orbital_info import (
    OrbitalInfoError,
    basis_dimension,
    parse_orbital_header,
)


COMPACT = """---------------------------------------------------------------------------
Element                     Te
Energy Cutoff(Ry)           100
Radius Cutoff(a.u.)         10
Lmax                        3
Number of Sorbital-->       3
Number of Porbital-->       3
Number of Dorbital-->       3
Number of Forbital-->       2
---------------------------------------------------------------------------
SUMMARY  END

Mesh                        1001
dr                          0.01
"""

BLOCK = """Element
Ca
Lmax
2
Number of radial functions for each angular momentum
3 2 1
Mesh
1001
dr
0.01
"""


class OrbitalInfoTest(unittest.TestCase):
    def _write(self, text: str) -> pathlib.Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = pathlib.Path(directory.name) / "test.orb"
        path.write_text(text, encoding="utf-8")
        return path

    def test_compact_header_dimension(self):
        header = parse_orbital_header(self._write(COMPACT))
        self.assertEqual(header.element, "Te")
        self.assertEqual(header.lmax, 3)
        self.assertEqual(header.radial_counts, {0: 3, 1: 3, 2: 3, 3: 2})
        self.assertEqual(header.mesh, 1001)
        self.assertAlmostEqual(header.dr, 0.01)
        # 3*1 + 3*3 + 3*5 + 2*7
        self.assertEqual(header.basis_dimension, 41)
        self.assertEqual(header.shell_summary(), "3s3p3d2f")

    def test_soc_doubles_the_basis_dimension(self):
        header = parse_orbital_header(self._write(COMPACT))
        self.assertEqual(header.basis_dimension_for(soc=False), 41)
        self.assertEqual(header.basis_dimension_for(soc=True), 82)

    def test_block_header_dimension(self):
        header = parse_orbital_header(self._write(BLOCK))
        self.assertEqual(header.element, "Ca")
        self.assertEqual(header.radial_counts, {0: 3, 1: 2, 2: 1})
        # 3*1 + 2*3 + 1*5
        self.assertEqual(header.basis_dimension, 14)

    def test_missing_counts_is_rejected(self):
        with self.assertRaises(OrbitalInfoError):
            parse_orbital_header(self._write("Element Te\nLmax 2\n"))

    def test_unknown_angular_letter_is_rejected(self):
        text = "Element Te\nNumber of Zorbital--> 2\n"
        with self.assertRaises(OrbitalInfoError):
            parse_orbital_header(self._write(text))

    def test_negative_count_is_rejected(self):
        text = "Element Te\nNumber of Sorbital--> -1\n"
        with self.assertRaises(OrbitalInfoError):
            parse_orbital_header(self._write(text))

    def test_basis_dimension_helper(self):
        path = self._write(COMPACT)
        self.assertEqual(basis_dimension(path), 41)
        self.assertEqual(basis_dimension(path, soc=True), 82)

    def test_missing_file_is_rejected(self):
        with self.assertRaises(OrbitalInfoError):
            parse_orbital_header("/nonexistent/file.orb")


if __name__ == "__main__":
    unittest.main()
