import json
import pathlib
import tempfile
import unittest


from oml_mcp.provenance import sha256_file
from oml_mcp.scientific_definition import (
    ScientificDefinitionError,
    build_definition_signature,
    compare_definitions,
)


REVISIONS = {
    "abacus": "a" * 40,
    "librpa": "b" * 40,
    "pyatb": "c" * 40,
}


def write_run(
    root: pathlib.Path,
    *,
    nfreq: int = 6,
    nbands: int = 8,
    grid=(2, 2, 2),
    n_params_anacon: int = 6,
    option_qpe_solver: int = 0,
    use_symmetry: bool = True,
) -> None:
    oml = root / ".oml"
    oml.mkdir(parents=True)
    (root / "INPUT_scf").write_text(
        "\n".join(
            (
                "INPUT_PARAMETERS",
                "basis_type lcao",
                "rpa 1",
                f"nbands {nbands}",
                "nspin 1",
                "ecutwfc 100",
                "smearing_method gaussian",
                "smearing_sigma 1e-4",
                f"symmetry {1 if use_symmetry else -1}",
                "shrink_abfs_pca_thr 1e-1",
                "shrink_lu_inv_thr 1e-3",
                "exx_pca_threshold 1e-3",
                "out_librpa_reader_version 1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "INPUT_nscf").write_text(
        f"INPUT_PARAMETERS\nnbands {nbands}\nnspin 1\necutwfc 100\nsymmetry -1\n",
        encoding="utf-8",
    )
    (root / "KPT_scf").write_text(
        f"K_POINTS\n0\nGamma\n{grid[0]} {grid[1]} {grid[2]} 0 0 0\n",
        encoding="utf-8",
    )
    (root / "KPT_nscf").write_text(
        "K_POINTS\n2\nLine\n0 0 0 2\n0.5 0 0.5 1\n",
        encoding="utf-8",
    )
    (root / "librpa.in").write_text(
        "\n".join(
            (
                "task = g0w0",
                "tfgrids_type = minimax",
                f"nfreq = {nfreq}",
                "tfgrids_freq_min = 0.005",
                "tfgrids_freq_interval = 0",
                "tfgrids_freq_max = 1000",
                "tfgrids_time_min = 0.005",
                "tfgrids_time_interval = 0",
                "minimax_emin = -1",
                "minimax_emax = -1",
                "minimax_regulation = 0",
                f"n_params_anacon = {n_params_anacon}",
                "n_params_anacon_resample = -1",
                "anacon_nfreq = -1",
                f"option_qpe_solver = {option_qpe_solver}",
                "qpe_solver_thres = 1e-6",
                "qpe_solver_n_iter_max = 10000",
                "qpe_solver_damp_factor = 0.1",
                "use_qpe_adaptive_damp = f",
                "use_qpe_legacy_update = f",
                "override_qpe_solver_nan = f",
                "use_hedin_shift = f",
                "istate_ref_hedin_shift = -1",
                "n_bands_chi0 = -1",
                "n_bands_sigc = -1",
                "option_dielect_func = 3",
                "replace_w_head = t",
                "use_fullcoul_exx = f",
                "use_shrink_abfs = t",
                "use_shrink_chi = t",
                f"use_symmetry_exx = {'t' if use_symmetry else 'f'}",
                f"use_symmetry_gw = {'t' if use_symmetry else 'f'}",
                "use_soc = 0",
                "version_coul_reader = 1",
                "version_lri_reader = 1",
                "sqrt_coulomb_threshold = 0",
                "libri_chi0_threshold_C = 1e-4",
                "libri_chi0_threshold_G = 1e-5",
                "libri_g0w0_threshold_C = 1e-5",
                "libri_g0w0_threshold_G = 1e-5",
                "libri_g0w0_threshold_Wc = 1e-6",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for name, content in (
        ("STRU", "ATOMIC_SPECIES\nSi 28 Si.upf\n"),
        ("Si.upf", "pseudo-v1\n"),
        ("Si.orb", "orbital-v1\n"),
        ("Si.abfs", "aux-v1\n"),
        ("perform.sh", "#!/bin/sh\n"),
        ("get_diel.py", "# adapter-v1\n"),
        ("output_librpa.py", "# writer-v1\n"),
        ("preprocess_abacus_for_librpa_band.py", "# preprocess-v1\n"),
    ):
        (root / name).write_text(content, encoding="utf-8")
    manifest = []
    for path in sorted(root.iterdir()):
        if path.is_file():
            manifest.append(
                {
                    "path": path.name,
                    "size": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    plan = {
        "profile_id": "pinned-stack",
        "route": "periodic_gw_symmetry" if use_symmetry else "periodic_gw",
        "options": {
            "task": "gw",
            "system_type": "solid",
            "use_symmetry": use_symmetry,
            "soc": False,
            "headwing": True,
        },
        "source_manifest": manifest,
    }
    execution = {
        "version_evidence": {
            "verdict": "match",
            "components": {
                name: {
                    "actual_revision": revision,
                    "expected_revision": revision,
                }
                for name, revision in REVISIONS.items()
            },
            "executables": {
                "abacus": {"sha256": "d" * 64},
                "librpa": {"sha256": "e" * 64},
            },
        }
    }
    (oml / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    (oml / "execution.json").write_text(json.dumps(execution), encoding="utf-8")


class ScientificDefinitionTest(unittest.TestCase):
    def test_definition_digest_is_stable_and_nfreq_axis_allows_only_nfreq(self):
        with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
            left_root = pathlib.Path(left_tmp)
            right_root = pathlib.Path(right_tmp)
            write_run(left_root, nfreq=6)
            write_run(right_root, nfreq=12)

            left = build_definition_signature(left_root)
            repeated = build_definition_signature(left_root)
            right = build_definition_signature(right_root)

        self.assertEqual(left, repeated)
        self.assertEqual(left["schema_version"], 2)
        self.assertEqual(
            left["librpa"]["frequency_grid"],
            {
                "type": "minimax",
                "nfreq": 6,
                "frequency_min": 0.005,
                "frequency_interval": 0.0,
                "frequency_max": 1000.0,
                "time_min": 0.005,
                "time_interval": 0.0,
                "minimax_emin": -1.0,
                "minimax_emax": -1.0,
                "minimax_regulation": 0.0,
            },
        )
        self.assertEqual(left["librpa"]["analytic_continuation"]["n_params"], 6)
        self.assertEqual(left["librpa"]["qpe_solver"]["option"], 0)
        self.assertNotEqual(left["digest"], right["digest"])
        differences = compare_definitions(left, right)
        self.assertEqual(
            [item["field"] for item in differences],
            ["librpa.frequency_grid.nfreq"],
        )
        self.assertEqual(compare_definitions(left, right, allowed_axis="nfreq"), [])

    def test_nfreq_axis_rejects_continuation_or_qpe_solver_drift(self):
        with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
            left_root = pathlib.Path(left_tmp)
            right_root = pathlib.Path(right_tmp)
            write_run(left_root, nfreq=24, n_params_anacon=6, option_qpe_solver=0)
            write_run(right_root, nfreq=32, n_params_anacon=8, option_qpe_solver=1)

            left = build_definition_signature(left_root)
            right = build_definition_signature(right_root)

        with self.assertRaises(ScientificDefinitionError) as raised:
            compare_definitions(left, right, allowed_axis="nfreq")

        self.assertEqual(raised.exception.code, "MULTIPLE_DEFINITION_CHANGES")
        self.assertIn("librpa.analytic_continuation.n_params", raised.exception.fields)
        self.assertIn("librpa.qpe_solver.option", raised.exception.fields)
        self.assertIn("librpa.frequency_grid.nfreq", raised.exception.fields)

    def test_empty_state_and_kgrid_axes_are_isolated(self):
        with tempfile.TemporaryDirectory() as base_tmp, tempfile.TemporaryDirectory() as bands_tmp, tempfile.TemporaryDirectory() as grid_tmp:
            base_root = pathlib.Path(base_tmp)
            bands_root = pathlib.Path(bands_tmp)
            grid_root = pathlib.Path(grid_tmp)
            write_run(base_root, nbands=8, grid=(2, 2, 2))
            write_run(bands_root, nbands=12, grid=(2, 2, 2))
            write_run(grid_root, nbands=8, grid=(3, 3, 3))
            base = build_definition_signature(base_root)
            bands = build_definition_signature(bands_root)
            grid = build_definition_signature(grid_root)

        self.assertEqual(compare_definitions(base, bands, allowed_axis="empty_states"), [])
        self.assertEqual(compare_definitions(base, grid, allowed_axis="screening_kgrid"), [])
        self.assertEqual(
            [item["field"] for item in compare_definitions(base, bands)],
            ["abacus.nbands"],
        )
        self.assertEqual(
            [item["field"] for item in compare_definitions(base, grid)],
            ["kpoints.scf.grid"],
        )

    def test_symmetry_axis_pins_abacus_and_librpa_switches(self):
        with tempfile.TemporaryDirectory() as sym_tmp, tempfile.TemporaryDirectory() as full_tmp:
            sym_root = pathlib.Path(sym_tmp)
            full_root = pathlib.Path(full_tmp)
            write_run(sym_root, use_symmetry=True)
            write_run(full_root, use_symmetry=False)

            symmetry = build_definition_signature(sym_root)
            full_q = build_definition_signature(full_root)

        self.assertTrue(symmetry["librpa"]["use_symmetry_exx"])
        self.assertTrue(symmetry["librpa"]["use_symmetry_gw"])
        self.assertFalse(full_q["librpa"]["use_symmetry_exx"])
        self.assertFalse(full_q["librpa"]["use_symmetry_gw"])
        self.assertEqual(
            [item["field"] for item in compare_definitions(symmetry, full_q)],
            [
                "abacus.scf_symmetry",
                "librpa.use_symmetry_exx",
                "librpa.use_symmetry_gw",
                "route",
                "symmetry",
            ],
        )
        self.assertEqual(
            compare_definitions(symmetry, full_q, allowed_axis="symmetry"), []
        )

        full_q["librpa"]["use_shrink_abfs"] = False
        with self.assertRaises(ScientificDefinitionError) as raised:
            compare_definitions(symmetry, full_q, allowed_axis="symmetry")
        self.assertEqual(raised.exception.code, "MULTIPLE_DEFINITION_CHANGES")

    def test_axis_comparison_rejects_simultaneous_asset_or_coulomb_change(self):
        with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
            left_root = pathlib.Path(left_tmp)
            right_root = pathlib.Path(right_tmp)
            write_run(left_root, nfreq=6)
            write_run(right_root, nfreq=12)
            (right_root / "Si.upf").write_text("pseudo-v2\n", encoding="utf-8")
            plan_path = right_root / ".oml" / "plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            pp = next(
                item for item in plan["source_manifest"] if item["path"] == "Si.upf"
            )
            pp["sha256"] = sha256_file(right_root / "Si.upf")
            pp["size"] = (right_root / "Si.upf").stat().st_size
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            librpa = right_root / "librpa.in"
            librpa.write_text(
                librpa.read_text(encoding="utf-8").replace(
                    "use_fullcoul_exx = f", "use_fullcoul_exx = t"
                ),
                encoding="utf-8",
            )
            left = build_definition_signature(left_root)
            right = build_definition_signature(right_root)

        with self.assertRaises(ScientificDefinitionError) as raised:
            compare_definitions(left, right, allowed_axis="nfreq")

        self.assertEqual(raised.exception.code, "MULTIPLE_DEFINITION_CHANGES")
        self.assertIn("assets.pseudopotentials.Si.upf", raised.exception.fields)
        self.assertIn("librpa.use_fullcoul_exx", raised.exception.fields)

    def test_software_revision_is_part_of_the_physical_definition(self):
        with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
            left_root = pathlib.Path(left_tmp)
            right_root = pathlib.Path(right_tmp)
            write_run(left_root)
            write_run(right_root)
            execution_path = right_root / ".oml" / "execution.json"
            execution = json.loads(execution_path.read_text(encoding="utf-8"))
            execution["version_evidence"]["components"]["librpa"][
                "actual_revision"
            ] = "f" * 40
            execution_path.write_text(json.dumps(execution), encoding="utf-8")

            differences = compare_definitions(
                build_definition_signature(left_root),
                build_definition_signature(right_root),
            )

        self.assertEqual(
            [item["field"] for item in differences],
            ["software.revisions.librpa"],
        )

    def test_workflow_helper_hashes_are_part_of_the_definition(self):
        with tempfile.TemporaryDirectory() as left_tmp, tempfile.TemporaryDirectory() as right_tmp:
            left_root = pathlib.Path(left_tmp)
            right_root = pathlib.Path(right_tmp)
            write_run(left_root)
            write_run(right_root)
            helper = right_root / "output_librpa.py"
            helper.write_text("# writer-v2\n", encoding="utf-8")
            plan_path = right_root / ".oml" / "plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            item = next(
                entry
                for entry in plan["source_manifest"]
                if entry["path"] == "output_librpa.py"
            )
            item["sha256"] = sha256_file(helper)
            item["size"] = helper.stat().st_size
            plan_path.write_text(json.dumps(plan), encoding="utf-8")

            differences = compare_definitions(
                build_definition_signature(left_root),
                build_definition_signature(right_root),
            )

        self.assertEqual(
            [item["field"] for item in differences],
            ["workflow_helpers.output_librpa.py"],
        )


if __name__ == "__main__":
    unittest.main()
