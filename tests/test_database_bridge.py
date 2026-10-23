import hashlib
import json
import pathlib
import tempfile
import unittest

from oml_mcp.campaign_export import build_manifest, file_entry
from oml_mcp.database_bridge import (
    BridgeError,
    build_candidate,
    record_type_for_route,
    sanitize_text,
)


STRU = "ATOMIC_SPECIES\nGa 69.723 Ga.upf\n"
INPUT = "INPUT_PARAMETERS\nnbands 12\n"
BANDS = "1 0 0 0 1.0 0.0 0.0 1.0\n"
LOG = "host /Users/ghj/run/x SLURM_JOB_ID=7\n"


def make_manifest(root: pathlib.Path, *, route: str = "periodic_3d_gw") -> dict:
    workspace = root / "workspace"
    workspace.mkdir(exist_ok=True)
    (workspace / "STRU").write_text(STRU, encoding="utf-8")
    (workspace / "INPUT").write_text(INPUT, encoding="utf-8")
    (workspace / "GW_band_spin_1.dat").write_text(BANDS, encoding="utf-8")
    (workspace / "analysis_receipt.json").write_text('{"accepted": true}\n', encoding="utf-8")
    (workspace / "slurm.out").write_text(LOG, encoding="utf-8")
    files = {
        "inputs": [
            file_entry(workspace / "STRU", root=workspace, role="structure", label="STRU"),
            file_entry(workspace / "INPUT", root=workspace, role="input", label="INPUT"),
        ],
        "results": [
            file_entry(
                workspace / "GW_band_spin_1.dat", root=workspace, role="result", label="GW_band"
            ),
            file_entry(
                workspace / "analysis_receipt.json",
                root=workspace,
                role="gate_receipt",
                label="analysis_receipt",
            ),
        ],
        "logs": [file_entry(workspace / "slurm.out", root=workspace, role="log", label="slurm")],
    }
    return build_manifest(
        campaign_id="gan-loop-1",
        route=route,
        case={
            "material": "GaN",
            "formula": "GaN",
            "dimension": "3d",
            "structure_sha256": "a" * 64,
            "site_count": 2,
            "occupied_bands": 8,
        },
        definition={"nbands": 12, "nfreq": 24},
        basis={
            "species": [
                {
                    "element": "Ga",
                    "set_id": "Ga-Dojo-NC-SR-1",
                    "pp_sha256": "b" * 64,
                    "nao_sha256": "c" * 64,
                    "abf_sha256": "d" * 64,
                    "dimension_per_atom": 41,
                    "atom_count": 1,
                }
            ]
        },
        software={
            "abacus": {"commit": "1" * 40},
            "librpa": {"executable_sha256": "2" * 64},
        },
        files=files,
        performance={
            "cluster_label": "fisherd",
            "nodes": 1,
            "cpus": 96,
            "mpi_ranks": 1,
            "omp_threads_per_rank": 48,
            "elapsed_seconds": 1234.0,
        },
        properties=[
            {
                "key": "gw_gap_ev",
                "value": 1.23,
                "unit": "eV",
                "definition": "GW CBM minus VBM on the sampled k grid",
                "status": "reported",
                "evidence": ["analysis_receipt.json"],
            }
        ],
        workspace=workspace,
        auxiliary_basis={
            "mode": "pca_generated",
            "threshold": 1e-4,
            "evidence": ["INPUT"],
        },
        gates={"band": {"accepted": True}},
        ledger=[{"trial": 1, "rule_id": None, "action": None, "accepted": True, "reasons": []}],
    )


class DatabaseBridgeTest(unittest.TestCase):
    def test_builds_a_complete_band_record(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            manifest = make_manifest(root)
            candidate = build_candidate(manifest, staging_root=root / "staging")
            record = candidate["record"]
            record_file = pathlib.Path(candidate["record_path"])
            record_text = record_file.read_text(encoding="utf-8")
            staged_log = root / "staging" / record["files"]["logs"][0]["path"]
            self.assertTrue(staged_log.is_file())

        self.assertEqual(record["id"], "oml-gan-loop-1")
        self.assertEqual(record["record_type"], "band")
        self.assertEqual(record["dimension"], "3d")
        self.assertEqual(record["structure_identity"]["algorithm"], "cell-sites-v1")
        self.assertIn("data/calculations/3d/GaN/oml-gan-loop-1/inputs/", record["structure_identity"]["evidence"])
        self.assertEqual(record["species"][0]["set_id"], "Ga-Dojo-NC-SR-1")
        self.assertEqual(record["auxiliary_basis"]["mode"], "pca_generated")
        self.assertEqual(record["computational_scale"]["atom_count"], 1)
        self.assertEqual(record["computational_scale"]["ao_count"], 41)
        self.assertEqual(record["computational_scale"]["occupied_states"], 8)
        self.assertEqual(record["computational_scale"]["unoccupied_states"], 4)
        self.assertEqual(record["summary"]["observable"], "gw_gap_ev")
        self.assertEqual(record["performance"]["cluster_label"], "fisherd")
        self.assertEqual(record["workflow"], {"frontend": "abacus", "task": "gw"})
        self.assertEqual(hashlib.sha256(record_text.encode()).hexdigest(), candidate["candidate_sha256"])
        self.assertEqual(candidate["plan"]["candidate_sha256"], candidate["candidate_sha256"])
        self.assertFalse(candidate["receipt"]["approved"])

    def test_sanitizes_private_paths_and_job_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            manifest = make_manifest(root)
            candidate = build_candidate(manifest, staging_root=root / "staging")
            log_entry = candidate["record"]["files"]["logs"][0]
            staged = root / "staging" / log_entry["path"]
            text = staged.read_text(encoding="utf-8")
        self.assertEqual(log_entry["transformation"], "sanitized")
        self.assertIn("/HPC/run/x", text)
        self.assertIn("SLURM_JOBID=7", text)
        self.assertNotIn("SLURM_JOB_ID", text)

    def test_receipt_requires_an_explicit_approval_statement(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            manifest = make_manifest(root)
            with self.assertRaisesRegex(BridgeError, "user_statement"):
                build_candidate(
                    manifest, staging_root=root / "bad", approval={"user_statement": ""}
                )
            manifest = make_manifest(root)
            candidate = build_candidate(
                manifest,
                staging_root=root / "good",
                approval={"user_statement": "批准入库", "timestamp": "2026-10-23T13:00:00Z"},
            )
        self.assertTrue(candidate["receipt"]["approved"])
        self.assertEqual(candidate["receipt"]["user_statement"], "批准入库")

    def test_route_mapping_and_unknown_routes(self):
        self.assertEqual(record_type_for_route("strict_2d_sos_rpa"), "rpa_energy")
        self.assertEqual(record_type_for_route("periodic_3d_gw"), "band")
        with self.assertRaises(BridgeError):
            record_type_for_route("unknown_route")

    def test_existing_staging_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            manifest = make_manifest(root)
            build_candidate(manifest, staging_root=root / "staging")
            with self.assertRaisesRegex(BridgeError, "already exists"):
                build_candidate(manifest, staging_root=root / "staging")

    def test_sanitize_text_reports_changes(self):
        cleaned, changed = sanitize_text("at /home/ghj/run and /work1/ghj/x SLURM_JOB_ID")
        self.assertTrue(changed)
        self.assertEqual(cleaned, "at /HPC/run and /HPC/x SLURM_JOBID")
        unchanged, changed = sanitize_text("nothing to do")
        self.assertFalse(changed)
        self.assertEqual(unchanged, "nothing to do")


if __name__ == "__main__":
    unittest.main()
