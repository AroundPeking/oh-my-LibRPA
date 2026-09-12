import pathlib
import tempfile
import unittest

from oml_mcp.fast_benchmark import (
    CaseValidator,
    FastCase,
    FastCaseError,
    aggregate_fast_results,
    evaluate_case_against_reference,
    list_fast_cases,
    load_fast_case,
    select_fast_cases,
)


REFERENCE_OUT = """
GW bandgap(eV):   6.1400000
EXX bandgap(eV):   9.1200000
DFT bandgap(eV):   4.3300000
"""


def _bn_case() -> FastCase:
    return load_fast_case("bn-3d-sym-shrink-g0w0")


class FastCaseRegistryTest(unittest.TestCase):
    def test_registry_loads_and_declares_references(self):
        cases = list_fast_cases()

        self.assertGreaterEqual(len(cases), 8)
        ids = {case.case_id for case in cases}
        self.assertIn("bn-3d-sym-shrink-g0w0", ids)
        self.assertIn("mno2-nspin2-shrink-wing-g0w0", ids)

    def test_full_pipeline_cases_are_evaluable(self):
        full = [
            case
            for case in select_fast_cases(evaluable_only=True)
            if len(case.stages) == 5
        ]

        # The fast benchmark must actually run the whole pipeline, not just read files.
        self.assertGreaterEqual(len(full), 4)
        for case in full:
            self.assertEqual(
                case.stages, ("scf", "pyatb", "nscf", "preprocess", "librpa")
            )

    def test_legacy_handoff_cases_are_not_evaluable(self):
        case = load_fast_case("bn-3d-headwing-g0w0")

        self.assertEqual(case.reference_status, "LEGACY_HANDOFF")
        self.assertFalse(case.evaluable)

    def test_load_rejects_unknown_case(self):
        with self.assertRaisesRegex(FastCaseError, "not available"):
            load_fast_case("nonexistent-case")

    def test_all_cases_are_fast(self):
        # "fast" is the whole point: every registered case must be seconds-to-minutes.
        for case in list_fast_cases():
            self.assertLessEqual(case.estimated_seconds, 300, case.case_id)

    def test_case_selection_filters(self):
        solid_gw = select_fast_cases(task="gw", system_type="solid")

        self.assertTrue(solid_gw)
        for case in solid_gw:
            self.assertEqual(case.task, "gw")
            self.assertEqual(case.system_type, "solid")


class FastCaseEvaluationTest(unittest.TestCase):
    def test_matching_output_passes(self):
        case = _bn_case()
        reference = {"librpa.out": REFERENCE_OUT}
        observed = {"librpa.out": REFERENCE_OUT}

        result = evaluate_case_against_reference(case, reference, observed)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["promotion_eligibility"], "ENABLED")

    def test_within_tolerance_passes(self):
        case = _bn_case()
        reference = {"librpa.out": REFERENCE_OUT}
        observed = {
            "librpa.out": REFERENCE_OUT.replace("6.1400000", "6.1400500")
        }

        result = evaluate_case_against_reference(case, reference, observed)

        self.assertEqual(result["status"], "PASS")

    def test_beyond_tolerance_fails(self):
        case = _bn_case()
        reference = {"librpa.out": REFERENCE_OUT}
        observed = {
            "librpa.out": REFERENCE_OUT.replace("6.1400000", "6.2400000")
        }

        result = evaluate_case_against_reference(case, reference, observed)

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reason_code"], "REFERENCE_TOLERANCE_EXCEEDED")
        self.assertEqual(result["promotion_eligibility"], "BLOCKED")

    def test_missing_reference_is_not_evaluated_never_passes(self):
        case = _bn_case()
        observed = {"librpa.out": REFERENCE_OUT}

        result = evaluate_case_against_reference(case, {}, observed)

        self.assertEqual(result["status"], "NOT_EVALUATED")
        self.assertNotEqual(result["status"], "PASS")

    def test_non_evaluable_case_never_passes(self):
        case = load_fast_case("bn-3d-headwing-g0w0")

        result = evaluate_case_against_reference(
            case, {"librpa.out": REFERENCE_OUT}, {"librpa.out": REFERENCE_OUT}
        )

        self.assertEqual(result["status"], "NOT_EVALUATED")
        self.assertIn("LEGACY_HANDOFF", result["reason_code"])

    def test_validator_rejects_regex_without_capture_group(self):
        with self.assertRaisesRegex(FastCaseError, "capture"):
            CaseValidator(name="bad", regex=r"GW bandgap\(eV\)")

    def test_aggregate_fails_when_any_case_fails(self):
        results = [
            {"case_id": "a", "status": "PASS"},
            {"case_id": "b", "status": "FAIL"},
        ]

        aggregate = aggregate_fast_results(results)

        self.assertEqual(aggregate["status"], "FAIL")
        self.assertEqual(aggregate["failed_cases"], ["b"])

    def test_aggregate_not_evaluated_when_any_case_unevaluated(self):
        results = [
            {"case_id": "a", "status": "PASS"},
            {"case_id": "b", "status": "NOT_EVALUATED"},
        ]

        aggregate = aggregate_fast_results(results)

        self.assertEqual(aggregate["status"], "NOT_EVALUATED")

    def test_aggregate_passes_only_when_all_pass(self):
        results = [
            {"case_id": "a", "status": "PASS"},
            {"case_id": "b", "status": "PASS"},
        ]

        aggregate = aggregate_fast_results(results)

        self.assertEqual(aggregate["status"], "PASS")


if __name__ == "__main__":
    unittest.main()


class SequenceLengthTest(unittest.TestCase):
    def test_sequence_length_mismatch_fails_instead_of_truncating(self):
        from oml_mcp.fast_benchmark import CaseValidator, evaluate_case_against_reference, load_fast_case

        case = load_fast_case("si-band-aims-g0w0")
        reference_text = "\n".join(f"{i} 0.0 0.0 0.0 1.0 {1.0 + i} 0.0 {10.0 + i}" for i in range(5))
        observed_text = "\n".join(f"{i} 0.0 0.0 0.0 1.0 {1.0 + i} 0.0 {10.0 + i}" for i in range(4))
        validator = case.validators[0]

        exx = case.validators[1].file
        result = evaluate_case_against_reference(
            case,
            {validator.file: reference_text, exx: reference_text},
            {validator.file: observed_text, exx: observed_text},
        )

        self.assertEqual(result["status"], "FAIL")
        report = next(r for r in result["validators"] if r["name"] == validator.name)
        self.assertEqual(report["reason"], "SEQUENCE_LENGTH_MISMATCH")
        self.assertEqual(report["reference_count"], 5 * 7)
        self.assertEqual(report["observed_count"], 4 * 7)

    def test_matching_sequence_within_tolerance_passes(self):
        from oml_mcp.fast_benchmark import evaluate_case_against_reference, load_fast_case

        case = load_fast_case("si-band-aims-g0w0")
        validator = case.validators[0]
        text = "\n".join(f"{i} 0.0 0.0 0.0 1.0 {1.0 + i} 0.0 {10.0 + i}" for i in range(5))

        exx = case.validators[1].file
        result = evaluate_case_against_reference(
            case,
            {validator.file: text, exx: text},
            {validator.file: text.replace("10.0", "10.00001"), exx: text},
        )

        self.assertEqual(result["status"], "PASS", result)
