import pathlib
import tempfile
import unittest

import numpy as np


from oml_mcp.known_issues import (
    KnownIssueError,
    diagnose_run,
    list_known_issues,
    load_known_issue,
)
from oml_mcp.parameter_prescriptions import (
    ParameterPrescriptionError,
    load_prescription,
    tune_parameter,
)
from tests.test_stage_inspection import command_completed, write_coulomb_block


def _write_pyatb_run(root: pathlib.Path, coulomb_matrix: np.ndarray) -> None:
    """Write a pyatb stage fixture with a real reader-v1 Coulomb block."""
    command_completed(root, "pyatb")
    (root / "band_out").write_text("1 1 4 4\n", encoding="utf-8")
    (root / "basis_wfc_out").write_text("basis_wfc\n")
    (root / "basis_aux_out").write_text("basis_aux\n")
    # The headwing directory must carry the metadata file the pyatb gate expects.
    pyatb_dir = root / "pyatb_librpa_df"
    pyatb_dir.mkdir(exist_ok=True)
    (pyatb_dir / "k_path_info").write_text("4 4 1 1\n0.0 0.0 0.0\n", encoding="utf-8")
    for i in (1, 2):
        (root / f"KS_eigenvector_{i}").write_text("ks\n")
        (root / f"v1_Cs_data_{i}").write_text("cs\n")
        (root / f"v1_coulomb_full_iq_{i}_rank0.dat").write_bytes(
            _coulomb_bytes(coulomb_matrix)
        )
        (root / f"v1_coulomb_cut_iq_{i}_rank0.dat").write_bytes(
            _coulomb_bytes(coulomb_matrix)
        )


def _coulomb_bytes(matrix: np.ndarray) -> bytes:
    import io

    naux = matrix.shape[0]
    header_bytes = 24 + 4 + 12
    data = bytearray()
    data += (np.int32(-20129433)).tobytes()
    data += (np.int32(1)).tobytes()
    data += (np.int32(naux)).tobytes()
    data += (np.int32(1)).tobytes()
    data += (np.int32(1)).tobytes()
    data += (np.int32(1)).tobytes()
    data += (np.int32(naux)).tobytes()
    data += (np.int32(0)).tobytes()
    data += (np.int64(header_bytes)).tobytes()
    data += np.asarray(matrix, dtype=np.complex128).tobytes(order="C")
    return bytes(data)


