import pathlib
import tempfile
import unittest


from oml_mcp.models import GateResult, ValidationReport
from oml_mcp.parsers import (
    ParseError,
    parse_abacus_input,
    parse_abacus_kpt,
    parse_band_out,
    parse_band_out_header,
    parse_bool,
    parse_bz_sampling,
    parse_k_path_info,
    parse_librpa_input,
    parse_vxc_out,
)


class InputParserTest(unittest.TestCase):
    def write(self, root: str, name: str, content: str) -> pathlib.Path:
        path = pathlib.Path(root) / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_abacus_kpt_parser_supports_mesh_line_and_explicit_modes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mesh = self.write(tmpdir, "KPT_mesh", "K_POINTS\n0\nGamma\n2 3 4 0 0.5 0\n")
            line = self.write(
                tmpdir,
                "KPT_line",
                "K_POINTS\n2\nLine\n0 0 0 3 # G\n0.5 0 0.5 1 # X\n",
            )
            direct = self.write(
                tmpdir,
                "KPT_direct",
                "K_POINTS\n2\nDirect\n0 0 0 0.5\n0.5 0 0.5 0.5\n",
            )

            mesh_data = parse_abacus_kpt(mesh)
            line_data = parse_abacus_kpt(line)
            direct_data = parse_abacus_kpt(direct)

        self.assertEqual(
            mesh_data,
            {
                "mode": "mesh",
                "scheme": "gamma",
                "grid": [2, 3, 4],
                "offset": [0.0, 0.5, 0.0],
            },
        )
        self.assertEqual(line_data["mode"], "path")
        self.assertEqual(line_data["segments"], [3, 1])
        self.assertEqual(line_data["points"][1], [0.5, 0.0, 0.5])
        self.assertEqual(direct_data["mode"], "explicit")
        self.assertEqual(direct_data["weights"], [0.5, 0.5])

    def test_abacus_kpt_parser_rejects_count_and_mode_errors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_count = self.write(
                tmpdir,
                "KPT_bad_count",
                "K_POINTS\n2\nDirect\n0 0 0 1\n",
            )
            bad_mode = self.write(
                tmpdir, "KPT_bad_mode", "K_POINTS\n0\nUnknown\n1 1 1\n"
            )

            with self.assertRaisesRegex(ParseError, "row count"):
                parse_abacus_kpt(bad_count)
            with self.assertRaisesRegex(ParseError, "unsupported KPT mode"):
                parse_abacus_kpt(bad_mode)

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

    def test_complete_band_out_is_parsed_and_truncation_is_rejected(self):
        body = """2
1
2
2
0.25
1 1
1 2.0 -0.5 -13.6
2 0.0 0.2 5.4
2 1
1 2.0 -0.4 -10.9
2 0.0 0.3 8.2
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid = self.write(tmpdir, "band_out", body)
            truncated = self.write(tmpdir, "band_out.bad", "\n".join(body.splitlines()[:-1]))

            parsed = parse_band_out(valid)
            with self.assertRaisesRegex(ParseError, "token count"):
                parse_band_out(truncated)

        self.assertEqual(parsed["nbasis"], 2)
        self.assertEqual(parsed["fermi_energy"], 0.25)

    def test_k_path_info_rejects_duplicate_and_nonfinite_kpoints(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            duplicate = self.write(
                tmpdir,
                "k_path_info.duplicate",
                "2 2 1 2\n0.0 0.0 0.0\n0.0 0.0 0.0\n",
            )
            nonfinite = self.write(
                tmpdir,
                "k_path_info.nonfinite",
                "2 2 1 1\nnan 0.0 0.0\n",
            )
            extra_column = self.write(
                tmpdir,
                "k_path_info.extra",
                "2 2 1 1\n0.0 0.0 0.0 7\n",
            )
            wrapped_duplicate = self.write(
                tmpdir,
                "k_path_info.wrapped-duplicate",
                "2 2 1 2\n0.0 0.0 0.0\n1.0 0.0 0.0\n",
            )

            with self.assertRaisesRegex(ParseError, "duplicate"):
                parse_k_path_info(duplicate)
            with self.assertRaisesRegex(ParseError, "finite"):
                parse_k_path_info(nonfinite)
            with self.assertRaisesRegex(ParseError, "invalid k-point"):
                parse_k_path_info(extra_column)
            with self.assertRaisesRegex(ParseError, "duplicate periodic"):
                parse_k_path_info(wrapped_duplicate)

    def test_bz_sampling_is_fully_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            valid = self.write(
                tmpdir,
                "bz_sampling_out",
                "1 1 2\n2 1\n1 0.5 0 0 0 0 0 0 1 1\n2 0.5 0 0 0.5 0 0 0.5 1 1\n",
            )
            invalid = self.write(
                tmpdir,
                "bz_sampling_out.bad",
                "1 1 2\n2 1\n1 0.4 0 0 0 0 0 0 1 1\n2 0.4 0 0 0.5 0 0 0.5 1 1\n",
            )

            parsed = parse_bz_sampling(valid)
            with self.assertRaisesRegex(ParseError, "weights"):
                parse_bz_sampling(invalid)

        self.assertEqual(parsed["nk_scf"], 2)
        self.assertEqual(parsed["nk_ibz"], 1)

    def test_vxc_out_is_fully_parsed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            valid = self.write(tmpdir, "vxc_out", "1\n1\n2\n-0.4 -10.9\n-0.2 -5.4\n")
            truncated = self.write(tmpdir, "vxc_out.bad", "1\n1\n2\n-0.4 -10.9\n")

            parsed = parse_vxc_out(valid)
            with self.assertRaisesRegex(ParseError, "token count"):
                parse_vxc_out(truncated)

        self.assertEqual(parsed["nstates"], 2)

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
