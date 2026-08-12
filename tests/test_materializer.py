import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch


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
    ):
        (root / name).write_text(content, encoding="utf-8")
    template = pathlib.Path(__file__).resolve().parents[1] / "templates" / "abacus-librpa-gw" / "template"
    for name in (
        "get_diel.py",
        "output_librpa.py",
        "preprocess_abacus_for_librpa_band.py",
        "perform.sh",
    ):
        shutil.copy2(template / name, root / name)
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
        environment={"LD_LIBRARY_PATH": "/opt/lib:/usr/lib"},
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
            (source / "INPUT").write_text("stale working input\n")
            (source / "KPT").write_text("stale working kpoints\n")
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")

            receipt = prepare_run(
                source, plan.digest, profile, execution_receipt=make_execution_receipt(profile)
            )
            run_dir = pathlib.Path(receipt["local_run_dir"])

            self.assertTrue((run_dir / "STRU").is_file())
            self.assertTrue((run_dir / "Si.upf").is_file())
            self.assertFalse((run_dir / "OUT.ABACUS").exists())
            self.assertFalse((run_dir / "INPUT").exists())
            self.assertFalse((run_dir / "KPT").exists())
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
            librpa = (run_dir / ".oml" / "stages" / "librpa.slurm").read_text(encoding="utf-8")
            env = (run_dir / ".oml" / "env.sh").read_text(encoding="utf-8")
            self.assertIn("#SBATCH --partition=debug", scf)
            self.assertIn('cp -- "KPT_scf" "KPT"', scf)
            self.assertIn('cp -- "OUT.ABACUS/vxc_out.dat" "vxc_out"', scf)
            self.assertNotIn("eval", scf)
            self.assertIn('bash -- "perform.sh"', pyatb)
            self.assertNotIn('"$OML_MPI_LAUNCHER" -np "$OML_PYATB_MPI_RANKS" bash', pyatb)
            self.assertIn("export python3_exec=/usr/bin/python3", env)
            self.assertIn("export pyatb_mpi_ranks=1", env)
            self.assertIn("export LD_LIBRARY_PATH=/opt/lib:/usr/lib", env)
            self.assertIn('export OMP_NUM_THREADS="$OML_OMP_THREADS"', scf)
            self.assertIn("export PYTHONDONTWRITEBYTECODE=1", pyatb)
            self.assertIn('export OMP_NUM_THREADS="$OML_OMP_THREADS"', librpa)
            manifest_text = (run_dir / ".oml" / "manifest.json").read_text(encoding="utf-8")
            self.assertIn('"path": ".oml/env.sh"', manifest_text)
            self.assertIn('"path": ".oml/execution.json"', manifest_text)
            self.assertIn('"path": ".oml/plan.json"', manifest_text)
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
            from oml_mcp.state import StateStore

            attempt = StateStore(profile.state_db).authorize_submission(
                receipt["run_id"], "scf", plan.digest
            )

        self.assertEqual(receipt["plan_digest"], plan.digest)
        self.assertEqual(attempt["stage"], "scf")

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

    def test_unreviewed_helper_code_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            (source / "perform.sh").write_text("#!/bin/bash\necho unreviewed\n", encoding="utf-8")
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")

            with self.assertRaisesRegex(OMLError, "HELPER_MISMATCH"):
                prepare_run(
                    source,
                    plan.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

    def test_external_input_and_abacus_asset_directories_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            (source / "librpa.in").write_text(
                (source / "librpa.in").read_text(encoding="utf-8").replace(
                    "input_dir = .", "input_dir = dataset"
                ),
                encoding="utf-8",
            )
            external = plan_case(source, task="gw", system_type="solid")
            with self.assertRaisesRegex(OMLError, "RUN_PATH_UNSAFE"):
                prepare_run(
                    source,
                    external.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

            (source / "librpa.in").write_text(
                (source / "librpa.in").read_text(encoding="utf-8").replace(
                    "input_dir = dataset", "input_dir = ."
                ),
                encoding="utf-8",
            )
            (source / "STRU").write_text(
                "ATOMIC_SPECIES\nSi 28 ../shared/Si.upf\n", encoding="utf-8"
            )
            escaped_stru = plan_case(source, task="gw", system_type="solid")
            with self.assertRaisesRegex(OMLError, "RUN_PATH_UNSAFE"):
                prepare_run(
                    source,
                    escaped_stru.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

            (source / "INPUT_scf").write_text(
                (source / "INPUT_scf").read_text(encoding="utf-8")
                + "pseudo_dir /external/pseudopotentials\n",
                encoding="utf-8",
            )
            escaped = plan_case(source, task="gw", system_type="solid")
            with self.assertRaisesRegex(OMLError, "RUN_PATH_UNSAFE"):
                prepare_run(
                    source,
                    escaped.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

            (source / "INPUT_scf").write_text(
                (source / "INPUT_scf").read_text(encoding="utf-8").replace(
                    "pseudo_dir /external/pseudopotentials\n", ""
                ),
                encoding="utf-8",
            )
            (source / "STRU").write_text(
                "ATOMIC_SPECIES\nSi 28 Si.upf\n", encoding="utf-8"
            )
            (source / "INPUT_nscf").write_text(
                (source / "INPUT_nscf").read_text(encoding="utf-8")
                + "orbital_dir ../shared/orbitals\n",
                encoding="utf-8",
            )
            escaped_nscf = plan_case(source, task="gw", system_type="solid")
            with self.assertRaisesRegex(OMLError, "RUN_PATH_UNSAFE"):
                prepare_run(
                    source,
                    escaped_nscf.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

    def test_identical_sources_in_different_case_directories_register_separate_plans(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            left = source_root / "left"
            right = source_root / "right"
            make_periodic_source(left)
            shutil.copytree(left, right)
            profile = make_profile(root, source_root)
            left_plan = plan_case(left, task="gw", system_type="solid")
            right_plan = plan_case(right, task="gw", system_type="solid")

            left_run = prepare_run(
                left,
                left_plan.digest,
                profile,
                execution_receipt=make_execution_receipt(profile),
            )
            right_run = prepare_run(
                right,
                right_plan.digest,
                profile,
                execution_receipt=make_execution_receipt(profile),
            )

        self.assertEqual(left_plan.digest, right_plan.digest)
        self.assertNotEqual(left_plan.plan_id, right_plan.plan_id)
        self.assertNotEqual(left_run["run_id"], right_run["run_id"])

    def test_state_registration_failure_removes_the_unpublished_run_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")

            with patch(
                "oml_mcp.materializer.StateStore.create_run",
                side_effect=OMLError(
                    "RUN_CONFLICT",
                    "injected registration failure",
                    evidence=(),
                    recovery="retry",
                ),
            ):
                with self.assertRaisesRegex(OMLError, "RUN_CONFLICT"):
                    prepare_run(
                        source,
                        plan.digest,
                        profile,
                        execution_receipt=make_execution_receipt(profile),
                    )

            run_dirs = tuple((root / "runs").glob("run-*"))

        self.assertEqual(run_dirs, ())

    def test_magnetic_and_strict_2d_routes_are_not_executable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)

            magnetic_text = (source / "INPUT_scf").read_text(encoding="utf-8") + "nspin 2\n"
            (source / "INPUT_scf").write_text(magnetic_text, encoding="utf-8")
            magnetic = plan_case(source, task="gw", system_type="solid")
            with self.assertRaisesRegex(OMLError, "ROUTE_NOT_EXECUTABLE"):
                prepare_run(
                    source,
                    magnetic.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

            (source / "INPUT_scf").write_text(
                magnetic_text.replace("nspin 2\n", ""), encoding="utf-8"
            )
            nscf_magnetic_text = (
                source / "INPUT_nscf"
            ).read_text(encoding="utf-8") + "nspin 2\n"
            (source / "INPUT_nscf").write_text(nscf_magnetic_text, encoding="utf-8")
            nscf_magnetic = plan_case(source, task="gw", system_type="solid")
            with self.assertRaisesRegex(OMLError, "ROUTE_NOT_EXECUTABLE"):
                prepare_run(
                    source,
                    nscf_magnetic.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

            (source / "INPUT_nscf").write_text(
                nscf_magnetic_text.replace("nspin 2\n", ""), encoding="utf-8"
            )
            nscf_symmetry_text = (
                source / "INPUT_nscf"
            ).read_text(encoding="utf-8").replace("symmetry -1", "symmetry 1")
            (source / "INPUT_nscf").write_text(nscf_symmetry_text, encoding="utf-8")
            nscf_symmetry = plan_case(source, task="gw", system_type="solid")
            with self.assertRaisesRegex(OMLError, "ROUTE_NOT_EXECUTABLE"):
                prepare_run(
                    source,
                    nscf_symmetry.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

            (source / "INPUT_nscf").write_text(
                nscf_symmetry_text.replace("symmetry 1", "symmetry -1"),
                encoding="utf-8",
            )
            strict_2d = plan_case(source, task="gw", system_type="2d")
            with self.assertRaisesRegex(OMLError, "ROUTE_NOT_EXECUTABLE"):
                prepare_run(
                    source,
                    strict_2d.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

    def test_mixed_source_after_planning_returns_stable_stale_plan_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            source = source_root / "si"
            make_periodic_source(source)
            profile = make_profile(root, source_root)
            plan = plan_case(source, task="gw", system_type="solid")
            (source / "control.in").write_text("xc pbe\n", encoding="utf-8")
            (source / "geometry.in").write_text("atom 0 0 0 Si\n", encoding="utf-8")

            with self.assertRaisesRegex(OMLError, "STALE_PLAN") as raised:
                prepare_run(
                    source,
                    plan.digest,
                    profile,
                    execution_receipt=make_execution_receipt(profile),
                )

        self.assertEqual(raised.exception.code, "STALE_PLAN")

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
