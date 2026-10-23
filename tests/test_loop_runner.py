import json
import pathlib
import tempfile
import unittest

import numpy as np

from oml_mcp.loop_runner import (
    TrialOutcome,
    definition_digest,
    measure_noise_floor,
    run_loop,
)


OCCUPATIONS = (1.0, 1.0, 1.0, 0.0, 0.0, 0.0)


def write_band(path: pathlib.Path, rows, occupations=OCCUPATIONS) -> None:
    lines = []
    for index, kx, ky, kz, energies in rows:
        fields = [str(index), repr(kx), repr(ky), repr(kz)]
        for occupation, energy in zip(occupations, energies):
            fields.extend([repr(occupation), repr(energy)])
        lines.append(" ".join(fields))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def smooth_rows(offset: float) -> list:
    rows = []
    for k in range(5):
        shift = 0.01 * k
        energies = [-1.0 + shift, -0.8 + shift, -0.6 + shift, 1.0 + shift, 1.2 + shift, 1.4 + shift]
        rows.append((k + 1, k / 5.0, 0.0, 0.0, [energy + offset for energy in energies]))
    return rows


def write_triple(root: pathlib.Path, *, gw_spike: bool = False, ks_spike: bool = False) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    ks_rows = smooth_rows(0.0)
    exx_rows = smooth_rows(0.5)
    gw_rows = smooth_rows(0.7)
    if ks_spike:
        index, kx, ky, kz, energies = ks_rows[2]
        energies = [value + 0.8 for value in energies]
        ks_rows[2] = (index, kx, ky, kz, energies)
        # Keep the EXX/GW deltas clean by carrying the same spike.
        exx_rows[2] = (exx_rows[2][0], *exx_rows[2][1:4], [value + 0.8 for value in exx_rows[2][4]])
        gw_rows[2] = (gw_rows[2][0], *gw_rows[2][1:4], [value + 0.8 for value in gw_rows[2][4]])
    if gw_spike:
        index, kx, ky, kz, energies = gw_rows[2]
        energies = list(energies)
        energies[4] += 0.8
        gw_rows[2] = (index, kx, ky, kz, energies)
    write_band(root / "KS_band_spin_1.dat", ks_rows)
    write_band(root / "EXX_band_spin_1.dat", exx_rows)
    write_band(root / "GW_band_spin_1.dat", gw_rows)
    return {
        "ks": str(root / "KS_band_spin_1.dat"),
        "exx": str(root / "EXX_band_spin_1.dat"),
        "gw": str(root / "GW_band_spin_1.dat"),
    }


GOOD_COULOMB = {"matrix": np.eye(2, dtype=complex)}
BAD_COULOMB = {"matrix": np.array([[1.0, 2.0], [0.0, 1.0]], dtype=complex)}


class ScriptedRunner:
    def __init__(self, root: pathlib.Path, script: list[dict]):
        self.root = root
        self.script = script
        self.calls: list[dict] = []

    def run(self, definition, *, trial: int) -> TrialOutcome:
        self.calls.append(dict(definition))
        behavior = self.script[min(trial - 1, len(self.script) - 1)]
        artifacts = write_triple(self.root / f"trial{trial}", **behavior.get("bands", {}))
        return TrialOutcome(
            status=behavior.get("status", "COMPLETED"),
            artifacts=artifacts,
            coulomb=behavior.get("coulomb"),
            elapsed_seconds=1.0,
        )


