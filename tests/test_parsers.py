import pathlib
import tempfile
import unittest


from oml_mcp.models import GateResult, ValidationReport
from oml_mcp.parsers import (
    ParseError,
    parse_abacus_input,
    parse_band_out_header,
    parse_bool,
    parse_k_path_info,
    parse_librpa_input,
)


class InputParserTest(unittest.TestCase):
    def write(self, root: str, name: str, content: str) -> pathlib.Path:
        path = pathlib.Path(root) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_abacus_parser_keeps_values_lines_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write(
                tmpdir,
                "INPUT_scf",
                """INPUT_PARAMETERS
# comment
basis_type lcao
rpa 1 # inline
symmetry 1
symmetry -1
""",
            )

            document = parse_abacus_input(path)

        self.assertEqual(document.syntax, "abacus")
        self.assertEqual(document.value("basis_type"), "lcao")
        self.assertEqual(document.value("rpa"), "1")
        self.assertEqual(document.value("symmetry"), "-1")
        self.assertEqual(document.lines("symmetry"), (5, 6))
        self.assertEqual(document.duplicates, ("symmetry",))

    def test_librpa_parser_requires_equals_and_strips_comments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write(
                tmpdir,
                "librpa.in",
                """task = g0w0
version_coul_reader = 1 # binary v1
use_symmetry_gw = t
""",
            )

            document = parse_librpa_input(path)

        self.assertEqual(document.syntax, "librpa")
        self.assertEqual(document.value("task"), "g0w0")
        self.assertEqual(document.value("version_coul_reader"), "1")
        self.assertTrue(parse_bool(document.value("use_symmetry_gw")))

    def test_librpa_parser_rejects_non_assignment_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self.write(tmpdir, "librpa.in", "task g0w0\n")
            with self.assertRaisesRegex(ParseError, "line 1"):
                parse_librpa_input(path)

    def test_boolean_parser_accepts_program_spellings_and_rejects_unknown(self):
        for value in ("t", "true", "1", "yes", "on"):
            self.assertTrue(parse_bool(value))
        for value in ("f", "false", "0", "no", "off"):
            self.assertFalse(parse_bool(value))
        with self.assertRaisesRegex(ParseError, "boolean"):
            parse_bool("maybe")

    def test_missing_input_file_is_reported(self):
        with self.assertRaisesRegex(ParseError, "not found"):
            parse_abacus_input("/definitely/missing/INPUT")

    def test_k_path_info_and_band_out_headers_are_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kpath = self.write(
                tmpdir,
                "k_path_info",
                "2 3 1 2\n0.0 0.0 0.0\n0.5 0.0 0.0\n",
            )
            band = self.write(tmpdir, "band_out", "2\n1\n3\n")

            info = parse_k_path_info(kpath)
            dims = parse_band_out_header(band)

        self.assertEqual(info["nbasis"], 2)
        self.assertEqual(info["nstates"], 3)
        self.assertEqual(info["nspin"], 1)
        self.assertEqual(info["nkpoints"], 2)
        self.assertEqual(info["kpoints"], ((0.0, 0.0, 0.0), (0.5, 0.0, 0.0)))
        self.assertEqual(dims, {"nkpoints": 2, "nspin": 1, "nstates": 3})

    def test_structured_reports_are_json_compatible(self):
        report = ValidationReport(
            profile_id="profile",
            gates=(
                GateResult(
                    gate_id="reader",
                    status="FAIL",
                    message="reader mismatch",
                    evidence=("INPUT:4",),
                    repair="set reader to 1",
                ),
            ),
        )

        self.assertFalse(report.accepted)
        self.assertEqual(report.to_dict()["gates"][0]["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
