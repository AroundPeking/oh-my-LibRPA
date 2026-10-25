import pathlib
import unittest

from oml_mcp.parameter_knowledge import lookup
from oml_mcp.parameter_prescriptions import load_prescription
from oml_mcp.review import PRODUCTION_DEFAULTS


ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "abacus-librpa-gw" / "template"
SKILL_TEMPLATE = ROOT / "skills" / "oh-my-librpa" / "templates" / "abacus-librpa-gw"


def value(path: pathlib.Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        content = line.split("#", 1)[0].strip()
        if not content:
            continue
        if "=" in content:
            name, _, raw = content.partition("=")
            if name.strip() == key:
                return raw.strip()
        else:
            fields = content.split()
            if fields[:1] == [key] and len(fields) > 1:
                return fields[1]
    raise AssertionError(f"{key} not found in {path}")


def kpt_grid(path: pathlib.Path) -> list[int]:
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [int(token) for token in lines[-1].split()[:3]]


def files_under(root: pathlib.Path) -> dict[pathlib.Path, pathlib.Path]:
    return {
        path.relative_to(root): path
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }


class DefaultsConsistencyTest(unittest.TestCase):
    def test_only_one_3d_prescription_file(self):
        files = sorted(
            path.name
            for path in (ROOT / "oml_mcp" / "parameter_prescriptions").glob("periodic_3d_gw__*.json")
        )
        self.assertEqual(files, ["periodic_3d_gw__default.json"])

    def test_prescription_values(self):
        prescription = load_prescription("periodic_3d_gw", "default")
        parameters = prescription.parameters
        self.assertEqual(parameters["nfreq"].default, 16)
        self.assertEqual(parameters["nfreq"].target, 16)
        self.assertEqual(parameters["screening_kgrid"].target, [8, 8, 8])
        self.assertEqual(parameters["shrink_threshold"].target, 1e-3)
        self.assertEqual(parameters["exx_cs_inv_thr"].target, 1e-5)

    def test_template_matches_the_prescription_default(self):
        librpa = TEMPLATE / "librpa.in"
        scf = TEMPLATE / "INPUT_scf"
        self.assertEqual(int(value(librpa, "nfreq")), 16)
        self.assertEqual(int(value(librpa, "n_params_anacon")), -1)
        self.assertEqual(value(librpa, "use_qpe_adaptive_damp"), "t")
        self.assertEqual(float(value(librpa, "libri_exx_threshold_V")), 1e-2)
        self.assertEqual(kpt_grid(TEMPLATE / "KPT_scf"), [8, 8, 8])
        self.assertEqual(float(value(scf, "shrink_abfs_pca_thr")), 1e-4)
        self.assertEqual(float(value(scf, "shrink_lu_inv_thr")), 1e-3)
        self.assertEqual(int(value(scf, "ecutwfc")), 100)
        self.assertEqual(int(value(scf, "symmetry")), 1)
        self.assertEqual(float(value(scf, "exx_pca_threshold")), 10.0)
        self.assertEqual(value(librpa, "use_fullcoul_exx"), "t")
        self.assertEqual(value(librpa, "use_shrink_abfs"), "t")
        self.assertEqual(value(librpa, "use_symmetry_exx"), "t")
        self.assertEqual(value(librpa, "use_symmetry_gw"), "t")
        self.assertEqual(value(librpa, "replace_w_head"), "t")

    def test_review_defaults_match(self):
        self.assertEqual(PRODUCTION_DEFAULTS["nfreq"], 16)
        self.assertEqual(PRODUCTION_DEFAULTS["n_params_anacon"], -1)
        self.assertIs(PRODUCTION_DEFAULTS["use_qpe_adaptive_damp"], True)
        self.assertEqual(PRODUCTION_DEFAULTS["libri_exx_threshold_V"], 1e-2)
        self.assertEqual(PRODUCTION_DEFAULTS["shrink_abfs_pca_thr"], 1e-4)
        self.assertEqual(PRODUCTION_DEFAULTS["scf_kgrid"], [8, 8, 8])
        self.assertIs(PRODUCTION_DEFAULTS["use_fullcoul_exx"], True)

    def test_knowledge_defaults_match(self):
        self.assertEqual(lookup("nfreq")["parameter"]["default"], 16)
        self.assertEqual(lookup("n_params_anacon")["parameter"]["default"], -1)
        self.assertIs(lookup("use_qpe_adaptive_damp")["parameter"]["default"], True)
        self.assertEqual(lookup("scf_kgrid")["parameter"]["default"], [8, 8, 8])
        self.assertEqual(lookup("shrink_abfs_pca_thr")["parameter"]["default"], 1e-4)
        self.assertEqual(lookup("libri_exx_threshold_V")["parameter"]["default"], 0.01)

    def test_2d_has_one_gw_prescription_and_the_standard_grid(self):
        files = sorted(
            path.name
            for path in (ROOT / "oml_mcp" / "parameter_prescriptions").glob("strict_2d_gw__*.json")
        )
        self.assertEqual(files, ["strict_2d_gw__default.json"])
        prescription = load_prescription("strict_2d_gw", "default")
        self.assertEqual(prescription.parameters["in_plane_kgrid"].target, [12, 12])
        self.assertEqual(prescription.parameters["nfreq"].target, 16)
        self.assertEqual(prescription.parameters["vacuum"].target, 20.0)
        self.assertEqual(prescription.parameters["ewald_precision"].target, 1e-8)
        know = lookup("in_plane_kgrid")["parameter"]["default"]
        self.assertEqual(know, [12, 12, 1])

    def test_skill_template_copies_are_byte_identical(self):
        root = files_under(ROOT / "templates" / "abacus-librpa-gw")
        skill = files_under(SKILL_TEMPLATE)
        self.assertEqual(set(root), set(skill))
        for relative, path in root.items():
            with self.subTest(file=str(relative)):
                self.assertEqual(path.read_bytes(), skill[relative].read_bytes())

    def test_rule_card_copies_are_byte_identical(self):
        root = ROOT / "rules" / "cards" / "librpa-default-presets.yml"
        skill = ROOT / "skills" / "oh-my-librpa" / "rules" / "cards" / "librpa-default-presets.yml"
        self.assertEqual(root.read_bytes(), skill.read_bytes())


if __name__ == "__main__":
    unittest.main()
