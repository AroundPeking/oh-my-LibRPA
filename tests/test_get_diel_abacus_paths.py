"""Regression tests for current and legacy ABACUS band-output locations."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


GET_DIEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "abacus-librpa-gw"
    / "template"
    / "get_diel.py"
)


def load_get_diel_module():
    spec = importlib.util.spec_from_file_location("get_diel_under_test", GET_DIEL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_minimal_case(root: Path, *, current_layout: bool) -> None:
    (root / "STRU").write_text(
        "LATTICE_VECTORS\n1 0 0\n0 1 0\n0 0 1\n", encoding="utf-8"
    )
    out_abacus = root / "OUT.ABACUS"
    out_abacus.mkdir()
    (out_abacus / "running_scf.log").write_text("E_FERMI = 1.25 eV\n", encoding="utf-8")
    band_text = "header\nheader\n4 1 1\nheader\nheader\n1 2.0 -1.0\n2 0.0 0.5\n"
    band_path = root / "OUT.librpa" / "band_out.txt" if current_layout else root / "band_out"
    band_path.parent.mkdir(parents=True, exist_ok=True)
    band_path.write_text(band_text, encoding="utf-8")


class GetDielAbacusPathTests(unittest.TestCase):
    def test_prefers_current_librpa_txt_band_output(self) -> None:
        module = load_get_diel_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_case(root, current_layout=True)
            _, fermi_energy, occupied, nstates = module.get_param(str(root))
        self.assertEqual(fermi_energy, 1.25)
        self.assertEqual(occupied, 1)
        self.assertEqual(nstates, 4)

    def test_accepts_legacy_root_band_output_as_fallback(self) -> None:
        module = load_get_diel_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_minimal_case(root, current_layout=False)
            _, _, occupied, nstates = module.get_param(str(root))
        self.assertEqual(occupied, 1)
        self.assertEqual(nstates, 4)


if __name__ == "__main__":
    unittest.main()
