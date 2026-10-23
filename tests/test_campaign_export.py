import json
import pathlib
import tempfile
import unittest

import yaml

from oml_mcp.campaign_export import (
    ManifestError,
    build_manifest,
    file_entry,
    manifest_digest,
    write_manifest,
)


def make_workspace(root: pathlib.Path) -> pathlib.Path:
    workspace = root / "workspace"
    workspace.mkdir(exist_ok=True)
    (workspace / "STRU").write_text("ATOMIC_SPECIES\nGa 69.723 Ga.upf\n", encoding="utf-8")
    (workspace / "INPUT").write_text("INPUT_PARAMETERS\nnbands 12\n", encoding="utf-8")
    (workspace / "GW_band_spin_1.dat").write_text(
        "1 0 0 0 1.0 0.0 0.0 1.0\n", encoding="utf-8"
    )
    (workspace / "analysis_receipt.json").write_text('{"accepted": true}\n', encoding="utf-8")
    (workspace / "slurm.out").write_text("job done\n", encoding="utf-8")
    return workspace


def manifest_arguments(root: pathlib.Path, **overrides):
    workspace = make_workspace(root)
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
    arguments = {
        "campaign_id": "gan-loop-1",
        "route": "periodic_3d_gw",
        "case": {
            "material": "GaN",
            "formula": "GaN",
            "dimension": "3d",
            "structure_sha256": "a" * 64,
            "site_count": 2,
            "occupied_bands": 8,
        },
        "definition": {"nbands": 12, "nfreq": 24},
        "basis": {
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
        "software": {
            "abacus": {"commit": "1" * 40},
            "librpa": {"executable_sha256": "2" * 64},
        },
        "files": files,
        "performance": {
            "cluster_label": "fisherd",
            "nodes": 1,
            "cpus": 96,
            "mpi_ranks": 1,
            "omp_threads_per_rank": 48,
            "elapsed_seconds": 1234.0,
        },
        "properties": [
            {
                "key": "gw_gap_ev",
                "value": 1.23,
                "unit": "eV",
                "definition": "GW CBM minus VBM on the sampled k grid",
                "status": "reported",
                "evidence": ["analysis_receipt.json"],
            }
        ],
        "workspace": workspace,
        "auxiliary_basis": {
            "mode": "pca_generated",
            "threshold": 1e-4,
            "evidence": ["INPUT"],
        },
        "gates": {"band": {"accepted": True}},
        "ledger": [{"trial": 1, "rule_id": None, "action": None, "accepted": True, "reasons": []}],
    }
    arguments.update(overrides)
    return arguments, workspace


def make_manifest(root: pathlib.Path, **overrides):
    arguments, workspace = manifest_arguments(root, **overrides)
    return build_manifest(**arguments), workspace


class CampaignManifestTest(unittest.TestCase):
    def test_manifest_is_complete_and_hashes_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest, workspace = make_manifest(pathlib.Path(tmpdir))
            import hashlib

            actual = hashlib.sha256((workspace / "INPUT").read_bytes()).hexdigest()
        self.assertEqual(manifest["schema_version"], "oml.campaign-manifest.v1")
        self.assertEqual(manifest["case"]["material"], "GaN")
        self.assertEqual(manifest["files"]["inputs"][0]["role"], "structure")
        self.assertEqual(manifest["auxiliary_basis"]["mode"], "pca_generated")
        self.assertEqual(manifest["performance"]["cluster_label"], "fisherd")
        self.assertEqual(len(manifest["ledger"]), 1)
        # The declared hash is the actual payload hash.
        declared = next(entry for entry in manifest["files"]["inputs"] if entry["path"] == "INPUT")
        self.assertEqual(declared["sha256"], actual)

    def test_yaml_and_json_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            manifest, _ = make_manifest(root)
            yaml_path = root / "manifest.yaml"
            json_path = root / "manifest.json"
            write_manifest(manifest, yaml_path)
            write_manifest(manifest, json_path)
            yaml_value = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            json_value = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(yaml_value["campaign"]["id"], "gan-loop-1")
        self.assertEqual(json_value["case"]["formula"], "GaN")

    def test_stale_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            arguments, workspace = manifest_arguments(root)
            (workspace / "INPUT").write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "stale sha256"):
                build_manifest(**arguments)

    def test_missing_software_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ManifestError, "software.librpa"):
                make_manifest(
                    pathlib.Path(tmpdir),
                    software={"abacus": {"commit": "1" * 40}, "librpa": {}},
                )

    def test_undeclared_property_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ManifestError, "not a declared file"):
                make_manifest(
                    pathlib.Path(tmpdir),
                    properties=[
                        {
                            "key": "gw_gap_ev",
                            "value": 1.0,
                            "unit": "eV",
                            "definition": "d",
                            "status": "reported",
                            "evidence": ["missing.json"],
                        }
                    ],
                )

    def test_structure_role_is_required(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            workspace = make_workspace(root)
            files = {
                "inputs": [
                    file_entry(workspace / "INPUT", root=workspace, role="input", label="INPUT")
                ],
                "results": [
                    file_entry(
                        workspace / "analysis_receipt.json",
                        root=workspace,
                        role="gate_receipt",
                    )
                ],
                "logs": [file_entry(workspace / "slurm.out", root=workspace, role="log")],
            }
            with self.assertRaisesRegex(ManifestError, "structure"):
                make_manifest(pathlib.Path(tmpdir), files=files)

    def test_digest_is_stable(self):
        manifest = {"a": 1, "b": [1, 2]}
        self.assertEqual(manifest_digest(manifest), manifest_digest({"b": [1, 2], "a": 1}))


if __name__ == "__main__":
    unittest.main()
