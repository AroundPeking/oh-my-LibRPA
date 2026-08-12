import json
import pathlib
import tempfile
import unittest


from oml_mcp.errors import OMLError
from oml_mcp.execution_profiles import execution_profile_receipt, load_execution_profile


def write_profile(root: pathlib.Path, profile_id: str = "test-local", **updates):
    profile = {
        "schema_version": 1,
        "profile_id": profile_id,
        "enabled": True,
        "transport": "local",
        "allowed_source_roots": [str(root / "sources")],
        "allowed_run_roots": [str(root / "runs")],
        "state_db": str(root / "state" / "oml.sqlite3"),
        "scheduler": {
            "submit_program": "/usr/bin/true",
            "status_program": "/usr/bin/true",
            "history_program": "/usr/bin/true",
        },
        "resources": {
            "partition": "debug",
            "nodes": 1,
            "ntasks_per_node": 4,
            "cpus_per_task": 8,
            "memory_mb": 16000,
            "walltime_minutes": 30,
        },
        "runtime": {
            "python": "/usr/bin/python3",
            "mpi_launcher": "/usr/bin/true",
            "abacus": "/opt/abacus",
            "librpa": "/opt/chi0_main.exe",
            "mpi_ranks": 4,
            "pyatb_mpi_ranks": 1,
            "omp_threads": 8,
        },
        "sources": {
            "git_program": "/usr/bin/git",
            "abacus": "/opt/src/abacus",
            "librpa": "/opt/src/librpa",
            "pyatb": "/opt/src/pyatb",
        },
    }
    profile.update(updates)
    path = root / f"{profile_id}.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    return path


class ExecutionProfileTest(unittest.TestCase):
    def test_loads_enabled_profile_by_id_from_configured_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_profile(root)

            profile = load_execution_profile("test-local", roots=(root,))

        self.assertEqual(profile.profile_id, "test-local")
        self.assertEqual(profile.transport, "local")
        self.assertEqual(profile.runtime["mpi_ranks"], 4)
        self.assertEqual(profile.resources["partition"], "debug")
        self.assertEqual(profile.sources["git_program"], "/usr/bin/git")
        self.assertTrue(profile.allowed_run_roots[0].is_absolute())

        receipt = execution_profile_receipt(profile, {"verdict": "match"})
        self.assertEqual(len(receipt["execution_profile_digest"]), 64)
        self.assertEqual(receipt["execution_profile"]["profile_id"], "test-local")

    def test_rejects_unsafe_slurm_resource_text(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_profile(
                root,
                "unsafe-resource",
                resources={
                    "partition": "debug\n#SBATCH --export=ALL",
                    "nodes": 1,
                    "ntasks_per_node": 4,
                    "cpus_per_task": 8,
                    "memory_mb": 16000,
                    "walltime_minutes": 30,
                },
            )

            with self.assertRaisesRegex(OMLError, "PROFILE_INVALID"):
                load_execution_profile("unsafe-resource", roots=(root,))

    def test_rejects_path_ids_disabled_profiles_and_placeholders(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_profile(root, "disabled", enabled=False)
            write_profile(
                root,
                "placeholder",
                runtime={
                    "python": "/path/to/python3",
                    "mpi_launcher": "/usr/bin/true",
                    "abacus": "/opt/abacus",
                    "librpa": "/opt/librpa",
                    "mpi_ranks": 4,
                    "pyatb_mpi_ranks": 1,
                    "omp_threads": 8,
                },
            )

            with self.assertRaisesRegex(OMLError, "PROFILE_ID_INVALID"):
                load_execution_profile("../disabled", roots=(root,))
            with self.assertRaisesRegex(OMLError, "PROFILE_DISABLED"):
                load_execution_profile("disabled", roots=(root,))
            with self.assertRaisesRegex(OMLError, "PROFILE_INVALID"):
                load_execution_profile("placeholder", roots=(root,))

    def test_ssh_profile_requires_bounded_remote_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_profile(root, "bad-ssh", transport="ssh")
            write_profile(
                root,
                "good-ssh",
                transport="ssh",
                ssh={
                    "host": "approved-hpc",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )

            with self.assertRaisesRegex(OMLError, "PROFILE_INVALID"):
                load_execution_profile("bad-ssh", roots=(root,))
            profile = load_execution_profile("good-ssh", roots=(root,))

        self.assertEqual(profile.ssh["host"], "approved-hpc")
        self.assertEqual(profile.ssh["remote_run_root"], "/work/approved/oml")

    def test_ssh_profile_rejects_remote_shell_metacharacters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            write_profile(
                root,
                "unsafe-ssh",
                transport="ssh",
                ssh={
                    "host": "approved-hpc;false",
                    "remote_run_root": "/work/approved/oml",
                    "ssh_program": "/usr/bin/ssh",
                    "rsync_program": "/usr/bin/rsync",
                },
            )

            with self.assertRaisesRegex(OMLError, "PROFILE_INVALID"):
                load_execution_profile("unsafe-ssh", roots=(root,))


if __name__ == "__main__":
    unittest.main()
