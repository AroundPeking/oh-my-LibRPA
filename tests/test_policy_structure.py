import unittest

from oml_mcp.policy_gates import (
    FAIL,
    GATE_IMPLEMENTATIONS,
    NOT_EVALUATED,
    PASS,
    check_abfs_contract,
    check_basis_source,
    check_kpoint_standard,
)
from oml_mcp.policies import (
    EffectiveDefinition,
    PolicyError,
    load_policies,
    merge_layers,
    policy_ids,
)
from oml_mcp.preflight import preflight
from oml_mcp.references import (
    ReferenceError,
    physical_from_record,
    physical_reference,
    replay_reference,
    verdict,
)


class PolicyRegistryTest(unittest.TestCase):
    def test_loads_the_three_production_policies(self):
        policies = load_policies()
        self.assertEqual(policy_ids(policies), ("abfs_contract", "basis_source", "kpoint_standard"))
        for policy in policies:
            self.assertEqual(policy.on_violation, "fail_closed")

    def test_every_policy_is_enforced_by_a_gate(self):
        for policy in load_policies():
            with self.subTest(policy=policy.id):
                self.assertIn(policy.enforcement_id, GATE_IMPLEMENTATIONS)

    def test_sources_are_dated(self):
        for policy in load_policies():
            for source in policy.sources:
                self.assertRegex(source["accessed"], r"^\d{4}-\d{2}-\d{2}$")


class EffectiveDefinitionTest(unittest.TestCase):
    def test_layers_are_recorded_in_order(self):
        definition = merge_layers(
            ("case", {"nfreq": 8, "nbands": 26}),
            ("seed", {"nfreq": 24}),
            ("policy", {"scf_kgrid": [8, 8, 8]}),
        )
        self.assertEqual(definition.values["nfreq"], 24)
        self.assertEqual(definition.provenance["nfreq"], ("case", "seed"))
        self.assertEqual(definition.provenance["scf_kgrid"], ("policy",))
        self.assertEqual(definition.provenance["nbands"], ("case",))

    def test_with_layer_appends_provenance(self):
        definition = EffectiveDefinition(values={}, provenance={})
        definition = definition.with_layer("seed", {"nfreq": 24})
        definition = definition.with_layer("retry", {"nfreq": 16})
        self.assertEqual(definition.values["nfreq"], 16)
        self.assertEqual(definition.provenance["nfreq"], ("seed", "retry"))


class PolicyGatesTest(unittest.TestCase):
    def test_basis_source(self):
        self.assertEqual(check_basis_source(database_basis=True).status, PASS)
        self.assertEqual(check_basis_source(database_basis=False).status, FAIL)
        missing = check_basis_source(database_basis=True, missing_elements=("Te",))
        self.assertEqual(missing.status, FAIL)
        self.assertIn("abacus-librpa-gw-basis-skill", missing.repair)
        self.assertEqual(check_basis_source(database_basis=True, mode="replay").status, NOT_EVALUATED)

    def test_kpoint_standard(self):
        self.assertEqual(check_kpoint_standard(scf_kgrid=[8, 8, 8], dimension="3d").status, PASS)
        self.assertEqual(check_kpoint_standard(scf_kgrid=[12, 12, 12], dimension="3d").status, PASS)
        self.assertEqual(check_kpoint_standard(scf_kgrid=[4, 4, 4], dimension="3d").status, FAIL)
        self.assertEqual(check_kpoint_standard(scf_kgrid=[12, 12, 1], dimension="2d").status, PASS)
        self.assertEqual(check_kpoint_standard(scf_kgrid=[12, 12, 2], dimension="2d").status, FAIL)
        self.assertEqual(check_kpoint_standard(scf_kgrid=[4, 4, 4], dimension="3d", mode="replay").status, NOT_EVALUATED)

    def test_abfs_contract(self):
        self.assertEqual(
            check_abfs_contract(abfs_orbital=True, exx_pca_threshold=10.0, use_shrink_abfs=True).status,
            PASS,
        )
        self.assertEqual(
            check_abfs_contract(abfs_orbital=True, exx_pca_threshold=1e-3, use_shrink_abfs=True).status,
            FAIL,
        )
        self.assertEqual(
            check_abfs_contract(abfs_orbital=True, exx_pca_threshold=10.0, use_shrink_abfs=False).status,
            FAIL,
        )
        self.assertEqual(
            check_abfs_contract(abfs_orbital=False, exx_pca_threshold=None, use_shrink_abfs=None).status,
            PASS,
        )


