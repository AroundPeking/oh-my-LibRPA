"""The basis label must say what a person needs to decide, not a set id."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from oml_mcp.basis_label import (
    BasisLabelError,
    dimension_from_channels,
    historical_uses,
    label_for_set,
    orbital_channels,
    payload_facts,
    shell_string,
    summarise_uses,
    valence_electrons,
)


UPF = """<UPF version="2.0.1">
  <PP_HEADER>
    z_valence="    4.00"
  </PP_HEADER>
</UPF>
"""
ORB = """---------------------------------------------------------------------------
Element                     Si
Lmax                        2
Number of Sorbital-->       3
Number of Porbital-->       3
Number of Dorbital-->       2
---------------------------------------------------------------------------
SUMMARY  END
"""
ABF = """---------------------------------------------------------------------------
Element                     Si
Lmax                        8
Number of Sorbital-->       12
Number of Porbital-->       12
Number of Dorbital-->       11
Number of Forbital-->       9
Number of Gorbital-->       9
Number of Horbital-->       6
Number of Iorbital-->       4
Number of Jorbital-->       1
Number of Korbital-->       1
---------------------------------------------------------------------------
SUMMARY  END
"""


def record(record_id, material, formula, *, gap=None, gap_method="G0W0", rpa=None):
    properties = []
    if gap is not None:
        properties.append(
            {"key": "band_gap", "method": gap_method, "value": gap, "unit": "eV"}
        )
    if rpa is not None:
        properties.append(
            {"key": "rpa_cohesive_energy", "method": "RPA", "value": rpa, "unit": "eV/atom"}
        )
    return {
        "id": record_id,
        "material": material,
        "formula": formula,
        "dimension": "3d",
        "species": [{"element": "Si", "set_id": "Si-SG15-aaaa"}],
        "properties": properties,
    }


class PayloadFactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_valence_electrons_come_from_the_pseudopotential(self) -> None:
        path = self.write("Si.upf", UPF)
        self.assertEqual(valence_electrons(path), 4)
        self.assertEqual(payload_facts(path, "pp")["statement"], "4 valence electrons")

    def test_a_pseudopotential_without_z_valence_says_so_instead_of_guessing(self) -> None:
        path = self.write("weird.upf", "<UPF version='1.0'></UPF>")
        self.assertIsNone(valence_electrons(path))
        self.assertIn("not declared", payload_facts(path, "pp")["statement"])

    def test_orbital_channels_and_dimension(self) -> None:
        path = self.write("Si.orb", ORB)
        channels = orbital_channels(path)
        self.assertEqual(channels, {"S": 3, "P": 3, "D": 2})
        self.assertEqual(shell_string(channels), "3s3p2d")
        self.assertEqual(dimension_from_channels(channels), 22)

    def test_auxiliary_basis_keeps_the_high_channels(self) -> None:
        # The library index has dropped J/K for 60 auxiliary bases; the file is
        # the authority, so the label must count them.
        path = self.write("Si.abfs", ABF)
        facts = payload_facts(path, "abf")
        self.assertEqual(facts["dimension_per_atom"], 397)
        # shell_string is written from low to high l; J is 1 and K is 1
        self.assertTrue(facts["shells"].endswith("1j1k"))

    def test_an_unreadable_payload_raises_rather_than_reporting_zero(self) -> None:
        path = self.write("empty.orb", "not an orbital header\n")
        with self.assertRaisesRegex(BasisLabelError, "no angular-momentum"):
            orbital_channels(path)


class HistoricalUseTest(unittest.TestCase):
    def test_a_gw_gap_is_quoted_with_its_material(self) -> None:
        uses = historical_uses([record("si", "Si", "Si", gap=1.0596309)], "Si-SG15-aaaa")
        self.assertEqual(len(uses), 1)
        self.assertAlmostEqual(uses[0]["result_value"], 1.0596309)
        # result is the bare measurement; the material is named by the caller
        self.assertIn("GW gap 1.06 eV", uses[0]["result"])

    def test_an_rpa_record_is_described_by_its_cohesive_energy(self) -> None:
        uses = historical_uses(
            [record("si-rpa", "Si", "Si2", rpa=4.4349)], "Si-SG15-aaaa"
        )
        self.assertIn("RPA cohesive energy 4.43 eV/atom", uses[0]["result"])

    def test_a_dft_gap_is_not_presented_as_a_gw_result(self) -> None:
        uses = historical_uses(
            [record("dft", "Si", "Si", gap=0.56, gap_method="PBE")], "Si-SG15-aaaa"
        )
        self.assertIsNone(uses[0]["result"])

    def test_records_that_used_another_set_are_not_counted(self) -> None:
        other = record("x", "Si", "Si", gap=1.0)
        other["species"] = [{"element": "Si", "set_id": "Si-ONCV-bbbb"}]
        self.assertEqual(historical_uses([other], "Si-SG15-aaaa"), [])

    def test_the_usage_clause_reads_as_a_sentence(self) -> None:
        uses = historical_uses(
            [record("si", "Si", "Si", gap=1.06), record("sic", "SiC", "SiC", gap=2.26)],
            "Si-SG15-aaaa",
        )
        text = summarise_uses(uses, "Si")
        self.assertTrue(text.startswith("2 archived calculations"))
        self.assertIn("Si GW gap 1.06 eV", text)
        self.assertIn("SiC GW gap 2.26 eV", text)

    def test_no_use_is_stated_rather_than_left_blank(self) -> None:
        self.assertIn("no calculation", summarise_uses([], "Si"))


class LabelTest(unittest.TestCase):
    def facts(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        (root / "Si.upf").write_text(UPF, encoding="utf-8")
        (root / "Si.orb").write_text(ORB, encoding="utf-8")
        (root / "Si.abfs").write_text(ABF, encoding="utf-8")
        return (
            payload_facts(root / "Si.upf", "pp"),
            payload_facts(root / "Si.orb", "nao"),
            payload_facts(root / "Si.abfs", "abf"),
        )

    def test_the_sentence_states_what_a_user_asked_for(self) -> None:
        pp, nao, abf = self.facts()
        uses = historical_uses([record("si", "Si", "Si", gap=1.0596)], "Si-SG15-aaaa")
        label = label_for_set(
            "Si", valence=pp["valence_electrons"], nao=nao, abf=abf, uses=uses
        )
        sentence = label["sentence"]
        self.assertIn("4 valence electrons", sentence)
        self.assertIn("22 orbital functions per atom", sentence)
        self.assertIn("397 auxiliary functions per atom", sentence)
        self.assertIn("Si GW gap 1.06 eV", sentence)
        # and only then the identifier, which is not what the sentence is for
        self.assertNotIn("Si-SG15-aaaa", sentence)

    def test_a_structure_total_replaces_the_per_atom_size(self) -> None:
        pp, nao, abf = self.facts()
        label = label_for_set(
            "Si",
            valence=pp["valence_electrons"],
            nao=nao,
            abf=abf,
            uses=[],
            atom_count=2,
        )
        self.assertIn("44 orbital functions", label["sentence"])
        self.assertIn("794 auxiliary functions", label["sentence"])
        self.assertNotIn("per atom", label["sentence"])

    def test_method_names_and_units_keep_their_case(self) -> None:
        pp, nao, abf = self.facts()
        label = label_for_set(
            "Si",
            valence=pp["valence_electrons"],
            nao=nao,
            abf=abf,
            uses=historical_uses([record("si", "Si", "Si", gap=1.0596)], "Si-SG15-aaaa"),
        )
        self.assertIn("Si GW gap", label["sentence"])
        self.assertIn("eV", label["sentence"])


class DescribeSetTest(unittest.TestCase):
    def test_describe_set_carries_the_label_sentence(self) -> None:
        from oml_mcp.basis_registry import describe_set

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            for role, name, text in (
                ("pp", "pseudopotentials", UPF),
                ("nao", "orbitals", ORB),
                ("abf", "auxiliary", ABF),
            ):
                directory = root / "data" / "elements" / "Si" / name
                directory.mkdir(parents=True)
                (directory / f"payload{ {'pp':'.upf','nao':'.orb','abf':'.abfs'}[role] }").write_text(
                    text, encoding="utf-8"
                )
            import hashlib

            files = []
            for role, name in (
                ("pp", "pseudopotentials/payload.upf"),
                ("nao", "orbitals/payload.orb"),
                ("abf", "auxiliary/payload.abfs"),
            ):
                path = root / "data" / "elements" / "Si" / name
                files.append(
                    {
                        "role": role,
                        "path": f"data/elements/Si/{name}",
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
            set_dir = root / "data" / "elements" / "Si" / "sets" / "Si-test"
            set_dir.mkdir(parents=True)
            (set_dir / "set.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "Si-test",
                        "element": "Si",
                        "family": "SG15",
                        "files": files,
                    }
                ),
                encoding="utf-8",
            )
            from oml_mcp.basis_registry import load_registry

            registry = load_registry(root)
            described = describe_set(registry["Si"][0], records=())
        self.assertIn("4 valence electrons", described["label_sentence"])
        self.assertIn("22 orbital functions per atom", described["label_sentence"])
        self.assertEqual(described["label"]["valence_electrons"], 4)


if __name__ == "__main__":
    unittest.main()
