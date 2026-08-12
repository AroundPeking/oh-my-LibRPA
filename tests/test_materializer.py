import pathlib
import tempfile
import unittest


from oml_mcp.errors import OMLError
from oml_mcp.execution_profiles import ExecutionProfile, execution_profile_receipt
from oml_mcp.materializer import prepare_run
from oml_mcp.planner import plan_case


def make_periodic_source(root: pathlib.Path) -> None:
    root.mkdir(parents=True)
    (root / "INPUT_scf").write_text(
        "\n".join(
            (
                "INPUT_PARAMETERS",
                "calculation scf",
                "basis_type lcao",
                "rpa 1",
                "out_librpa_reader_version 1",
                "symmetry -1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "INPUT_nscf").write_text(
        "INPUT_PARAMETERS\ncalculation nscf\nbasis_type lcao\nsymmetry -1\n",
        encoding="utf-8",
    )
    (root / "KPT_scf").write_text("K_POINTS\n0\nGamma\n2 2 2 0 0 0\n", encoding="utf-8")
    (root / "KPT_nscf").write_text("K_POINTS\n1\nDirect\n0 0 0 1\n", encoding="utf-8")
    (root / "STRU").write_text("ATOMIC_SPECIES\nSi 28 Si.upf\n", encoding="utf-8")
    (root / "librpa.in").write_text(
        "\n".join(
            (
                "task = g0w0",
                "input_dir = .",
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
                "use_shrink_abfs = f",
                "replace_w_head = t",
                "use_soc = 0",
                "use_symmetry_exx = f",
                "use_symmetry_gw = f",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    for name, content in (
        ("Si.upf", "pseudo\n"),
        ("Si.orb", "orbital\n"),
        ("Si.abfs", "auxiliary\n"),
        ("get_diel.py", "print('pyatb')\n"),
        ("output_librpa.py", "print('adapter')\n"),
        ("preprocess_abacus_for_librpa_band.py", "print('preprocess')\n"),
        ("perform.sh", "#!/bin/bash\nset -euo pipefail\npython3 get_diel.py\npython3 output_librpa.py\n"),
    ):
        (root / name).write_text(content, encoding="utf-8")
    (root / "OUT.ABACUS").mkdir()
    (root / "OUT.ABACUS" / "running_scf.log").write_text("stale\n", encoding="utf-8")
    (root / "v1_Cs_data_stale").write_text("stale\n", encoding="utf-8")


def make_profile(root: pathlib.Path, source_root: pathlib.Path) -> ExecutionProfile:
    return ExecutionProfile(
        profile_id="test-local",
        source_path=root / "test-local.json",
        transport="local",
        allowed_source_roots=(source_root.resolve(),),
        allowed_run_roots=((root / "runs").resolve(),),
        state_db=(root / "state" / "oml.sqlite3").resolve(),
        scheduler={
            "submit_program": "/usr/bin/true",
            "status_program": "/usr/bin/true",
            "history_program": "/usr/bin/true",
        },
        resources={
            "partition": "debug",
            "nodes": 1,
            "ntasks_per_node": 4,
            "cpus_per_task": 8,
            "memory_mb": 16000,
            "walltime_minutes": 30,
        },
        runtime={
            "python": "/usr/bin/python3",
            "mpi_launcher": "/usr/bin/true",
            "abacus": "/opt/abacus",
            "librpa": "/opt/chi0_main.exe",
            "mpi_ranks": 4,
            "pyatb_mpi_ranks": 1,
            "omp_threads": 8,
        },
        sources={
            "git_program": "/usr/bin/git",
            "abacus": str(root / "sources-repos" / "abacus"),
            "librpa": str(root / "sources-repos" / "librpa"),
            "pyatb": str(root / "sources-repos" / "pyatb"),
        },
    )


def make_execution_receipt(profile: ExecutionProfile) -> dict:
    return execution_profile_receipt(
        profile,
        {
            "verdict": "match",
            "components": {
                name: {"actual_revision": name * 8, "expected_revision": name * 8}
                for name in ("abacus", "librpa", "pyatb")
            },
        },
    )


class MaterializerTest(unittest.TestCase):
    def test_prepare_run_copies_only_inputs_and_generates_fixed_receipts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")

            receipt = prepare_run(
                source, plan.digest, profile, execution_receipt=make_execution_receipt(profile)
            )
            run_dir = pathlib.Path(receipt["local_run_dir"])

            self.assertTrue((run_dir / "STRU").is_file())
            self.assertTrue((run_dir / "Si.upf").is_file())
            self.assertFalse((run_dir / "OUT.ABACUS").exists())
            self.assertFalse((run_dir / "v1_Cs_data_stale").exists())
            self.assertTrue((run_dir / ".oml" / "plan.json").is_file())
            self.assertTrue((run_dir / ".oml" / "manifest.json").is_file())
            self.assertTrue((run_dir / ".oml" / "execution.json").is_file())
            self.assertEqual(
                {path.name for path in (run_dir / ".oml" / "stages").glob("*.slurm")},
                {"scf.slurm", "pyatb.slurm", "nscf.slurm", "preprocess.slurm", "librpa.slurm"},
            )
            scf = (run_dir / ".oml" / "stages" / "scf.slurm").read_text(encoding="utf-8")
            pyatb = (run_dir / ".oml" / "stages" / "pyatb.slurm").read_text(encoding="utf-8")
            env = (run_dir / ".oml" / "env.sh").read_text(encoding="utf-8")
            self.assertIn("#SBATCH --partition=debug", scf)
            self.assertIn('cp -- "KPT_scf" "KPT"', scf)
            self.assertIn('cp -- "OUT.ABACUS/vxc_out.dat" "vxc_out"', scf)
            self.assertNotIn("eval", scf)
            self.assertIn('bash -- "perform.sh"', pyatb)
            self.assertNotIn('"$OML_MPI_LAUNCHER" -np "$OML_PYATB_MPI_RANKS" bash', pyatb)
            self.assertIn("export python3_exec=/usr/bin/python3", env)
            self.assertIn("export pyatb_mpi_ranks=1", env)
            manifest_text = (run_dir / ".oml" / "manifest.json").read_text(encoding="utf-8")
            self.assertIn('"path": ".oml/env.sh"', manifest_text)
            self.assertIn('"path": ".oml/execution.json"', manifest_text)
            self.assertIn('"path": ".oml/stages/scf.slurm"', manifest_text)
            self.assertEqual((source / "OUT.ABACUS" / "running_scf.log").read_text(), "stale\n")

    def test_prepare_run_matches_the_reviewed_symmetry_plan_digest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            source.joinpath("INPUT_scf").write_text(
                source.joinpath("INPUT_scf").read_text(encoding="utf-8").replace(
                    "symmetry -1", "symmetry 1"
                ),
                encoding="utf-8",
            )
            source.joinpath("librpa.in").write_text(
                source.joinpath("librpa.in").read_text(encoding="utf-8")
                .replace("use_symmetry_exx = f", "use_symmetry_exx = t")
                .replace("use_symmetry_gw = f", "use_symmetry_gw = t"),
                encoding="utf-8",
            )
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid", use_symmetry=True)

            receipt = prepare_run(
                source, plan.digest, profile, execution_receipt=make_execution_receipt(profile)
            )

        self.assertEqual(receipt["plan_digest"], plan.digest)

    def test_stale_plan_is_rejected_before_creating_a_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")
            (source / "KPT_scf").write_text("K_POINTS\n0\nGamma\n3 3 3 0 0 0\n", encoding="utf-8")

            with self.assertRaisesRegex(OMLError, "STALE_PLAN"):
                prepare_run(
                    source, plan.digest, profile, execution_receipt=make_execution_receipt(profile)
                )

            self.assertFalse((root / "runs").exists())

    def test_source_outside_allowed_root_and_escaped_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, root / "different-approved-root")
            plan = plan_case(source, task="gw", system_type="solid")

            with self.assertRaisesRegex(OMLError, "SOURCE_NOT_ALLOWED"):
                prepare_run(
                    source, plan.digest, profile, execution_receipt=make_execution_receipt(profile)
                )

            profile = make_profile(root, source_root)
            outside = root / "outside.upf"
            outside.write_text("outside\n", encoding="utf-8")
            (source / "Si.upf").unlink()
            (source / "Si.upf").symlink_to(outside)

            with self.assertRaisesRegex(OMLError, "SOURCE_UNSAFE"):
                prepare_run(
                    source, plan.digest, profile, execution_receipt=make_execution_receipt(profile)
                )


if __name__ == "__main__":
    unittest.main()
