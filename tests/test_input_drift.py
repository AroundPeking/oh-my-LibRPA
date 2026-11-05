"""In-place parameter drift must be visible before the next stage is submitted."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest

from oml_mcp.input_drift import InputDriftError, check_run_inputs


def write_manifest(root: pathlib.Path, files: dict[str, str]) -> None:
    entries = []
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        entries.append(
            {"path": relative, "sha256": hashlib.sha256(content.encode()).hexdigest()}
        )
    meta = root / ".oml"
    meta.mkdir(exist_ok=True)
    (meta / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "run_id": "run-x", "files": entries}), encoding="utf-8"
    )


class InputDriftTest(unittest.TestCase):
    def test_clean_run_reports_no_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_manifest(root, {"librpa.in": "nfreq = 16\n", "INPUT_scf": "symmetry -1\n"})
            report = check_run_inputs(root)
        self.assertFalse(report["drifted"])
        self.assertEqual(report["changed"], [])

    def test_edited_parameter_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_manifest(root, {"librpa.in": "nfreq = 16\n", "INPUT_scf": "symmetry -1\n"})
            (root / "librpa.in").write_text("nfreq = 24\n", encoding="utf-8")
            report = check_run_inputs(root)
        self.assertTrue(report["drifted"])
        self.assertEqual(report["changed"][0]["path"], "librpa.in")
        self.assertNotEqual(report["changed"][0]["manifest"], report["changed"][0]["actual"])

    def test_missing_manifest_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(InputDriftError):
                check_run_inputs(pathlib.Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
