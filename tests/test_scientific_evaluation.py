import copy
import unittest


from oml_mcp.provenance import digest_json
from oml_mcp.scientific_evaluation import (
    ScientificEvaluationError,
    aggregate_convergence,
    evaluate_convergence_axis,
    evaluate_regression,
)


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
        self.assertEqual(report["quantities"]["gw"]["candidate_ev"], -1.499)
        self.assertEqual(report["quantities"]["gw"]["reference_ev"], -1.5)
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

    def test_explicit_candidate_failure_precedes_missing_reference(self):
        candidate = scientific_result()
        candidate["diagnostics"] = {
            "accepted": False,
            "failure_count": 1,
            "failures": [
                {"reason_code": "NONPOSITIVE_GW_GAP", "gap_ev": -1.0}
            ],
        }

        report = evaluate_regression(candidate, None, tolerance_ev=0.001)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["reason_code"], "NONPOSITIVE_GW_GAP")


class ScientificConvergenceTest(unittest.TestCase):
    def convergence_pair(self, *, delta: float = 0.05) -> tuple[dict, dict]:
        coarse = scientific_result(nfreq=6)
        fine = scientific_result(nfreq=12)
        fine["window"]["states"][2]["gw_ev"] += delta
        fine["window"]["fundamental_gw_gap_ev"] -= delta
        return coarse, fine

    def test_exact_50_mev_boundary_passes_for_states_and_gap(self):
        coarse, fine = self.convergence_pair()

        report = evaluate_convergence_axis(
            coarse,
            fine,
            axis="nfreq",
            tolerance_ev=0.05,
        )

        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["max_abs_gw_change_ev"], 0.05)
        self.assertEqual(report["gap_change_ev"], 0.05)
        self.assertEqual(report["axis"], "nfreq")

    def test_just_over_50_mev_fails(self):
        coarse, fine = self.convergence_pair(delta=0.050001)

        report = evaluate_convergence_axis(
            coarse,
            fine,
            axis="nfreq",
            tolerance_ev=0.05,
        )

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["reason_code"], "CONVERGENCE_TOLERANCE_EXCEEDED")

    def test_pair_may_change_only_the_declared_axis(self):
        coarse, fine = self.convergence_pair()
        fine["definition"]["profile_id"] = "other-profile"

        with self.assertRaises(ScientificEvaluationError) as raised:
            evaluate_convergence_axis(
                coarse,
                fine,
                axis="nfreq",
                tolerance_ev=0.05,
            )

        self.assertEqual(raised.exception.code, "MULTIPLE_DEFINITION_CHANGES")

    def test_state_set_and_qpe_failures_cannot_pass(self):
        coarse, fine = self.convergence_pair()
        missing = copy.deepcopy(fine)
        missing["window"]["states"].pop()
        qpe = copy.deepcopy(fine)
        qpe["diagnostics"] = {
            "accepted": False,
            "failure_count": 1,
            "failures": [{"path": "LibRPA.out", "line": 4, "excerpt": "QPE failed"}],
        }

        state_report = evaluate_convergence_axis(
            coarse, missing, axis="nfreq", tolerance_ev=0.05
        )
        qpe_report = evaluate_convergence_axis(
            coarse, qpe, axis="nfreq", tolerance_ev=0.05
        )

        self.assertEqual(state_report["reason_code"], "STATE_SET_MISMATCH")
        self.assertEqual(qpe_report["reason_code"], "QPE_DIAGNOSTIC_FAILURE")

    def test_all_required_axes_must_be_present_and_pass(self):
        passing = {
            axis: {"axis": axis, "status": "PASS", "reason_code": "WITHIN_TOLERANCE"}
            for axis in ("nfreq", "empty_states", "screening_kgrid")
        }

        complete = aggregate_convergence(
            passing,
            required_axes=("nfreq", "empty_states", "screening_kgrid"),
        )
        incomplete = aggregate_convergence(
            {"nfreq": passing["nfreq"]},
            required_axes=("nfreq", "empty_states", "screening_kgrid"),
        )
        failed_reports = copy.deepcopy(passing)
        failed_reports["empty_states"]["status"] = "FAIL"
        failed = aggregate_convergence(
            failed_reports,
            required_axes=("nfreq", "empty_states", "screening_kgrid"),
        )

        self.assertEqual(complete["status"], "PASS")
        self.assertEqual(incomplete["status"], "NOT_EVALUATED")
        self.assertEqual(incomplete["missing_axes"], ["empty_states", "screening_kgrid"])
        self.assertEqual(failed["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