class KnownIssueStoreTest(unittest.TestCase):
    def test_list_returns_curated_issues(self):
        issues = list_known_issues()

        self.assertGreaterEqual(len(issues), 6)
        ids = {issue.issue_id for issue in issues}
        self.assertIn("coulomb-matrix-not-positive-definite", ids)
        self.assertIn("garbage-exx-bands", ids)
        self.assertIn("nbands-not-equal-nbasis", ids)
        self.assertIn("symmetry-full-q-mismatch", ids)

    def test_load_known_issue_returns_structured_entry(self):
        issue = load_known_issue("coulomb-matrix-not-positive-definite")

        self.assertEqual(issue.issue_id, "coulomb-matrix-not-positive-definite")
        self.assertEqual(issue.confidence, "established")
        self.assertIn("positive-definite", issue.title)
        self.assertEqual(issue.gate_id, "coulomb.psd_hermitian")
        self.assertIn("exx_cs_inv_thr", issue.parameters)

    def test_load_rejects_unknown_issue(self):
        with self.assertRaisesRegex(KnownIssueError, "not available"):
            load_known_issue("nonexistent-issue")

    def test_diagnose_run_maps_indefinite_coulomb_to_coulomb_issue(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            # Indefinite matrix: eigenvalues [4.0, -1.0]
            _write_pyatb_run(root, np.diag([4.0, -1.0]))

            report = diagnose_run(root, stage="pyatb")

        self.assertGreaterEqual(report["matched_count"], 1)
        # Every top match must be a Coulomb PSD issue (same gate_id), and the
        # store must surface both the generic repair entry and the specific
        # 3D full-Ewald root-cause entry for an indefinite matrix.
        top_ids = [match["issue"]["issue_id"] for match in report["matches"][:5]]
        for issue_id in (
            "coulomb-matrix-not-positive-definite",
            "3d-full-ewald-coulomb-strongly-indefinite",
        ):
            self.assertIn(issue_id, top_ids)
        for match in report["matches"]:
            if match["rank"] == report["matches"][0]["rank"]:
                self.assertEqual(match["issue"]["gate_id"], "coulomb.psd_hermitian")

    def test_diagnose_run_returns_no_coulomb_match_for_clean_coulomb(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            # Positive-definite matrix: eigenvalues [4.0, 9.0]
            _write_pyatb_run(root, np.diag([4.0, 9.0]))

            report = diagnose_run(root, stage="pyatb")

        # No coulomb.psd_hermitian gate should be failing, so no coulomb issue match.
        coulomb_matches = [
            match
            for match in report["matches"]
            if match["issue"]["gate_id"] == "coulomb.psd_hermitian"
        ]
        self.assertEqual(coulomb_matches, [])


class KnownIssueCoverageTest(unittest.TestCase):
    """The store must cover the recurring problems comprehensively, not just a few examples."""

    def test_store_is_comprehensive(self):
        issues = list_known_issues()

        # The curated store is mined from the codex session history; a handful of
        # entries would mean the mining was not actually done.
        self.assertGreaterEqual(len(issues), 60)
        ids = [issue.issue_id for issue in issues]
        self.assertEqual(len(ids), len(set(ids)), "issue ids must be unique")

    def test_every_category_of_recurring_problem_is_covered(self):
        ids = {issue.issue_id for issue in list_known_issues()}

        for prefix in (
            "coulomb",
            "symmetry",
            "exx",
            "nbands",
            "abfs",
            "full-q",
            "rpa",
        ):
            with self.subTest(prefix=prefix):
                self.assertTrue(
                    any(issue_id.startswith(prefix) for issue_id in ids),
                    f"no known issue covers the {prefix!r} family",
                )

    def test_every_issue_is_well_formed(self):
        for issue in list_known_issues():
            with self.subTest(issue_id=issue.issue_id):
                self.assertIn(issue.confidence, {"established", "tentative"})
                self.assertTrue(issue.symptom)
                self.assertTrue(issue.minimal_fix)
                self.assertTrue(issue.validation)
                self.assertTrue(issue.avoid)
                self.assertTrue(issue.source)

    def test_most_issues_carry_a_gate_or_parameters(self):
        issues = list_known_issues()
        actionable = [
            issue for issue in issues if issue.gate_id or issue.parameters
        ]

        # An issue that names neither a gate nor a parameter cannot be acted on.
        self.assertGreaterEqual(len(actionable), int(len(issues) * 0.8))

    def test_diagnosis_reports_each_issue_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            # Two q blocks fail, so the same issue would match twice without dedup.
            _write_pyatb_run(root, np.diag([4.0, -1.0]))

            report = diagnose_run(root, stage="pyatb")

        ids = [match["issue"]["issue_id"] for match in report["matches"]]
        self.assertEqual(len(ids), len(set(ids)), "an issue must be reported once")

    def test_matches_are_ranked_descending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_pyatb_run(root, np.diag([4.0, -1.0]))

            report = diagnose_run(root, stage="pyatb")

        ranks = [match["rank"] for match in report["matches"]]
        self.assertEqual(ranks, sorted(ranks, reverse=True))


class ResolutionPlanTest(unittest.TestCase):
    """A diagnosis must turn into something an agent can actually act on."""

    def test_plan_is_actionable_for_a_broken_run(self):
        from oml_mcp.known_issues import resolve_run

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_pyatb_run(root, np.diag([4.0, -1.0]))

            plan = resolve_run(root, stage="pyatb")

        self.assertTrue(plan["actionable"])
        self.assertEqual(plan["schema"], "oml.resolution-plan.v1")
        for action in plan["actions"]:
            self.assertTrue(action["do"], "every action needs a concrete fix")
            self.assertTrue(action["verify"], "every action needs a verification step")
            self.assertTrue(action["avoid"], "every action needs the dead end to avoid")

    def test_plan_attaches_prescribed_parameter_values(self):
        from oml_mcp.known_issues import resolve_run

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_pyatb_run(root, np.diag([4.0, -1.0]))

            plan = resolve_run(
                root,
                stage="pyatb",
                route_id="periodic_3d_gw",
                material_class="transition_metal_oxide_gw",
            )

        prescribed = [
            action.get("prescribed_parameters", {}) for action in plan["actions"]
        ]
        exx = [item["exx_cs_inv_thr"] for item in prescribed if "exx_cs_inv_thr" in item]
        self.assertTrue(exx, "the heavy-element EXX threshold must be prescribed")
        self.assertEqual(exx[0]["target"], 1e-5)
        self.assertIn("allowed_range", exx[0])

    def test_plan_never_claims_to_have_applied_anything(self):
        from oml_mcp.known_issues import resolve_run

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_pyatb_run(root, np.diag([4.0, -1.0]))

            plan = resolve_run(root, stage="pyatb")

        self.assertIn("advisory", plan["note"])
        self.assertIn("No fix is applied", plan["note"])

    def test_plan_writes_to_disk(self):
        from oml_mcp.known_issues import resolve_run, write_resolution_plan

        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _write_pyatb_run(root, np.diag([4.0, -1.0]))
            plan = resolve_run(root, stage="pyatb")
            path = write_resolution_plan(plan, root / "plan.json")
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
