import json
import pathlib
import subprocess
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch


from oml_mcp.errors import OMLError
from oml_mcp.executor import SlurmExecutor
from oml_mcp.profiles import load_profile
from oml_mcp.stage_templates import stage_job_name
from tests.test_materializer import make_profile


class SlurmExecutorTest(unittest.TestCase):
    def test_submission_reconciliation_finds_one_job_or_confirms_absence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            executor = SlurmExecutor(profile)
            name = stage_job_name("run-20260813T010203Z-0123456789", "scf")

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(
                    [], 0, f"31415|RUNNING|{name}\n", ""
                )
                found = executor.reconcile_submission(
                    "run-20260813T010203Z-0123456789", "scf"
                )

            self.assertEqual(found["verdict"], "found")
            self.assertEqual(found["scheduler_id"], "31415")
            self.assertEqual(found["normalized_state"], "RUNNING")

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.side_effect = (
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                )
                absent = executor.reconcile_submission(
                    "run-20260813T010203Z-0123456789", "scf"
                )

            self.assertEqual(absent["verdict"], "absent")
            self.assertRegex(absent["observed_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_submission_reconciliation_rejects_multiple_matching_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            executor = SlurmExecutor(profile)
            run_id = "run-20260813T010203Z-0123456789"
            name = stage_job_name(run_id, "scf")

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess(
                    [], 0, f"31415|RUNNING|{name}\n31416|PENDING|{name}\n", ""
                )
                with self.assertRaisesRegex(OMLError, "SUBMISSION_AMBIGUOUS"):
                    executor.reconcile_submission(run_id, "scf")

    def test_remote_scheduler_arguments_are_shell_quoted_as_one_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            base = make_profile(root, root / "sources")
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            executor = SlurmExecutor(profile)

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, "", "")
                executor.reconcile_submission("run-20260813T010203Z-0123456789", "scf")

            command = run.call_args_list[0].args[0]

        self.assertEqual(command[:2], ["/usr/bin/ssh", "approved-hpc"])
        self.assertEqual(len(command), 3)
        self.assertIn("'%i|%T|%j'", command[2])

    def test_local_submit_uses_exact_program_cwd_and_generated_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            source_root = root / "sources"
            profile = make_profile(root, source_root)
            run_dir = root / "runs" / "run-1"
            script = run_dir / ".oml" / "stages" / "scf.slurm"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/bash\n", encoding="utf-8")
            executor = SlurmExecutor(profile)

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, "31415;cluster\n", "")
                scheduler_id = executor.submit(
                    run_dir,
                    "scf",
                    attempt_id="attempt-0123456789abcdef0123",
                    remote_run_dir=None,
                )

            self.assertEqual(scheduler_id, "31415")
            self.assertEqual(
                run.call_args.args[0],
                [
                    profile.scheduler["submit_program"],
                    "--parsable",
                    "--export=ALL,OML_ATTEMPT_ID=attempt-0123456789abcdef0123",
                    ".oml/stages/scf.slurm",
                ],
            )
            self.assertEqual(run.call_args.kwargs["cwd"], run_dir)
            self.assertFalse(run.call_args.kwargs["shell"])

    def test_submit_rejects_unknown_stage_missing_script_and_bad_scheduler_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            executor = SlurmExecutor(profile)

            with self.assertRaisesRegex(OMLError, "STATE_TRANSITION_DENIED"):
                executor.submit(
                    run_dir,
                    "cleanup",
                    attempt_id="attempt-0123456789abcdef0123",
                    remote_run_dir=None,
                )
            with self.assertRaisesRegex(OMLError, "STAGE_SCRIPT_MISSING"):
                executor.submit(
                    run_dir,
                    "scf",
                    attempt_id="attempt-0123456789abcdef0123",
                    remote_run_dir=None,
                )

            script = run_dir / ".oml" / "stages" / "scf.slurm"
            script.parent.mkdir(parents=True)
            script.write_text("#!/bin/bash\n", encoding="utf-8")
            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, "unexpected output\n", "")
                with self.assertRaisesRegex(OMLError, "SUBMISSION_AMBIGUOUS"):
                    executor.submit(
                        run_dir,
                        "scf",
                        attempt_id="attempt-0123456789abcdef0123",
                        remote_run_dir=None,
                    )

    def test_scheduler_timeout_is_unobservable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            executor = SlurmExecutor(profile)

            with patch("oml_mcp.executor.subprocess.run", side_effect=subprocess.TimeoutExpired([], 20)):
                observation = executor.status("31415")

        self.assertEqual(observation["normalized_state"], "UNKNOWN")
        self.assertEqual(observation["error_code"], "SCHEDULER_UNOBSERVABLE")
        self.assertRegex(observation["observed_at"], r"^\d{4}-\d{2}-\d{2}T")

    def test_version_check_timeout_is_not_reported_as_an_ambiguous_submission(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            executor = SlurmExecutor(profile)

            with patch(
                "oml_mcp.executor.subprocess.run",
                side_effect=subprocess.TimeoutExpired([], 20),
            ):
                with self.assertRaisesRegex(OMLError, "SCHEDULER_UNOBSERVABLE") as raised:
                    executor.verify_versions()

        self.assertNotEqual(raised.exception.code, "SUBMISSION_AMBIGUOUS")

    def test_scheduler_states_are_normalized_without_claiming_stage_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            executor = SlurmExecutor(profile)
            states = {}
            for raw in ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"):
                with patch("oml_mcp.executor.subprocess.run") as run:
                    run.return_value = subprocess.CompletedProcess([], 0, raw + "\n", "")
                    states[raw] = executor.status("31415")["normalized_state"]

        self.assertEqual(states["PENDING"], "PENDING")
        self.assertEqual(states["RUNNING"], "RUNNING")
        self.assertEqual(states["COMPLETED"], "COMPLETED")
        self.assertEqual(states["FAILED"], "FAILED")
        self.assertEqual(states["CANCELLED"], "CANCELLED")

    def test_scheduler_history_resolves_job_after_it_leaves_active_queue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            executor = SlurmExecutor(profile)

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.side_effect = (
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "COMPLETED|\n", ""),
                )
                observation = executor.status("31415")

        self.assertEqual(observation["normalized_state"], "COMPLETED")
        self.assertEqual(observation["source"], "sacct")
        self.assertRegex(observation["observed_at"], r"^\d{4}-\d{2}-\d{2}T")
        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                profile.scheduler["history_program"],
                "-n",
                "-X",
                "-j",
                "31415",
                "--format=State",
                "--parsable2",
            ],
        )

    def test_remote_snapshot_is_new_and_never_overwrites_the_run_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            base = make_profile(root, root / "sources")
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            executor = SlurmExecutor(profile)
            snapshot = root / "runs" / "run-1" / ".oml" / "snapshots" / "attempt-1"

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, "", "")
                executor.snapshot_run("/work/approved/oml/run-1", snapshot)

            self.assertTrue(snapshot.is_dir())
            self.assertEqual(
                run.call_args.args[0],
                [
                    "/usr/bin/rsync",
                    "-a",
                    "--",
                    "approved-hpc:/work/approved/oml/run-1/",
                    f"{snapshot.parent}/.{snapshot.name}.fetching/",
                ],
            )
            executor.snapshot_run("/work/approved/oml/run-1", snapshot)
            self.assertEqual(run.call_count, 1)

    def test_pinned_source_revisions_are_verified_before_execution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            profile = make_profile(root, root / "sources")
            executor = SlurmExecutor(profile)
            pinned = load_profile()["components"]

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.side_effect = tuple(
                    subprocess.CompletedProcess([], 0, pinned[name]["revision"] + "\n", "")
                    for name in ("abacus", "librpa", "pyatb")
                ) + (
                    subprocess.CompletedProcess([], 0, '{"sha256":"' + "a" * 64 + '","size":100}\n', ""),
                    subprocess.CompletedProcess([], 0, '{"sha256":"' + "b" * 64 + '","size":200}\n', ""),
                )
                evidence = executor.verify_versions()

            self.assertEqual(evidence["verdict"], "match")
            self.assertEqual(len(run.call_args_list), 5)
            self.assertEqual(evidence["executables"]["abacus"]["sha256"], "a" * 64)
            self.assertEqual(evidence["executables"]["librpa"]["size"], 200)

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.side_effect = (
                    subprocess.CompletedProcess([], 0, "0" * 40 + "\n", ""),
                    subprocess.CompletedProcess([], 0, pinned["librpa"]["revision"] + "\n", ""),
                    subprocess.CompletedProcess([], 0, pinned["pyatb"]["revision"] + "\n", ""),
                )
                with self.assertRaisesRegex(OMLError, "VERSION_MISMATCH"):
                    executor.verify_versions()

    def test_remote_bundle_dry_run_blocks_changed_controlled_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            base = make_profile(root, root / "sources")
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            run_dir = root / "runs" / "run-1"
            oml = run_dir / ".oml"
            oml.mkdir(parents=True)
            (run_dir / "INPUT_scf").write_text("input\n")
            (oml / "plan.json").write_text("{}\n")
            (oml / "manifest.json").write_text(
                json.dumps({"files": [{"path": "INPUT_scf"}]}) + "\n"
            )
            executor = SlurmExecutor(profile)

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, "", "")
                evidence = executor.verify_remote_bundle(run_dir, "/work/approved/oml/run-1")
            self.assertEqual(evidence["verdict"], "match")
            self.assertIn("--dry-run", run.call_args.args[0])
            self.assertIn("--checksum", run.call_args.args[0])

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.return_value = subprocess.CompletedProcess([], 0, ">fcs....... INPUT_scf\n", "")
                with self.assertRaisesRegex(OMLError, "REMOTE_MANIFEST_MISMATCH"):
                    executor.verify_remote_bundle(run_dir, "/work/approved/oml/run-1")

    def test_remote_bundle_rejects_unmanifested_runtime_code_or_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            base = make_profile(root, root / "sources")
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            executor = SlurmExecutor(profile)

            with patch("oml_mcp.executor.subprocess.run") as run:
                run.side_effect = (
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "*deleting env.sh\n", ""),
                )
                with self.assertRaisesRegex(OMLError, "REMOTE_MANIFEST_MISMATCH"):
                    executor.verify_remote_bundle(run_dir, "/work/approved/oml/run-1")

            protected = run.call_args.args[0]

        self.assertIn("--delete", protected)

    def test_remote_prepare_requires_a_fresh_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            base = make_profile(root, root / "sources")
            profile = replace(
                base,
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            executor = SlurmExecutor(profile)
            with patch("oml_mcp.executor.subprocess.run") as run:
                run.side_effect = (
                    subprocess.CompletedProcess([], 0, "", ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                )
                executor.sync_run(run_dir, "/work/approved/oml/run-1")

            create = run.call_args_list[0].args[0]

        self.assertEqual(
            create,
            [
                "/usr/bin/ssh",
                "approved-hpc",
                "mkdir",
                "--",
                "/work/approved/oml/run-1",
            ],
        )


if __name__ == "__main__":
    unittest.main()
