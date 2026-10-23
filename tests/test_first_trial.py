import hashlib
import json
import pathlib
import tempfile
import unittest

from oml_mcp.basis_registry import BasisRegistryError
from oml_mcp.first_trial import build_first_trial
from oml_mcp.stru import structure_fingerprint


ORB = """Element {element}
Lmax 1
Number of Sorbital--> 2
Number of Porbital--> 1
"""
EXTENSIONS = {"pp": ".upf", "nao": ".orb", "abf": ".abfs"}

STRU = """ATOMIC_SPECIES
Ga 69.723 Ga.upf
N 14.007 N.upf

NUMERICAL_ORBITAL
Ga.orb
N.orb

LATTICE_CONSTANT
1.8897162

LATTICE_VECTORS
3.2 0.0 0.0
0.0 3.2 0.0
0.0 0.0 5.2

ATOMIC_POSITIONS
Direct
Ga
0.0
1
0.0 0.0 0.0 0 0 0

N
0.0
1
0.25 0.25 0.25 0 0 0
"""


def make_registry(root: pathlib.Path, elements=("Ga", "N")) -> pathlib.Path:
    for element in elements:
        set_id = f"{element}-Dojo-NC-SR-{element.lower()}1"
        files = []
        for role, content in (
            ("pp", f"pp {element}\n"),
            ("nao", ORB.format(element=element)),
            ("abf", f"abf {element}\n"),
        ):
            relative = f"data/elements/{element}/{role}/{set_id}{EXTENSIONS[role]}"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            files.append(
                {
                    "role": role,
                    "path": relative,
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "size_bytes": len(content.encode()),
                }
            )
        set_dir = root / f"data/elements/{element}/sets/{set_id}"
        set_dir.mkdir(parents=True)
        (set_dir / "set.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": set_id,
                    "element": element,
                    "family": "Dojo-NC-SR",
                    "files": files,
                }
            ),
            encoding="utf-8",
        )
    return root


def make_reference(root: pathlib.Path, digest: str) -> pathlib.Path:
    directory = root / "data" / "calculations" / "3d" / "GaN" / "gan-ref"
    (directory / "inputs").mkdir(parents=True)
    (directory / "inputs" / "INPUT").write_text("INPUT_PARAMETERS\n", encoding="utf-8")
    record = {
        "schema_version": 1,
        "id": "gan-ref",
        "material": "GaN",
        "dimension": "3d",
        "record_type": "band",
        "structure_identity": {
            "algorithm": "cell-sites-v1",
            "sha256": digest,
            "evidence": "data/calculations/3d/GaN/gan-ref/inputs/INPUT",
        },
        "properties": [{"key": "gap", "status": "validated"}],
        "software": {
            "abacus": {"commit": "1" * 40},
            "librpa": {"executable_sha256": "2" * 64},
        },
        "species": [{"element": "Ga", "set_id": "Ga-set"}, {"element": "N", "set_id": "N-set"}],
        "auxiliary_basis": {"mode": "pca_generated", "threshold": 1e-4},
        "files": {"inputs": [{"path": "data/calculations/3d/GaN/gan-ref/inputs/INPUT"}]},
    }
    (directory / "record.json").write_text(json.dumps(record), encoding="utf-8")
    return root


class FirstTrialTest(unittest.TestCase):
    def _case(self, root: pathlib.Path) -> pathlib.Path:
        case = root / "case"
        case.mkdir()
        (case / "STRU").write_text(STRU, encoding="utf-8")
        return case

    def test_nbands_equals_nbasis_and_basis_sets_are_resolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            case = self._case(root)
            make_registry(root / "library")
            trial = build_first_trial(
                case,
                route="periodic_3d_gw",
                registry_root=root / "library",
                dimension="3d",
            )
        self.assertEqual(trial.definition["nbands"], 10)  # 2 atoms * (2*1 + 1*3)
        self.assertEqual(trial.basis["Ga"]["set_id"], "Ga-Dojo-NC-SR-ga1")
        self.assertEqual(trial.basis["N"]["dimension_per_atom"], 5)
        self.assertEqual(trial.nbasis, 10)
        self.assertEqual(trial.atom_counts, {"Ga": 1, "N": 1})
        expected, sites = structure_fingerprint(STRU, dimension="3d")
        self.assertEqual(trial.structure_sha256, expected)
        self.assertEqual(trial.site_count, sites)

    def test_staging_rewrites_the_file_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            case = self._case(root)
            make_registry(root / "library")
            trial = build_first_trial(
                case,
                route="periodic_3d_gw",
                registry_root=root / "library",
                dimension="3d",
                stage_dir=root / "staged",
            )
            self.assertTrue((root / "staged" / trial.basis["Ga"]["nao_file"]).is_file())
        self.assertTrue(trial.basis["Ga"]["nao_file"].startswith("Ga_nao_"))
        self.assertTrue(trial.basis["N"]["abf_file"].startswith("N_abf_"))

    def test_trusted_reference_is_returned_but_not_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            case = self._case(root)
            make_registry(root / "library")
            digest, _ = structure_fingerprint(STRU, dimension="3d")
            make_reference(root / "references", digest)
            trial = build_first_trial(
                case,
                route="periodic_3d_gw",
                registry_root=root / "library",
                dimension="3d",
                reference_root=root / "references",
            )
        self.assertEqual(len(trial.references), 1)
        self.assertTrue(trial.references[0]["trustworthy"])
        self.assertEqual(trial.references[0]["record_id"], "gan-ref")
        # The reference is advisory: nbands still comes from nbasis.
        self.assertEqual(trial.definition["nbands"], 10)

    def test_missing_element_fails_with_the_build_hint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            case = self._case(root)
            make_registry(root / "library", elements=("Ga",))
            with self.assertRaisesRegex(BasisRegistryError, "abacus-librpa-gw-basis-skill"):
                build_first_trial(
                    case,
                    route="periodic_3d_gw",
                    registry_root=root / "library",
                    dimension="3d",
                )


if __name__ == "__main__":
    unittest.main()
