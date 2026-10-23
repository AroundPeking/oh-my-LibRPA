import hashlib
import json
import pathlib
import tempfile
import unittest

from oml_mcp.basis_registry import (
    BasisRegistryError,
    load_registry,
    resolve_set,
    stage_element_sets,
    verify_asset,
)


ORB = """Element {element}
Lmax 1
Number of Sorbital--> 2
Number of Porbital--> 1
"""
PP = "pseudopotential payload for {element}\n"
ABF = "auxiliary basis payload for {element}\n"
EXTENSIONS = {"pp": ".upf", "nao": ".orb", "abf": ".abfs"}


def write_asset(root: pathlib.Path, element: str, role: str, set_id: str, content: str) -> dict:
    relative = f"data/elements/{element}/{role}/{set_id}{EXTENSIONS[role]}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    entry = {
        "role": role,
        "path": relative,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "size_bytes": len(content.encode()),
    }
    if role == "nao":
        entry["dimensions"] = {"basis_dimension": 5}
    return entry


def make_set(
    root: pathlib.Path,
    element: str,
    set_id: str,
    family: str,
    *,
    with_abf: bool = True,
) -> pathlib.Path:
    files = [
        write_asset(root, element, "pp", set_id, PP.format(element=element)),
        write_asset(root, element, "nao", set_id, ORB.format(element=element)),
    ]
    if with_abf:
        files.append(write_asset(root, element, "abf", set_id, ABF.format(element=element)))
    set_dir = root / f"data/elements/{element}/sets/{set_id}"
    set_dir.mkdir(parents=True)
    (set_dir / "set.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": set_id,
                "element": element,
                "family": family,
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return set_dir


class BasisRegistryTest(unittest.TestCase):
    def _root(self) -> pathlib.Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        make_set(root, "Ga", "Ga-Dojo-NC-SR-aaaa", "Dojo-NC-SR")
        make_set(root, "N", "N-Dojo-NC-SR-bbbb", "Dojo-NC-SR")
        return root

    def test_load_and_resolve(self):
        root = self._root()
        registry = load_registry(root)
        self.assertEqual(sorted(registry), ["Ga", "N"])
        resolved = resolve_set(registry, "Ga")
        self.assertEqual(resolved.set_id, "Ga-Dojo-NC-SR-aaaa")
        self.assertEqual(resolved.family, "Dojo-NC-SR")
        self.assertIn("nao", resolved.files)

    def test_resolve_by_family(self):
        registry = load_registry(self._root())
        resolved = resolve_set(registry, "Ga", family="dojo_nc_sr")
        self.assertEqual(resolved.set_id, "Ga-Dojo-NC-SR-aaaa")

    def test_family_mismatch_lists_available(self):
        registry = load_registry(self._root())
        with self.assertRaisesRegex(BasisRegistryError, "available"):
            resolve_set(registry, "Ga", family="gth")

    def test_missing_element_points_to_the_build_skill(self):
        registry = load_registry(self._root())
        with self.assertRaisesRegex(BasisRegistryError, "abacus-librpa-gw-basis-skill"):
            resolve_set(registry, "Te")

    def test_require_abf_filters_sets_without_auxiliary_basis(self):
        root = self._root()
        make_set(root, "Te", "Te-Dojo-NC-SR-cccc", "Dojo-NC-SR", with_abf=False)
        registry = load_registry(root)
        with self.assertRaisesRegex(BasisRegistryError, "auxiliary basis"):
            resolve_set(registry, "Te", require_abf=True)
        self.assertIsNotNone(resolve_set(registry, "Te"))

    def test_hash_mismatch_is_rejected(self):
        root = self._root()
        registry = load_registry(root)
        asset = resolve_set(registry, "Ga").asset("nao")
        asset.path.write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(BasisRegistryError, "hash mismatch"):
            verify_asset(asset)

    def test_stage_copies_verified_assets(self):
        root = self._root()
        registry = load_registry(root)
        destination = root / "staged"
        staged = stage_element_sets(registry, ["Ga", "N"], destination=destination)
        self.assertEqual(set(staged), {"Ga", "N"})
        for element, roles in staged.items():
            self.assertEqual(set(roles), {"pp", "nao", "abf"})
            for name in roles.values():
                self.assertTrue((destination / name).is_file())
                self.assertIn(element, name)

    def test_incomplete_set_is_not_used(self):
        root = self._root()
        set_dir = root / "data/elements/Te/sets/Te-unresolved"
        set_dir.mkdir(parents=True)
        (set_dir / "set.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "Te-unresolved",
                    "element": "Te",
                    "family": "Unresolved",
                    "files": [
                        {
                            "role": "pp",
                            "path": "data/elements/Te/pp/unresolved.upf",
                            "sha256": "a" * 64,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        registry = load_registry(root)
        with self.assertRaisesRegex(BasisRegistryError, "incomplete"):
            resolve_set(registry, "Te")

    def test_asset_path_escape_is_rejected(self):
        root = self._root()
        set_dir = root / "data/elements/Ga/sets/Ga-Escape"
        set_dir.mkdir(parents=True)
        (set_dir / "set.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": "Ga-Escape",
                    "element": "Ga",
                    "family": "Escape",
                    "files": [
                        {"role": "pp", "path": "../../../evil.upf", "sha256": "a" * 64},
                        {"role": "nao", "path": "../../../evil.orb", "sha256": "b" * 64},
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BasisRegistryError, "escapes"):
            load_registry(root)


if __name__ == "__main__":
    unittest.main()
