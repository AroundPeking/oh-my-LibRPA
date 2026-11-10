"""The basis a run will use must be shown to a human and acknowledged."""

from __future__ import annotations

import hashlib
import json
import pathlib
import tempfile
import unittest

from oml_mcp.basis_disclosure import (
    DISCLOSURE_RELATIVE_PATH,
    BasisDisclosureError,
    build_basis_disclosure,
    disclosure_digest,
    format_basis_disclosure,
    read_disclosure,
    summarise_disclosure,
    write_disclosure,
)
from oml_mcp.basis_registry import (
    BasisAmbiguityError,
    BasisRegistryError,
    load_registry,
    resolve_set,
)


ORB = """Element {element}
Lmax 1
Number of Sorbital--> 2
Number of Porbital--> 1
"""
ABF = """---------------------------------------------------------------------------
Element                     {element}
Lmax                        2
Number of Sorbital-->       3
Number of Porbital-->       2
Number of Dorbital-->       1
---------------------------------------------------------------------------
SUMMARY  END
"""
PP = "pseudopotential payload for {element}\n"
EXTENSIONS = {"pp": ".upf", "nao": ".orb", "abf": ".abfs"}


def _write_asset(root: pathlib.Path, element: str, role: str, set_id: str, content: str) -> dict:
    relative = f"data/elements/{element}/{role}/{set_id}{EXTENSIONS[role]}"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "role": role,
        "path": relative,
        "sha256": hashlib.sha256(content.encode()).hexdigest(),
        "size_bytes": len(content.encode()),
    }


def make_set(
    root: pathlib.Path,
    element: str,
    set_id: str,
    family: str,
    *,
    with_abf: bool = True,
) -> dict[str, str]:
    files = [
        _write_asset(root, element, "pp", set_id, PP.format(element=element)),
        _write_asset(root, element, "nao", set_id, ORB.format(element=element)),
    ]
    if with_abf:
        files.append(_write_asset(root, element, "abf", set_id, ABF.format(element=element)))
    set_dir = root / f"data/elements/{element}/sets/{set_id}"
    set_dir.mkdir(parents=True, exist_ok=True)

    (set_dir / "set.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": set_id,
                "element": element,
                "family": family,
                "validation_scope": f"test scope for {set_id}",
                "files": files,
            }
        ),
        encoding="utf-8",
    )
    return {
        role: f"data/elements/{element}/{role}/{set_id}{EXTENSIONS[role]}"
        for role in ("pp", "nao", "abf")
    }


STRU_TEMPLATE = """ATOMIC_SPECIES
Si 28.0855 {pp}

NUMERICAL_ORBITAL
{nao}

ABFS_ORBITAL
{abf}

LATTICE_CONSTANT
1.8897261254578281

LATTICE_VECTORS
0.0 2.715 2.715
2.715 0.0 2.715
2.715 2.715 0.0

ATOMIC_POSITIONS
Direct
Si
0.0
2
0.0 0.0 0.0
0.25 0.25 0.25
"""