class ReferenceVerdictTest(unittest.TestCase):
    def test_physical_claims_require_a_physical_reference(self):
        validated = physical_reference(6.324, source="db:bn-paper-sg15", scope="same geometry", status="validated")
        accepted = verdict(gates_ok=True, value=6.30, references=[validated])
        self.assertEqual(accepted["verdict"], "ACCEPTED_PHYSICAL")
        reported = physical_reference(6.324, source="db:bn-paper-sg15", scope="same geometry", status="reported")
        accepted_reference = verdict(gates_ok=True, value=6.30, references=[reported])
        self.assertEqual(accepted_reference["verdict"], "ACCEPTED_REFERENCE")
        rejected = verdict(gates_ok=True, value=6.03, references=[validated])
        self.assertEqual(rejected["verdict"], "REJECTED_PHYSICAL")

    def test_replay_only_cannot_be_a_physical_claim(self):
        replay = replay_reference(6.0003, source="fast-case:bn-k222")
        result = verdict(gates_ok=True, value=5.997, references=[replay])
        self.assertEqual(result["verdict"], "REPRODUCED_REPLAY")

    def test_no_reference_is_inconclusive(self):
        self.assertEqual(verdict(gates_ok=True, value=6.0, references=[])["verdict"], "INCONCLUSIVE")
        self.assertEqual(verdict(gates_ok=False, value=6.0, references=[])["verdict"], "REJECTED_GATES")

    def test_physical_from_record(self):
        record = {
            "id": "bn-paper-sg15",
            "properties": [{"status": "reported"}],
            "summary": {"value": 6.3242668, "scope": "same geometry"},
        }
        reference = physical_from_record(record)
        self.assertIsNotNone(reference)
        self.assertEqual(reference.kind, "physical")
        self.assertEqual(reference.status, "reported")
        self.assertEqual(reference.value, 6.3242668)
        self.assertIsNone(physical_from_record({"id": "x", "summary": {}}))

    def test_invalid_reference_is_rejected(self):
        with self.assertRaises(ReferenceError):
            physical_reference(6.0, source="x", scope="y", status="regression")


class PreflightTest(unittest.TestCase):
    def test_all_gates_pass_with_a_physical_reference(self):
        reference = physical_reference(6.324, source="db:bn-paper-sg15", scope="same geometry", status="reported")
        result = preflight(
            database_basis=True,
            scf_kgrid=[8, 8, 8],
            dimension="3d",
            abfs_orbital=True,
            exx_pca_threshold=10.0,
            use_shrink_abfs=True,
            value=6.30,
            references=[reference],
        )
        self.assertTrue(result.ok, result.reasons)
        self.assertEqual(result.reference_verdict["verdict"], "ACCEPTED_REFERENCE")

    def test_case_basis_fails_preflight(self):
        result = preflight(
            database_basis=False,
            scf_kgrid=[8, 8, 8],
            dimension="3d",
            abfs_orbital=True,
            exx_pca_threshold=10.0,
            use_shrink_abfs=True,
        )
        self.assertFalse(result.ok)
        self.assertTrue(any("policy.basis_source" in reason for reason in result.reasons))

    def test_physical_claim_without_a_physical_reference_fails(self):
        result = preflight(
            database_basis=True,
            scf_kgrid=[8, 8, 8],
            dimension="3d",
            abfs_orbital=True,
            exx_pca_threshold=10.0,
            use_shrink_abfs=True,
            require_physical=True,
            references=[replay_reference(6.0, source="replay")],
        )
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
