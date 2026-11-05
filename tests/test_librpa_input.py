import tempfile
import unittest
from pathlib import Path

from oml_mcp.librpa_input import audit_librpa_in


def _write(directory: Path, text: str, name: str = "librpa.in") -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


class LibrpaInputAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_3d_input_passes(self):
        path = _write(
            self.root,
            "task = g0w0\nnfreq = 16\noption_dielect_func = 3\n"
            "use_fullcoul_wc = f\ncs_threshold = 0\n",
        )
        report = audit_librpa_in(path, dimension="3d", require_cs_threshold=True)
        self.assertTrue(report.ok, [f.to_dict() for f in report.findings])
        self.assertEqual(report.findings[0].status, "PASS")

    def test_dump_alias_is_rejected(self):
        path = _write(
            self.root,
            "task = g0w0\nnfreq = 16\noption_dielect_func = 3\n"
            "use_fullcoul_wc = f\ncs_R_threshold = 0\n",
        )
        report = audit_librpa_in(path, dimension="3d", require_cs_threshold=True)
        self.assertFalse(report.ok)
        gate_ids = [f.gate_id for f in report.findings]
        self.assertIn("librpa.input.dump_alias", gate_ids)
        self.assertIn("librpa.input.cs_threshold", gate_ids)

    def test_dump_header_is_rejected(self):
        path = _write(
            self.root,
            "Begin driver parameters\n"
            "task = g0w0\ncs_threshold = 0\noption_dielect_func = 3\n"
            "End control parameters\n",
        )
        report = audit_librpa_in(path, dimension="3d")
        self.assertFalse(report.ok)
        self.assertIn("librpa.input.dump_shape", [f.gate_id for f in report.findings])

    def test_duplicate_keys_are_rejected(self):
        path = _write(self.root, "task = g0w0\ntask = exx\n")
        report = audit_librpa_in(path, dimension="3d")
        self.assertFalse(report.ok)
        self.assertIn("librpa.input.duplicates", [f.gate_id for f in report.findings])

    def test_3d_input_rejects_strict2d_switches(self):
        path = _write(
            self.root,
            "task = g0w0\noption_dielect_func = 4\nuse_fullcoul_wc = t\n",
        )
        report = audit_librpa_in(path, dimension="3d")
        self.assertFalse(report.ok)
        self.assertIn("librpa.input.dielect", [f.gate_id for f in report.findings])

    def test_strict2d_input_passes_only_with_the_full_contract(self):
        complete = _write(
            self.root,
            "task = g0w0\noption_dielect_func = 4\nuse_fullcoul_wc = t\n"
            "use_2d_dielectric = t\nrpa_headwing_mode = qavg\n",
            "complete.in",
        )
        self.assertTrue(audit_librpa_in(complete, dimension="2d").ok)
        partial = _write(
            self.root,
            "task = g0w0\noption_dielect_func = 4\nuse_fullcoul_wc = t\n",
            "partial.in",
        )
        self.assertFalse(audit_librpa_in(partial, dimension="2d").ok)

    def test_missing_cs_threshold_only_fails_when_required(self):
        path = _write(self.root, "task = g0w0\noption_dielect_func = 3\n")
        self.assertTrue(audit_librpa_in(path, dimension="3d").ok)
        report = audit_librpa_in(path, dimension="3d", require_cs_threshold=True)
        self.assertFalse(report.ok)
        self.assertIn("librpa.input.cs_threshold", [f.gate_id for f in report.findings])

    def test_frequency_points_must_match_nfreq(self):
        librpa = _write(self.root, "task = g0w0\nnfreq = 6\noption_dielect_func = 3\n")
        control = self.root / "control.in"
        control.write_text("frequency_points 16\n", encoding="utf-8")
        report = audit_librpa_in(librpa, dimension="3d", control_in=control)
        self.assertFalse(report.ok)
        self.assertIn("librpa.input.frequency_pair", [f.gate_id for f in report.findings])


if __name__ == "__main__":
    unittest.main()


class RegularizationEchoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_echo_must_match_the_input(self):
        from oml_mcp.librpa_input import check_regularization_echo

        librpa = _write(self.root, "task = g0w0\nregularization = 1e-12\n")
        log = self.root / "LibRPA.1.out"
        log.write_text(
            "Begin driver parameters\nregularization = 1e-12\nEnd control parameters\n",
            encoding="utf-8",
        )
        self.assertEqual(check_regularization_echo(librpa, (log,)).status, "PASS")
        log.write_text(
            "Begin driver parameters\nregularization = 0\nEnd control parameters\n",
            encoding="utf-8",
        )
        self.assertEqual(check_regularization_echo(librpa, (log,)).status, "FAIL")

    def test_missing_line_in_a_dump_fails(self):
        from oml_mcp.librpa_input import check_regularization_echo

        librpa = _write(self.root, "task = g0w0\nregularization = 1e-12\n")
        log = self.root / "LibRPA.1.out"
        log.write_text(
            "Begin driver parameters\nnfreq = 16\nEnd control parameters\n",
            encoding="utf-8",
        )
        finding = check_regularization_echo(librpa, (log,))
        self.assertEqual(finding.status, "FAIL")
        self.assertIn("may ignore", finding.message)

    def test_regularization_value_is_validated(self):
        negative = _write(self.root, "task = g0w0\nregularization = -1e-12\n", "negative.in")
        self.assertFalse(audit_librpa_in(negative, dimension="3d").ok)
        deviating = _write(self.root, "task = g0w0\nregularization = 1e-13\n", "deviate.in")
        report = audit_librpa_in(deviating, dimension="3d")
        self.assertTrue(report.ok)
        self.assertIn("librpa.input.penalty", [f.gate_id for f in report.findings])