def make_run(root: pathlib.Path, names: dict[str, str]) -> pathlib.Path:
    """Copy one element set's payloads into a run directory with its STRU."""
    run = root / "run"
    run.mkdir(parents=True, exist_ok=True)
    for role, relative in names.items():
        source = root / relative
        (run / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (run / "STRU").write_text(
        STRU_TEMPLATE.format(
            pp=pathlib.Path(names["pp"]).name,
            nao=pathlib.Path(names["nao"]).name,
            abf=pathlib.Path(names["abf"]).name,
        ),
        encoding="utf-8",
    )
    return run


class BasisAmbiguityTest(unittest.TestCase):
    def test_two_usable_sets_are_refused_instead_of_picked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            make_set(root, "Si", "Si-SG15-aaaa", "SG15")
            make_set(root, "Si", "Si-Dojo-bbbb", "Dojo-NC-SR")
            registry = load_registry(root)
            with self.assertRaises(BasisAmbiguityError) as caught:
                resolve_set(registry, "Si")
        self.assertEqual(
            caught.exception.candidate_ids(), ("Si-Dojo-bbbb", "Si-SG15-aaaa")
        )
        self.assertIn("Refusing to choose one", str(caught.exception))

    def test_an_explicit_set_id_selects_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            make_set(root, "Si", "Si-SG15-aaaa", "SG15")
            make_set(root, "Si", "Si-Dojo-bbbb", "Dojo-NC-SR")
            registry = load_registry(root)
            self.assertEqual(
                resolve_set(registry, "Si", set_id="Si-SG15-aaaa").set_id, "Si-SG15-aaaa"
            )
            with self.assertRaisesRegex(BasisRegistryError, "usable sets"):
                resolve_set(registry, "Si", set_id="Si-nope")

    def test_a_family_that_leaves_one_set_does_not_need_a_set_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            make_set(root, "Si", "Si-SG15-aaaa", "SG15")
            make_set(root, "Si", "Si-Dojo-bbbb", "Dojo-NC-SR")
            registry = load_registry(root)
            self.assertEqual(
                resolve_set(registry, "Si", family="SG15").set_id, "Si-SG15-aaaa"
            )


class BasisDisclosureTest(unittest.TestCase):
    def _fixture(self) -> tuple[pathlib.Path, dict[str, str]]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = pathlib.Path(directory.name)
        names = make_set(root, "Si", "Si-SG15-aaaa", "SG15")
        return root, names

    def test_disclosure_names_the_set_and_the_sizes(self) -> None:
        root, names = self._fixture()
        run = make_run(root, names)
        registry = load_registry(root)
        disclosure = build_basis_disclosure(run, registry=registry)
        element = disclosure["elements"]["Si"]
        self.assertEqual(element["provenance"]["set_id"], "Si-SG15-aaaa")
        self.assertTrue(element["provenance"]["matched_database_set"])
        self.assertEqual(element["payloads"]["nao"]["shells"], "2s1p")
        self.assertEqual(element["basis_dimension_per_atom"], 2 + 3)  # 2 s + 1 p
        self.assertEqual(element["payloads"]["abf"]["shells"], "3s2p1d")
        self.assertEqual(disclosure["structure"]["atom_count"], 2)
        self.assertEqual(disclosure["totals"]["nbasis"], 2 * element["basis_dimension_per_atom"])
        self.assertEqual(disclosure["status"], "DECLARED_NOT_YET_APPROVED")

    def test_a_run_bundled_basis_is_reported_as_such_not_as_a_record(self) -> None:
        root, names = self._fixture()
        run = make_run(root, names)
        disclosure = build_basis_disclosure(run, registry=None)
        provenance = disclosure["elements"]["Si"]["provenance"]
        self.assertFalse(provenance["matched_database_set"])
        self.assertEqual(provenance["source"], "run-bundled")
        self.assertIn("Si", disclosure["totals"]["elements_without_database_set"])

    def test_the_disclosure_digest_survives_writing_and_reading(self) -> None:
        root, names = self._fixture()
        run = make_run(root, names)
        disclosure = build_basis_disclosure(run, registry=load_registry(root))
        disclosure["digest"] = disclosure_digest(disclosure)
        write_disclosure(run, disclosure)
        reloaded = read_disclosure(run)
        self.assertEqual(disclosure_digest(reloaded), disclosure["digest"])
        self.assertTrue((run / DISCLOSURE_RELATIVE_PATH).is_file())

    def test_changing_one_payload_changes_the_digest(self) -> None:
        root, names = self._fixture()
        run = make_run(root, names)
        before = disclosure_digest(build_basis_disclosure(run, registry=load_registry(root)))
        target = run / pathlib.Path(names["nao"]).name
        target.write_text(target.read_text(encoding="utf-8") + "\n# tamper\n", encoding="utf-8")
        after = disclosure_digest(build_basis_disclosure(run, registry=load_registry(root)))
        self.assertNotEqual(before, after)

    def test_a_missing_payload_is_an_error_not_a_gap(self) -> None:
        root, names = self._fixture()
        run = make_run(root, names)
        (run / pathlib.Path(names["pp"]).name).unlink()
        with self.assertRaisesRegex(BasisDisclosureError, "missing from the run directory"):
            build_basis_disclosure(run, registry=load_registry(root))

    def test_the_printed_block_states_origin_and_size(self) -> None:
        root, names = self._fixture()
        run = make_run(root, names)
        disclosure = build_basis_disclosure(run, registry=load_registry(root))
        text = format_basis_disclosure(disclosure)
        self.assertIn("Si-SG15-aaaa", text)
        self.assertIn("2s1p", text)
        self.assertIn("nbasis", text)
        summary = summarise_disclosure(disclosure)
        self.assertIn("database set Si-SG15-aaaa", summary)
        self.assertIn("nbasis=", summary)

    def test_a_partial_match_is_not_reported_as_a_full_one(self) -> None:
        # The run carries an ABFS the matching set does not list: the pp and NAO
        # match, but the provenance must not claim the whole set.
        root, names = self._fixture()
        make_set(root, "Si", "Si-bare-cccc", "SG15", with_abf=False)
        run = make_run(root, names)
        registry = load_registry(root)
        disclosure = build_basis_disclosure(run, registry=registry)
        provenance = disclosure["elements"]["Si"]["provenance"]
        self.assertTrue(provenance["matched_database_set"])
        self.assertEqual(provenance["set_id"], "Si-SG15-aaaa")


if __name__ == "__main__":
    unittest.main()
