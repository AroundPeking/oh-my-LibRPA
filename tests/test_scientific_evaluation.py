import copy
import unittest


from oml_mcp.provenance import digest_json
from oml_mcp.scientific_evaluation import evaluate_regression


def definition(*, nfreq: int = 6) -> dict:
    content = {
        "schema_version": 1,
        "profile_id": "pinned-stack",
        "software": {"revisions": {"librpa": "a" * 40}},
        "librpa": {"nfreq": nfreq},
    }
    return {**content, "digest": digest_json(content)}


def state(kpoint, band, ks, exx, gw) -> dict:
    return {
        "spin": 1,
        "kpoint": list(kpoint),
        "band": band,
        "occupation": 2.0 if band <= 4 else 0.0,
        "ks_ev": ks,
        "exx_ev": exx,
        "gw_ev": gw,
    }


def scientific_result(*, nfreq: int = 6) -> dict:
    states = [
        state((0.0, 0.0, 0.0), 4, -2.0, -2.5, -1.5),
        state((0.0, 0.0, 0.0), 5, 0.5, 0.8, 1.0),
        state((0.5, 0.0, 0.5), 4, -1.8, -2.3, -1.2),
        state((0.5, 0.0, 0.5), 5, 0.2, 0.6, 0.4),
    ]
    return {
        "definition": definition(nfreq=nfreq),
        "window": {
            "vbm_band": 4,
            "cbm_band": 5,
            "band_start": 4,
            "band_stop": 5,
            "state_count": 4,
            "states": states,
            "fundamental_gw_gap_ev": 1.6,
        },
        "diagnostics": {"accepted": True, "failure_count": 0, "failures": []},
    }


def shifted(result: dict, *, quantity: str, delta: float) -> dict:
    changed = copy.deepcopy(result)
    changed["window"]["states"][0][f"{quantity}_ev"] += delta
    return changed


class ScientificRegressionTest(unittest.TestCase):
    def test_exact_1_mev_boundary_passes_and_reports_worst_state(self):
        reference = scientific_result()
        candidate = shifted(reference, quantity="gw", delta=0.001)

        report = evaluate_regression(candidate, reference, tolerance_ev=0.001)

        self.assertEqual(report["status"], "PASS")
        self.assertAlmostEqual(report["quantities"]["gw"]["max_abs_error_ev"], 0.001)
        self.assertEqual(report["quantities"]["gw"]["worst_state"]["band"], 4)
        self.assertEqual(report["state_count"], 4)

    def test_just_over_1_mev_fails(self):
        reference = scientific_result()
        candidate = shifted(reference, quantity="gw", delta=0.001001)

        report = evaluate_regression(candidate, reference, tolerance_ev=0.001)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["reason_code"], "REGRESSION_TOLERANCE_EXCEEDED")

    def test_all_ks_exx_and_gw_quantities_are_gated(self):
        reference = scientific_result()
        for quantity in ("ks", "exx", "gw"):
            with self.subTest(quantity=quantity):
                report = evaluate_regression(
                    shifted(reference, quantity=quantity, delta=0.002),
                    reference,
                    tolerance_ev=0.001,
                )
                self.assertEqual(report["status"], "FAIL")
                self.assertGreater(report["quantities"][quantity]["max_abs_error_ev"], 0.001)

    def test_definition_mismatch_and_missing_reference_are_not_evaluated(self):
        candidate = scientific_result(nfreq=6)
        mismatched = scientific_result(nfreq=12)

        mismatch = evaluate_regression(candidate, mismatched, tolerance_ev=0.001)
        missing = evaluate_regression(candidate, None, tolerance_ev=0.001)

        self.assertEqual(mismatch["status"], "NOT_EVALUATED")
        self.assertEqual(mismatch["reason_code"], "DEFINITION_MISMATCH")
        self.assertEqual(mismatch["definition_differences"][0]["field"], "librpa.nfreq")
        self.assertEqual(missing["status"], "NOT_EVALUATED")
        self.assertEqual(missing["reason_code"], "REFERENCE_NOT_AVAILABLE")

    def test_state_set_or_qpe_failure_cannot_pass(self):
        reference = scientific_result()
        missing_state = copy.deepcopy(reference)
        missing_state["window"]["states"].pop()
        qpe = copy.deepcopy(reference)
        qpe["diagnostics"] = {
            "accepted": False,
            "failure_count": 1,
            "failures": [{"path": "LibRPA.out", "line": 2, "excerpt": "QPE failed"}],
        }

        state_report = evaluate_regression(missing_state, reference, tolerance_ev=0.001)
        qpe_report = evaluate_regression(qpe, reference, tolerance_ev=0.001)

        self.assertEqual(state_report["status"], "FAIL")
        self.assertEqual(state_report["reason_code"], "STATE_SET_MISMATCH")
        self.assertEqual(qpe_report["status"], "FAIL")
        self.assertEqual(qpe_report["reason_code"], "QPE_DIAGNOSTIC_FAILURE")


if __name__ == "__main__":
    unittest.main()
