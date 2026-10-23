import json
import pathlib
import tempfile
import unittest

from oml_mcp.reference_query import (
    ReferenceQueryError,
    find_reference_records,
    load_records,
    trust_reasons,
)


DIGEST = "a" * 64


def make_record(
    root: pathlib.Path,
    *,
    record_id: str,
    structure_sha256: str = DIGEST,
    status: str = "validated",
    include_aux: bool = True,
) -> pathlib.Path:
    directory = root / "data" / "calculations" / "3d" / "C" / record_id
    (directory / "inputs").mkdir(parents=True)
    (directory / "inputs" / "INPUT").write_text("INPUT_PARAMETERS\n", encoding="utf-8")
    record = {
        "schema_version": 1,
        "id": record_id,
        "material": "C",
        "dimension": "3d",
        "record_type": "band",
        "structure_identity": {
            "algorithm": "cell-sites-v1",
            "sha256": structure_sha256,
            "evidence": f"data/calculations/3d/C/{record_id}/inputs/INPUT",
        },
        "properties": [{"key": "gap", "status": status}],
        "software": {
            "abacus": {"commit": "1" * 40},
            "librpa": {"executable_sha256": "2" * 64},
        },
        "species": [{"element": "C", "set_id": "C-set"}],
        "auxiliary_basis": {"mode": "pca_generated", "threshold": 1e-4} if include_aux else None,
        "files": {"inputs": [{"path": f"data/calculations/3d/C/{record_id}/inputs/INPUT"}]},
    }
    path = directory / "record.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


class ReferenceQueryTest(unittest.TestCase):
    def _root(self) -> pathlib.Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return pathlib.Path(directory.name)

    def test_trusted_record_passes_the_gate(self):
        root = self._root()
        make_record(root, record_id="trusted")
        record = load_records(root)[0][0]
        self.assertEqual(trust_reasons(record), ())

    def test_reported_property_is_untrusted(self):
        root = self._root()
        make_record(root, record_id="reported", status="reported")
        record = load_records(root)[0][0]
        self.assertIn("no validated property", trust_reasons(record))

    def test_missing_auxiliary_basis_is_untrusted(self):
        root = self._root()
        make_record(root, record_id="no-aux", include_aux=False)
        record = load_records(root)[0][0]
        self.assertIn("auxiliary-basis provenance is not recorded", trust_reasons(record))

    def test_find_returns_trusted_first_and_ignores_other_structures(self):
        root = self._root()
        make_record(root, record_id="b-reported", status="reported")
        make_record(root, record_id="a-trusted")
        make_record(root, record_id="other", structure_sha256="b" * 64)
        matches = find_reference_records(root, structure_sha256=DIGEST)
        self.assertEqual([match.record_id for match in matches], ["a-trusted", "b-reported"])
        self.assertTrue(matches[0].trustworthy)
        self.assertFalse(matches[1].trustworthy)

    def test_record_type_filter(self):
        root = self._root()
        make_record(root, record_id="band-case")
        self.assertEqual(
            find_reference_records(root, structure_sha256=DIGEST, record_type="rpa_energy"), ()
        )

    def test_missing_database_is_an_error(self):
        with self.assertRaises(ReferenceQueryError):
            load_records(self._root() / "missing")


if __name__ == "__main__":
    unittest.main()