class LoopRunnerTest(unittest.TestCase):
    def test_accepts_a_clean_first_trial(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(pathlib.Path(tmpdir), [{"coulomb": GOOD_COULOMB}])
            result = run_loop({"nfreq": 24}, runner, occupied_bands=3)
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(len(result.records), 1)
        self.assertTrue(result.records[0].accepted)

    def test_retries_a_bumpy_gw_with_one_axis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(
                pathlib.Path(tmpdir),
                [
                    {"bands": {"gw_spike": True}, "coulomb": GOOD_COULOMB},
                    {"coulomb": GOOD_COULOMB},
                ],
            )
            result = run_loop(
                {"nfreq": 24, "exx_pca_threshold": 1e-4}, runner, occupied_bands=3
            )
        self.assertEqual(result.status, "ACCEPTED")
        self.assertEqual(len(result.records), 2)
        first, second = result.records
        self.assertEqual(first.rule_id, "r4")
        self.assertIn("exx_pca_threshold", first.action or "")
        self.assertAlmostEqual(second.definition["exx_pca_threshold"], 1e-5)
        self.assertTrue(second.accepted)

    def test_coulomb_failure_switches_the_construction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(
                pathlib.Path(tmpdir),
                [{"coulomb": BAD_COULOMB}, {"coulomb": GOOD_COULOMB}],
            )
            result = run_loop(
                {"out_librpa_3d_coulomb_method": "ewald"}, runner, occupied_bands=3
            )
        self.assertEqual(result.status, "ACCEPTED")
        first, second = result.records
        self.assertEqual(first.rule_id, "r2")
        self.assertEqual(second.definition["out_librpa_3d_coulomb_method"], "direct_reciprocal")

    def test_stops_when_no_rule_matches(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(
                pathlib.Path(tmpdir),
                [{"bands": {"ks_spike": True}, "coulomb": GOOD_COULOMB}],
            )
            result = run_loop({"nfreq": 24}, runner, occupied_bands=3)
        self.assertEqual(result.status, "NO_RULE")
        self.assertEqual(len(result.records), 1)

    def test_budget_exhaustion_after_repeated_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(
                pathlib.Path(tmpdir),
                [{"bands": {"gw_spike": True}, "coulomb": GOOD_COULOMB}],
            )
            result = run_loop(
                {"nfreq": 24, "exx_pca_threshold": 1e-4},
                runner,
                occupied_bands=3,
                max_trials=3,
            )
        self.assertEqual(result.status, "BUDGET_EXHAUSTED")
        self.assertEqual(len(result.records), 3)
        values = [record.definition["exx_pca_threshold"] for record in result.records]
        self.assertAlmostEqual(values[1] / values[0], 0.1)
        self.assertAlmostEqual(values[2] / values[1], 0.1)

    def test_no_action_when_the_rule_has_no_numeric_parameter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(
                pathlib.Path(tmpdir),
                [{"bands": {"gw_spike": True}, "coulomb": GOOD_COULOMB}],
            )
            result = run_loop({"nfreq": 24}, runner, occupied_bands=3)
        self.assertEqual(result.status, "NO_ACTION")
        self.assertEqual(result.records[0].rule_id, "r4")

    def test_infrastructure_error_stops_after_the_consecutive_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(
                pathlib.Path(tmpdir), [{"status": "FAILED"}]
            )
            result = run_loop(
                {"nfreq": 24}, runner, occupied_bands=3, max_consecutive_failures=2
            )
        self.assertEqual(result.status, "INFRASTRUCTURE_ERROR")
        self.assertEqual(len(result.records), 2)

    def test_ledger_is_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            runner = ScriptedRunner(root, [{"coulomb": GOOD_COULOMB}])
            ledger = root / "ledger.json"
            result = run_loop({"nfreq": 24}, runner, occupied_bands=3, ledger_path=ledger)
            payload = json.loads(ledger.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "ACCEPTED")
        self.assertEqual(payload["records"][0]["definition_digest"], definition_digest({"nfreq": 24}))
        self.assertEqual(result.status, "ACCEPTED")

    def test_noise_floor_from_a_repeated_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = ScriptedRunner(
                pathlib.Path(tmpdir), [{"coulomb": GOOD_COULOMB}]
            )
            floor = measure_noise_floor({"nfreq": 24}, runner, occupied_bands=3)
        self.assertTrue(floor["evaluated"])
        self.assertEqual(floor["gap_delta_ev"], 0.0)
        self.assertEqual(len(runner.calls), 2)


if __name__ == "__main__":
    unittest.main()
