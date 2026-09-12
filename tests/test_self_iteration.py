import pathlib
import tempfile
import unittest

from oml_mcp.evolution import EvolutionBudget
from oml_mcp.fast_benchmark import load_fast_case
from oml_mcp.self_iteration import (
    ACCEPTED,
    INFRASTRUCTURE_ERROR,
    NOT_EVALUATED,
    REJECTED_GATE,
    REJECTED_REFERENCE,
    LoopPolicy,
    SelfIterationError,
    axis_candidates,
    run_self_iteration,
    write_ledger,
)


REFERENCE_OUT = """
GW bandgap(eV):   6.1400000
EXX bandgap(eV):   9.1200000
DFT bandgap(eV):   4.3300000
"""

# A baseline definition with the axes the periodic 3D GW route registers.
BASELINE = {
    "nfreq": 16,
    "nbands": 26,
    "exx_cs_inv_thr": -1.0,
    "shrink_threshold": 0.001,
}


def _budget(max_candidates: int = 8) -> EvolutionBudget:
    return EvolutionBudget(
        max_candidates=max_candidates,
        cpu_hours=24.0,
        wall_seconds=86400,
        disk_bytes=10_000_000_000,
    )


class FakeAdapter:
    """Deterministic in-process adapter that stands in for the remote cluster."""

    def __init__(self, *, good_values=(), gate_fail_values=(), error_values=()):
        self.good_values = set(good_values)
        self.gate_fail_values = set(gate_fail_values)
        self.error_values = set(error_values)
        self.calls = []

    def run_candidate(self, *, case, candidate, iteration):
        self.calls.append({"case_id": case.case_id, "candidate": dict(candidate), "iteration": iteration})
        axis_value = candidate.get("exx_cs_inv_thr")
        if axis_value in self.error_values:
            raise RuntimeError("scheduler unreachable")
        if axis_value in self.gate_fail_values:
            return {
                "status": "COMPLETED",
                "observed": {"librpa.out": REFERENCE_OUT},
                "diagnostics": {"status": "FAIL"},
                "run_id": f"run-{iteration}",
            }
        if axis_value in self.good_values:
            return {
                "status": "COMPLETED",
                "observed": {"librpa.out": REFERENCE_OUT},
                "diagnostics": {"status": "PASS"},
                "run_id": f"run-{iteration}",
            }
        # Default: numerically wrong result.
        wrong = REFERENCE_OUT.replace("6.1400000", "8.9900000")
        return {
            "status": "COMPLETED",
            "observed": {"librpa.out": wrong},
            "diagnostics": {"status": "PASS"},
            "run_id": f"run-{iteration}",
        }


class AxisCandidateTest(unittest.TestCase):
    def test_axis_candidates_change_exactly_one_axis(self):
        candidates = axis_candidates(BASELINE, axis="exx_cs_inv_thr", values=[1e-5, 1e-4])

        self.assertEqual(len(candidates), 2)
        for candidate in candidates:
            changed = [k for k in BASELINE if BASELINE[k] != candidate[k]]
            self.assertEqual(changed, ["exx_cs_inv_thr"])

    def test_axis_candidates_rejects_unknown_axis(self):
        with self.assertRaisesRegex(SelfIterationError, "does not define axis"):
            axis_candidates(BASELINE, axis="bogus_axis", values=[1])


