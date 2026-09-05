import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ACTIVE_ROOTS = (
    ROOT / "templates",
    ROOT / "rules",
    ROOT / "scripts",
    ROOT / "skills" / "abacus-librpa-gw",
    ROOT / "skills" / "oh-my-librpa",
    ROOT / "skills" / "oh-my-librpa-fhi-aims-g0w0-band",
    ROOT / "docs" / "guide",
    ROOT / "examples",
)
TEXT_SUFFIXES = frozenset({"", ".md", ".template", ".in", ".sh", ".yml", ".yaml"})


def active_files():
    for root in ACTIVE_ROOTS:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in TEXT_SUFFIXES and "__pycache__" not in path.parts:
                yield path


class ActiveDefaultsTest(unittest.TestCase):
    def test_version_guard_distinguishes_historical_and_current_profiles(self):
        text = (ROOT / "skills" / "abacus-librpa-version-guard" / "SKILL.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("abacus-master-ghj-librpa-0.7.0-pyatb-headwing-2026-08", text)
        self.assertIn("abacus-librpa-2026-08-30-v2", text)
        self.assertIn("641caa554b44c4db2743603e9c75c96379901d7c", text)
        self.assertIn("abacus-librpa-2026-08-30-v3", text)
        self.assertIn("81ff5f33995e7a545c2b9cb4f1a74490a74ecb4a", text)
        self.assertIn("abacus-librpa-2026-09-03-v4", text)
        self.assertIn("abacus-librpa-2026-09-06-v5", text)
        self.assertIn("abacus-librpa-2026-09-06-v6", text)
        self.assertIn("1648a8a344427ae1b6394912bf677c4a20e053f2", text)
        self.assertIn("current default", text)
        self.assertIn("v1_sternheimer_coulomb_iq_", text)
        self.assertIn("diagnostic only", text)
        self.assertIn("7e40c5bbf735a78aa15fa589ca2468fec2e2427b", text)
        self.assertIn("9fb9028c59b1dbaf9cf66965280961fc2225d9eb", text)
        self.assertIn("strict_2d_gw", text)
        self.assertIn("TESTABLE", text)
        self.assertIn("inspect_profile", text)

    def test_active_files_do_not_generate_deprecated_librpa_spellings(self):
        failures = []
        deprecated = re.compile(
            r"task\s*=\s*g0w0_band|(?:use_input|use_abacus)_(?:exx|gw|rpa)_symmetry\s*="
        )
        for path in active_files():
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if deprecated.search(line) and "deprecated" not in line.lower():
                    failures.append(f"{path.relative_to(ROOT)}:{line_number}:{line.strip()}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_abacus_librpa_templates_use_current_explicit_contract(self):
        template_paths = tuple((ROOT / "templates" / "abacus-librpa-gw").rglob("librpa.in*"))
        template_paths += tuple(
            (ROOT / "skills" / "oh-my-librpa" / "templates" / "abacus-librpa-gw").rglob(
                "librpa.in*"
            )
        )
        required = (
            "task = g0w0",
            "prefix_coul_full = v1_coulomb_full_iq_",
            "prefix_coul_cut = v1_coulomb_cut_iq_",
            "prefix_eigvecs_scf = KS_eigenvector",
            "prefix_lri_coeff = v1_Cs_data_",
            "fn_stru = stru_out",
            "fn_bz_sampling = bz_sampling_out",
            "fn_basis_wfc = basis_wfc_out",
            "fn_basis_aux = basis_aux_out",
            "fn_eigocc_scf = band_out",
            "fn_vxc_scf = vxc_out",
            "version_coul_reader = 1",
            "version_lri_reader = 1",
            "use_fullcoul_exx = f",
        )
        failures = []
        for path in template_paths:
            text = path.read_text(encoding="utf-8")
            missing = [item for item in required if item not in text]
            if missing:
                failures.append(f"{path.relative_to(ROOT)} missing {missing}")
        self.assertTrue(template_paths)
        self.assertEqual(failures, [], "\n".join(failures))

    def test_periodic_gw_templates_pin_the_current_continuation_baseline(self):
        template_paths = (
            ROOT / "templates" / "abacus-librpa-gw" / "minimal" / "librpa.in.template",
            ROOT / "templates" / "abacus-librpa-gw" / "template" / "librpa.in",
            ROOT
            / "skills"
            / "oh-my-librpa"
            / "templates"
            / "abacus-librpa-gw"
            / "minimal"
            / "librpa.in.template",
            ROOT
            / "skills"
            / "oh-my-librpa"
            / "templates"
            / "abacus-librpa-gw"
            / "template"
            / "librpa.in",
        )
        required = (
            "tfgrids_type = minimax",
            "nfreq = 24",
            "n_params_anacon = 6",
            "option_qpe_solver = 0",
            "use_qpe_adaptive_damp = f",
        )

        for path in template_paths:
            with self.subTest(path=path):
                text = path.read_text(encoding="utf-8")
                self.assertTrue(all(item in text for item in required))

    def test_molecular_gw_template_does_not_inherit_the_bn_pade_order(self):
        paths = (
            ROOT
            / "templates"
            / "abacus-librpa-gw"
            / "routes"
            / "molecule-gw-no-nscf-no-pyatb-no-shrink"
            / "librpa.in.template",
            ROOT
            / "skills"
            / "oh-my-librpa"
            / "templates"
            / "abacus-librpa-gw"
            / "routes"
            / "molecule-gw-no-nscf-no-pyatb-no-shrink"
            / "librpa.in.template",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertNotIn("n_params_anacon", path.read_text(encoding="utf-8"))

    def test_active_defaults_do_not_enable_full_coulomb_exx_implicitly(self):
        failures = []
        enabled = re.compile(r"use_fullcoul_exx\s*=\s*t\b", re.IGNORECASE)
        for path in active_files():
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if enabled.search(line) and "explicit" not in line.lower():
                    failures.append(f"{path.relative_to(ROOT)}:{line_number}:{line.strip()}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_shell_checker_accepts_current_task_and_keeps_deprecated_alias_detection(self):
        checker = (ROOT / "scripts" / "check_consistency.sh").read_text(encoding="utf-8")
        skill_checker = (
            ROOT / "skills" / "oh-my-librpa" / "scripts" / "check_consistency.sh"
        ).read_text(encoding="utf-8")
        intake = (ROOT / "scripts" / "intake_preflight.sh").read_text(encoding="utf-8")
        runner = (ROOT / "scripts" / "run_gw_workflow.sh").read_text(encoding="utf-8")
        self.assertIn('g0w0|g0w0_band) resolved_mode="gw"', checker)
        self.assertIn('g0w0|g0w0_band) resolved_mode="gw"', intake)
        self.assertIn('task_name="g0w0"', runner)
        self.assertIn("deprecated", checker.lower())
        for text in (checker, skill_checker):
            self.assertIn('get_value "$librpa" "tfgrids_type"', text)
            self.assertIn("obsolete singular key tfgrid_type", text)


if __name__ == "__main__":
    unittest.main()
