import dataclasses
import unittest


from oml_mcp.admission import (
    AdmissionError,
    AdmissionResources,
    build_admission_receipt,
)


class AdmissionReceiptTest(unittest.TestCase):
    def make_receipt(self, **overrides):
        arguments = {
            "campaign_id": "fisherd-v2-admission-20260830",
            "case_id": "component-librpa-headwing",
            "route_id": "strict_2d_gw",
            "profile_id": "abacus-librpa-2026-08-30-v2",
            "source_revisions": {
                "abacus": "a" * 40,
                "librpa": "b" * 40,
                "pyatb": "c" * 40,
            },
            "build_fingerprints": {
                "abacus": "d" * 64,
                "librpa": "e" * 64,
                "pyatb": "f" * 64,
            },
            "host_fingerprint": {
                "hostname": "Fisherd-Server",
                "cpu_count": 96,
            },
            "input_manifest_sha256": "1" * 64,
            "plan_digest": "2" * 64,
            "stage": "librpa_headwing_tests",
            "attempt_id": "attempt-source-l1-001",
            "started_at": "2026-08-30T01:00:00Z",
            "finished_at": "2026-08-30T01:03:00Z",
            "resources": AdmissionResources(
                compile_jobs=0,
                execution_threads=16,
                cpu_hours=0.8,
                wall_seconds=180,
                disk_bytes=4096,
            ),
            "process_status": "PASSED",
            "artifact_manifest": (
                {"path": "ctest.log", "size": 128, "sha256": "3" * 64},
            ),
            "gate_results": (
                {
                    "gate_id": "l1.librpa_headwing",
                    "status": "PASS",
                    "measurement": 0,
                    "threshold": 0,
                    "evidence": ["ctest.log"],
                },
            ),
        }
        arguments.update(overrides)
        return build_admission_receipt(**arguments)

    def test_receipt_is_deterministic_and_serializable(self):
        first = self.make_receipt()
        second = self.make_receipt()

        self.assertEqual(first, second)
        self.assertEqual(len(first.receipt_digest), 64)
        data = first.to_dict()
        self.assertEqual(data["receipt_schema"], "oml.receipt.v2")
        self.assertEqual(data["receipt_digest"], first.receipt_digest)
        self.assertEqual(data["resources"]["execution_threads"], 16)
        self.assertEqual(data["scientific_status"], "NOT_EVALUATED")
        self.assertEqual(data["promotion_eligibility"], "BLOCKED")

    def test_receipt_rejects_non_sha_build_fingerprint(self):
        fingerprints = {
            "abacus": "not-a-sha",
            "librpa": "e" * 64,
            "pyatb": "f" * 64,
        }

        with self.assertRaisesRegex(AdmissionError, "build_fingerprints.abacus"):
            self.make_receipt(build_fingerprints=fingerprints)

    def test_receipt_enforces_fisherd_resource_limits(self):
        with self.assertRaisesRegex(AdmissionError, "compile_jobs"):
            self.make_receipt(resources=AdmissionResources(compile_jobs=17))
        with self.assertRaisesRegex(AdmissionError, "execution_threads"):
            self.make_receipt(resources=AdmissionResources(execution_threads=49))

    def test_receipt_cannot_automatically_enable_a_route(self):
        with self.assertRaisesRegex(AdmissionError, "ENABLED"):
            self.make_receipt(promotion_eligibility="ENABLED")

    def test_receipt_digest_changes_with_gate_evidence(self):
        first = self.make_receipt()
        changed_gate = dict(first.payload["gate_results"][0])
        changed_gate["status"] = "FAIL"
        second = self.make_receipt(gate_results=(changed_gate,))

        self.assertNotEqual(first.receipt_digest, second.receipt_digest)

    def test_resource_dataclass_is_immutable(self):
        resources = AdmissionResources(execution_threads=2)

        with self.assertRaises(dataclasses.FrozenInstanceError):
            resources.execution_threads = 4


if __name__ == "__main__":
    unittest.main()