class SelfIterationTest(unittest.TestCase):
    def setUp(self):
        self.case = load_fast_case("bn-3d-sym-shrink-g0w0")

    def test_dry_run_proposes_without_executing(self):
        adapter = FakeAdapter()
        policy = LoopPolicy(
            budget=_budget(4),
            allowed_axes=("exx_cs_inv_thr",),
            execute=False,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-5, 1e-4]},
            policy=policy,
            adapter=adapter,
        )

        self.assertEqual(adapter.calls, [])
        self.assertFalse(report["executed"])
        self.assertEqual(report["iterations"], 2)
        self.assertEqual(report["accepted_count"], 0)
        self.assertFalse(report["improved"])

    def test_loop_accepts_the_good_value_and_stops_at_budget(self):
        adapter = FakeAdapter(good_values=[1e-5])
        policy = LoopPolicy(
            budget=_budget(4),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-6, 1e-5, 1e-4, 1e-3]},
            policy=policy,
            adapter=adapter,
            reference={"librpa.out": REFERENCE_OUT},
        )

        self.assertEqual(report["accepted_count"], 1)
        self.assertTrue(report["improved"])
        self.assertEqual(report["accepted_definition"]["exx_cs_inv_thr"], 1e-5)
        self.assertEqual(len(adapter.calls), 4)

    def test_loop_rejects_wrong_numbers(self):
        adapter = FakeAdapter()
        policy = LoopPolicy(
            budget=_budget(2),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-5]},
            policy=policy,
            adapter=adapter,
            reference={"librpa.out": REFERENCE_OUT},
        )

        self.assertEqual(report["ledger"][0]["outcome"], REJECTED_REFERENCE)
        self.assertFalse(report["improved"])

    def test_gate_failure_is_rejected_even_with_good_numbers(self):
        adapter = FakeAdapter(gate_fail_values=[1e-5])
        policy = LoopPolicy(
            budget=_budget(2),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-5]},
            policy=policy,
            adapter=adapter,
            reference={"librpa.out": REFERENCE_OUT},
        )

        self.assertEqual(report["ledger"][0]["outcome"], REJECTED_GATE)

    def test_infrastructure_error_is_recorded_not_crashed(self):
        adapter = FakeAdapter(error_values=[1e-5])
        policy = LoopPolicy(
            budget=_budget(2),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-5]},
            policy=policy,
            adapter=adapter,
            reference={"librpa.out": REFERENCE_OUT},
        )

        self.assertEqual(report["ledger"][0]["outcome"], INFRASTRUCTURE_ERROR)
        self.assertIn("scheduler unreachable", report["ledger"][0]["reason"])

    def test_missing_reference_cannot_accept(self):
        adapter = FakeAdapter(good_values=[1e-5])
        policy = LoopPolicy(
            budget=_budget(2),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-5]},
            policy=policy,
            adapter=adapter,
            reference={},
        )

        # No reference means no acceptance: the loop must never false-pass.
        self.assertEqual(report["ledger"][0]["outcome"], NOT_EVALUATED)
        self.assertEqual(report["accepted_count"], 0)

    def test_early_stop_after_consecutive_rejections(self):
        adapter = FakeAdapter()
        policy = LoopPolicy(
            budget=_budget(10),
            allowed_axes=("exx_cs_inv_thr",),
            stop_after_consecutive_rejections=2,
            execute=True,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-6, 1e-5, 1e-4, 1e-3]},
            policy=policy,
            adapter=adapter,
            reference={"librpa.out": REFERENCE_OUT},
        )

        self.assertEqual(report["stop_reason"], "CONSECUTIVE_REJECTIONS")
        self.assertEqual(len(adapter.calls), 2)

    def test_ledger_lessons_are_recorded(self):
        adapter = FakeAdapter()
        policy = LoopPolicy(
            budget=_budget(1),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )

        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-5]},
            policy=policy,
            adapter=adapter,
            reference={"librpa.out": REFERENCE_OUT},
        )

        self.assertIn("do not retry this value", report["ledger"][0]["lesson"])

    def test_unregistered_axis_is_rejected(self):
        policy = LoopPolicy(
            budget=_budget(2),
            allowed_axes=("totally_bogus",),
            execute=True,
        )
        with self.assertRaisesRegex(SelfIterationError, "not registered"):
            run_self_iteration(
                case=self.case,
                baseline=BASELINE,
                axis_values={"totally_bogus": [1]},
                policy=policy,
                adapter=FakeAdapter(),
            )

    def test_non_evaluable_case_refuses_to_iterate(self):
        case = load_fast_case("bn-3d-headwing-g0w0")
        policy = LoopPolicy(
            budget=_budget(2),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )
        with self.assertRaisesRegex(SelfIterationError, "not evaluable"):
            run_self_iteration(
                case=case,
                baseline=BASELINE,
                axis_values={"exx_cs_inv_thr": [1e-5]},
                policy=policy,
                adapter=FakeAdapter(),
                reference={"librpa.out": REFERENCE_OUT},
            )

    def test_ledger_is_written_to_disk(self):
        adapter = FakeAdapter(good_values=[1e-5])
        policy = LoopPolicy(
            budget=_budget(2),
            allowed_axes=("exx_cs_inv_thr",),
            execute=True,
        )
        report = run_self_iteration(
            case=self.case,
            baseline=BASELINE,
            axis_values={"exx_cs_inv_thr": [1e-5]},
            policy=policy,
            adapter=adapter,
            reference={"librpa.out": REFERENCE_OUT},
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_ledger(report, pathlib.Path(tmpdir) / "ledger.json")
            self.assertTrue(path.is_file())
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "oml.self-iteration-ledger.v1")
        self.assertEqual(payload["report"]["case_id"], self.case.case_id)


if __name__ == "__main__":
    unittest.main()
