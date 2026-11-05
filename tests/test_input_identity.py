import json
import tempfile
import unittest
from pathlib import Path

from oml_mcp.basis_registry import BasisAsset, ElementSet
from oml_mcp.input_identity import (
    compare_basis,
    element_for_name,
    expected_basis_hashes,
    file_sha256,
    observed_basis,
    role_for_name,
)
from oml_mcp.policy_gates import FAIL, NOT_EVALUATED, PASS, check_basis_identity


def _asset(role: str, path: Path) -> BasisAsset:
    return BasisAsset(role=role, path=path, sha256=file_sha256(path))


class InputIdentityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.case = self.root / "case"
        self.case.mkdir()
        (self.case / "B_gga_8au_100Ry_3s3p2d.orb").write_bytes(b"nao-b")
        (self.case / "N_gga_8au_100Ry_3s3p2d.orb").write_bytes(b"nao-n")
        (self.case / "B_ONCV_PBE-1.0.upf").write_bytes(b"pp-b")
        (self.case / "N_ONCV_PBE-1.0.upf").write_bytes(b"pp-n")
        (self.case / "B_3s3p2d1f1g_pca1e-6.abfs").write_bytes(b"abf-b")
        (self.case / "N_3s3p2d1f1g_pca1e-6.abfs").write_bytes(b"abf-n")

    def tearDown(self):
        self.tmp.cleanup()

    def _sets(self):
        def one(element: str, nao: str, abf: str) -> ElementSet:
            files = {
                "pp": _asset("pp", self.case / f"{element}_ONCV_PBE-1.0.upf"),
                "nao": _asset("nao", self.case / nao),
                "abf": _asset("abf", self.case / abf),
            }
            return ElementSet(
                set_id=f"{element}-SG15",
                element=element,
                family="SG15",
                validation_scope=None,
                files=files,
            )

        return {"B": one("B", "B_gga_8au_100Ry_3s3p2d.orb", "B_3s3p2d1f1g_pca1e-6.abfs"),
                "N": one("N", "N_gga_8au_100Ry_3s3p2d.orb", "N_3s3p2d1f1g_pca1e-6.abfs")}

    def test_role_and_element_attribution(self):
        self.assertEqual(role_for_name("B_gga_8au_100Ry_3s3p2d.orb"), "nao")
        self.assertEqual(role_for_name("B_3s3p2d1f1g_pca1e-6.abfs"), "abf")
        self.assertEqual(role_for_name("B_ONCV_PBE-1.0.upf"), "pp")
        self.assertEqual(element_for_name("B_gga.orb", ["B", "N"]), "B")
        self.assertEqual(element_for_name("Bi_gga.orb", ["B", "Bi"]), "Bi")

    def test_observed_basis_reports_duplicates(self):
        (self.case / "B_gga_8au_100Ry_2s2p1d.orb").write_bytes(b"other-nao")
        observed = observed_basis(self.case, ["B", "N"])
        self.assertEqual(observed.by_element(), ("B", "N"))
        self.assertIn("B/nao", observed.duplicates)

    def test_matching_payloads_pass_and_mismatch_fails(self):
        observed = observed_basis(self.case, ["B", "N"])
        expected = expected_basis_hashes(self._sets())
        self.assertEqual(compare_basis(expected, observed), [])
        self.assertEqual(
            check_basis_identity(expected_basis=expected, observed_basis=observed.hashes).status,
            PASS,
        )
        (self.case / "B_gga_8au_100Ry_3s3p2d.orb").write_bytes(b"nao-b-swapped")
        observed = observed_basis(self.case, ["B", "N"])
        problems = compare_basis(expected, observed)
        self.assertTrue(any("B/nao" in problem for problem in problems))
        finding = check_basis_identity(expected_basis=expected, observed_basis=observed.hashes)
        self.assertEqual(finding.status, FAIL)
        self.assertIn("B/nao", finding.message)

    def test_missing_payload_and_unresolved_set(self):
        expected = expected_basis_hashes(self._sets())
        observed = observed_basis(self.case, ["B", "N"])
        observed.hashes.pop("N/abf")
        self.assertEqual(
            check_basis_identity(expected_basis=expected, observed_basis=observed.hashes).status,
            FAIL,
        )
        self.assertEqual(
            check_basis_identity(expected_basis=None, observed_basis=observed.hashes).status,
            NOT_EVALUATED,
        )

    def test_identity_gate_is_not_relaxed_in_replay(self):
        expected = {"B/nao": "a" * 64}
        observed = {"B/nao": "b" * 64}
        self.assertEqual(
            check_basis_identity(
                expected_basis=expected, observed_basis=observed, mode="replay"
            ).status,
            FAIL,
        )


if __name__ == "__main__":
    unittest.main()
