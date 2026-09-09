import copy
import pathlib
import unittest


from oml_mcp.material_class import (
    MaterialClassError,
    list_material_classes,
    load_material_class,
    validate_material_class,
)
from oml_mcp.server import build_server


class MaterialClassTest(unittest.TestCase):
    def test_all_material_classes_are_registered_and_packaged(self):
        self.assertEqual(
            list_material_classes(),
            (
                "perovskite_gw",
                "transition_metal_oxide_gw",
                "altermagnet_gw",
                "soc_2d_gw",
            ),
        )
        root = pathlib.Path(__file__).resolve().parents[1]
        for material_class_id in list_material_classes():
            entry = load_material_class(material_class_id)
            repository = (
                root / "benchmarks" / "materials" / f"{material_class_id}.json"
            ).read_bytes()
            packaged = (
                root
                / "oml_mcp"
                / "material_classes"
                / f"{material_class_id}.json"
            ).read_bytes()
            self.assertEqual(packaged, repository)
            self.assertEqual(entry["material_class_id"], material_class_id)

    def test_pending_entries_need_no_input_hash_tree_or_software_identity(self):
        pending = ("perovskite_gw", "transition_metal_oxide_gw", "soc_2d_gw")
        for material_class_id in pending:
            entry = load_material_class(material_class_id)
            self.assertEqual(entry["reference_status"], "REFERENCE_PENDING")
            self.assertIsNone(entry["reference"])
            # A pending entry may freeze the asset hashes without freezing the
            # input-file hash tree or the software binaries.
            self.assertIn("pseudopotentials", entry["material"])
            self.assertIn("orbitals", entry["material"])

    def test_altermagnet_freezes_identity_but_reference_is_pending(self):
        # The altermagnet identity freezes the input-file hash tree and the
        # software binaries (reproducible identity/asset data). But the single
        # numeric gap (job 2485499) is a non-reproducible number on a stack the
        # frozen compatibility build cannot run, so the reference is PENDING:
        # it is not a valid GW convergence reference.
        entry = load_material_class("altermagnet_gw")
        self.assertEqual(entry["reference_status"], "REFERENCE_PENDING")
        self.assertIsNone(entry["reference"])
        self.assertIn("identity_sha256", entry["material"])
        self.assertIn("STRU", entry["material"]["identity_sha256"])
        software = entry["software_identity"]
        self.assertEqual(
            len(software["abacus_revision"]), 40
        )
        self.assertEqual(len(software["abacus_executable_sha256"]), 64)
        self.assertEqual(len(software["librpa_executable_sha256"]), 64)

    def test_material_class_identities_freeze_expected_formulas_and_magnetic_order(self):
        perovskite = load_material_class("perovskite_gw")
        tmo = load_material_class("transition_metal_oxide_gw")
        altermagnet = load_material_class("altermagnet_gw")
        soc = load_material_class("soc_2d_gw")

        self.assertEqual(perovskite["material"]["formula"], "SrTiO3")
        self.assertEqual(perovskite["material"]["magnetic_order"]["nspin"], 1)
        self.assertEqual(perovskite["material"]["magnetic_order"]["type"], "none")

        self.assertEqual(tmo["material"]["formula"], "NiO")
        self.assertEqual(tmo["material"]["magnetic_order"]["type"], "antiferromagnetic")
        self.assertEqual(tmo["material"]["magnetic_order"]["nspin"], 2)

        self.assertEqual(altermagnet["material"]["formula"], "alpha-MnTe")
        self.assertEqual(altermagnet["material"]["magnetic_order"]["type"], "collinear")
        self.assertEqual(altermagnet["material"]["magnetic_order"]["nspin"], 2)

        self.assertEqual(soc["material"]["formula"], "WSe2")
        self.assertEqual(soc["material"]["magnetic_order"]["type"], "none")
        self.assertEqual(soc["material"]["magnetic_order"]["nspin"], 1)

    def test_perovskite_and_tmo_require_abfs_before_reference(self):
        perovskite = load_material_class("perovskite_gw")
        tmo = load_material_class("transition_metal_oxide_gw")

        self.assertIsNone(perovskite["material"]["auxiliary_bases"])
        self.assertIsNone(tmo["material"]["auxiliary_bases"])
        self.assertEqual(perovskite["material"]["basis_family"], "dojo_nc_sr_tzdp")
        self.assertEqual(tmo["material"]["basis_family"], "dojo_nc_sr_tzdp")

    def test_altermagnet_and_soc_freeze_abfs_and_asset_hashes(self):
        altermagnet = load_material_class("altermagnet_gw")
        soc = load_material_class("soc_2d_gw")

        self.assertEqual(len(altermagnet["material"]["auxiliary_bases"]), 2)
        self.assertEqual(len(soc["material"]["auxiliary_bases"]), 2)
        self.assertEqual(len(altermagnet["material"]["pseudopotentials"]), 2)
        self.assertEqual(len(soc["material"]["pseudopotentials"]), 2)
        self.assertEqual(len(altermagnet["material"]["orbitals"]), 2)
        self.assertEqual(len(soc["material"]["orbitals"]), 2)

    def test_unknown_material_class_is_rejected(self):
        with self.assertRaisesRegex(MaterialClassError, "unknown material class"):
            load_material_class("no-such-material")

    def test_schema_rejects_mismatched_schema_tag(self):
        entry = load_material_class("perovskite_gw")
        drifted = copy.deepcopy(entry)
        drifted["schema"] = "oml.material-class.v2"
        with self.assertRaisesRegex(MaterialClassError, "schema"):
            validate_material_class(drifted)

    def test_schema_rejects_mismatched_reference_status(self):
        entry = load_material_class("perovskite_gw")
        drifted = copy.deepcopy(entry)
        # A frozen reference object with a REFERENCE_PENDING status is inconsistent.
        drifted["reference"] = {"source": "df"}
        with self.assertRaisesRegex(MaterialClassError, "reference_status"):
            validate_material_class(drifted)

    def test_schema_rejects_invalid_magnetic_order_nspin(self):
        entry = load_material_class("perovskite_gw")
        drifted = copy.deepcopy(entry)
        drifted["material"]["magnetic_order"]["nspin"] = 2
        with self.assertRaisesRegex(MaterialClassError, "nspin"):
            validate_material_class(drifted)

    def test_schema_rejects_missing_required_asset_group(self):
        entry = load_material_class("perovskite_gw")
        drifted = copy.deepcopy(entry)
        drifted["material"]["pseudopotentials"] = None
        with self.assertRaisesRegex(MaterialClassError, "pseudopotentials"):
            validate_material_class(drifted)

    def test_schema_rejects_short_git_revision_for_frozen_reference(self):
        entry = load_material_class("soc_2d_gw")
        drifted = copy.deepcopy(entry)
        # Promote to a frozen reference. The short abacus revision tag and null
        # executable hashes must then be rejected by the software identity check.
        drifted["reference_status"] = "REFERENCE_AVAILABLE"
        drifted["reference"] = {"source": "df"}
        drifted["material"]["identity_sha256"] = {"STRU": "a" * 64}
        with self.assertRaisesRegex(MaterialClassError, "software_identity"):
            validate_material_class(drifted)


class MaterialClassServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_lists_and_inspects_material_classes(self):
        server = build_server()
        listed = await server.call_tool(
            "list_material_classes",
            {},
        )
        inspected = await server.call_tool(
            "inspect_material_class",
            {"material_class_id": "altermagnet_gw"},
        )

        self.assertFalse(listed.is_error, listed.content)
        self.assertIn("altermagnet_gw", listed.structured_content["material_classes"])
        self.assertFalse(inspected.is_error, inspected.content)
        self.assertEqual(inspected.structured_content["material_class_id"], "altermagnet_gw")
        self.assertEqual(inspected.structured_content["reference_status"], "REFERENCE_PENDING")

    async def test_mcp_inspect_material_class_rejects_unknown_id(self):
        with self.assertRaises(Exception) as ctx:
            await build_server().call_tool(
                "inspect_material_class",
                {"material_class_id": "no-such-material"},
            )
        self.assertIn("unknown material class", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
