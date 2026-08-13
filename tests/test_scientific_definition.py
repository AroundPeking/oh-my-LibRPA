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


def write_run(root: pathlib.Path, *, nfreq: int = 6, nbands: int = 8, grid=(2, 2, 2)) -> None:
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
                "symmetry 1",
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
                f"nfreq = {nfreq}",
                "option_dielect_func = 3",
                "replace_w_head = t",
                "use_fullcoul_exx = f",
                "use_shrink_abfs = t",
                "use_shrink_chi = t",
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
        "route": "periodic_gw_symmetry",
        "options": {
            "task": "gw",
            "system_type": "solid",
            "use_symmetry": True,
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
        self.assertNotEqual(left["digest"], right["digest"])
        differences = compare_definitions(left, right)
        self.assertEqual([item["field"] for item in differences], ["librpa.nfreq"])
        self.assertEqual(compare_definitions(left, right, allowed_axis="nfreq"), [])

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


if __name__ == "__main__":
    unittest.main()
