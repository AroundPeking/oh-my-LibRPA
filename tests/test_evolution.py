import unittest


from oml_mcp.evolution import (
    ROUTE_MUTATION_AXES,
    CandidateProposal,
    EvolutionBudget,
    EvolutionError,
    EvolutionUsage,
    propose_candidate,
)
from oml_mcp.profiles import V2_PROFILE_ID, load_profile


class EvolutionPolicyTest(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "nfreq": 32,
            "nbands": 48,
            "screening_kgrid": [4, 4, 4],
            "structure_sha256": "a" * 64,
            "reader_format": "v1",
        }
        self.candidate = {**self.baseline, "nfreq": 48}
        self.budget = EvolutionBudget(
            max_candidates=8,
            cpu_hours=100.0,
            wall_seconds=86400,
            disk_bytes=10_000_000_000,
        )
        self.usage = EvolutionUsage(
            candidates=1,
            cpu_hours=10.0,
            wall_seconds=3600,
            disk_bytes=1_000_000,
        )

    def propose(self, **overrides) -> CandidateProposal:
        arguments = {
            "route_id": "periodic_3d_gw",
            "baseline": self.baseline,
            "candidate": self.candidate,
            "existing_definition_digests": frozenset(),
            "budget": self.budget,
            "usage": self.usage,
        }
        arguments.update(overrides)
        return propose_candidate(**arguments)

    def test_route_registry_contains_only_the_four_admission_routes(self):
        self.assertEqual(
            set(ROUTE_MUTATION_AXES),
            set(load_profile(profile_id=V2_PROFILE_ID)["capabilities"]),
        )
        self.assertNotIn("direct_mixed_fourier", ROUTE_MUTATION_AXES)

    def test_one_registered_axis_returns_a_proposal_only_record(self):
        proposal = self.propose()

        self.assertEqual(proposal.status, "PROPOSAL_ONLY")
        self.assertEqual(proposal.changed_axis, "nfreq")
        self.assertEqual(proposal.candidate["nfreq"], 48)
        self.assertEqual(len(proposal.definition_digest), 64)
        self.assertNotIn("command", proposal.to_dict())
        self.assertNotIn("submit", proposal.to_dict())

    def test_definition_digest_is_deterministic(self):
        self.assertEqual(self.propose(), self.propose())

    def test_two_changed_axes_are_rejected(self):
        candidate = {**self.candidate, "nbands": 64}

        with self.assertRaisesRegex(EvolutionError, "exactly one"):
            self.propose(candidate=candidate)

    def test_unregistered_changed_axis_is_rejected(self):
        candidate = {**self.baseline, "reader_format": "legacy"}

        with self.assertRaisesRegex(EvolutionError, "not registered"):
            self.propose(candidate=candidate)

    def test_existing_definition_is_not_proposed_twice(self):
        proposal = self.propose()

        with self.assertRaisesRegex(EvolutionError, "duplicate"):
            self.propose(
                existing_definition_digests=frozenset({proposal.definition_digest})
            )

    def test_exhausted_candidate_cpu_wall_and_disk_budgets_are_rejected(self):
        exhausted = (
            EvolutionUsage(
                candidates=self.budget.max_candidates,
                cpu_hours=0,
                wall_seconds=0,
                disk_bytes=0,
            ),
            EvolutionUsage(
                candidates=0,
                cpu_hours=self.budget.cpu_hours,
                wall_seconds=0,
                disk_bytes=0,
            ),
            EvolutionUsage(
                candidates=0,
                cpu_hours=0,
                wall_seconds=self.budget.wall_seconds,
                disk_bytes=0,
            ),
            EvolutionUsage(
                candidates=0,
                cpu_hours=0,
                wall_seconds=0,
                disk_bytes=self.budget.disk_bytes,
            ),
        )

        for usage in exhausted:
            with self.subTest(usage=usage):
                with self.assertRaisesRegex(EvolutionError, "budget"):
                    self.propose(usage=usage)

    def test_unknown_route_is_rejected(self):
        with self.assertRaisesRegex(EvolutionError, "route"):
            self.propose(route_id="strict_2d_direct_mixed_fourier")


if __name__ == "__main__":
    unittest.main()
