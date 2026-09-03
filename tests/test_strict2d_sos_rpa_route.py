import json
import pathlib
import tempfile
import unittest


from oml_mcp.profiles import ProfileError, list_profiles, load_profile
from oml_mcp.planner import PlanError, plan_case
from oml_mcp.server import build_server
from oml_mcp.validators import validate_case
from oml_mcp.evolution import ROUTE_MUTATION_AXES
from tests import test_validators
from oml_mcp.admission_manifest import (
    AdmissionManifestError,
    load_admission_manifest,
    validate_admission_manifest,
)


PROFILE_ID = "abacus-librpa-2026-09-02-strict2d-sos-rpa-v1"
PROFILE_NAME = "abacus-librpa-strict2d-sos-rpa-2026-09-v1.json"
PRODUCTION_PROFILE_ID = "abacus-librpa-2026-09-03-strict2d-sos-rpa-v2"
PRODUCTION_PROFILE_NAME = "abacus-librpa-strict2d-sos-rpa-2026-09-v2.json"
BENCHMARK_ID = "strict2d-sos-rpa-mos2-qavg-v1"
MANIFEST_ID = "df-dcu-strict2d-sos-rpa-2026-09-02-v1"


class Strict2dSosRpaProfileTest(unittest.TestCase):
    @staticmethod
    def make_case(root: pathlib.Path) -> None:
        (root / "INPUT_scf").write_text(
            "INPUT_PARAMETERS\n"
            "basis_type lcao\n"
            "rpa 1\n"
            "out_librpa_reader_version 1\n"
            "symmetry 1\n"
            "shrink_abfs_pca_thr 1e-4\n",
            encoding="utf-8",
        )
        (root / "STRU").write_text("ATOMIC_SPECIES\n", encoding="utf-8")
        (root / "librpa.in").write_text(
            "task = rpa\n"
            "input_dir = dataset\n"
            "prefix_coul_full = v1_coulomb_full_iq_\n"
            "prefix_eigvecs_scf = KS_eigenvector\n"
            "prefix_lri_coeff = v1_Cs_data_\n"
            "prefix_lri_coeff_shrink = v1_Cs_shrinked_data_\n"
            "prefix_shrink_sinvS = v1_shrink_sinvS_\n"
            "fn_stru = stru_out\n"
            "fn_bz_sampling = bz_sampling_out\n"
            "fn_basis_wfc = basis_wfc_out\n"
            "fn_basis_aux = basis_aux_out\n"
            "fn_basis_aux_shrink = basis_aux_shrink_out\n"
            "fn_eigocc_scf = band_out\n"
            "version_coul_reader = 1\n"
            "version_lri_reader = 1\n"
            "nfreq = 16\n"
            "use_shrink_abfs = t\n"
            "use_symmetry_rpa = t\n"
            "use_soc = 0\n"
            "replace_w_head = t\n"
            "option_dielect_func = 3\n"
            "use_2d_dielectric = t\n"
            "use_pyatb = t\n"
            "rpa_headwing_mode = qavg\n"
            "rpa_headwing_body_start = 1\n",
            encoding="utf-8",
        )

    def test_profile_is_registered_without_mutating_historical_profiles(self):
        self.assertIn(PROFILE_ID, list_profiles())
        self.assertIn(PRODUCTION_PROFILE_ID, list_profiles())

    def test_profile_pins_the_validated_librpa_and_replay_only_contract(self):
        profile = load_profile(profile_id=PROFILE_ID)
        route = profile["capabilities"]["strict_2d_sos_rpa"]
        contract = profile["contract"]["strict_2d_sos_rpa"]

        self.assertEqual(profile["components"]["librpa"]["revision"], "c87103df00b772ddbfc21597884c2787cf685037")
        self.assertEqual(route["status"], "TESTABLE")
        self.assertEqual(route["admission_level"], "L3")
        self.assertEqual(contract["task"], "rpa")
        self.assertEqual(contract["response_method"], "sos")
        self.assertEqual(contract["nfreq"], 16)
        self.assertEqual(contract["headwing"], "qavg")
        self.assertFalse(contract["head_only"])
        self.assertEqual(contract["coulomb"], "full_2d_ewald")
        self.assertEqual(contract["coulomb_head_artifact"], "librpa_2d_coulomb_head.dat")
        self.assertEqual(contract["producer_policy"], "reuse_validated_only")
        self.assertFalse(contract["allow_abacus_rerun"])
        self.assertFalse(contract["allow_pyatb_rerun"])
        self.assertEqual(
            contract["k_mesh_acceptance"]["validated_scope"],
            "four_mesh_functional_and_numerical_not_asymptotic",
        )
        self.assertTrue(contract["k_mesh_acceptance"]["require_stable_asymptotic_fit"])
        self.assertTrue(contract["k_mesh_acceptance"]["forbid_convergence_exponent_claim"])

    def test_profile_cannot_self_promote_beyond_testable_l3(self):
        profile = load_profile(profile_id=PROFILE_ID)
        profile["capabilities"]["strict_2d_sos_rpa"]["status"] = "ENABLED"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "promoted.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ProfileError, "TESTABLE"):
                load_profile(path)

    def test_reviewed_l4_profile_enables_only_the_benchmark_bound_route(self):
        historical = load_profile(profile_id=PROFILE_ID)
        production = load_profile(profile_id=PRODUCTION_PROFILE_ID)
        route = production["capabilities"]["strict_2d_sos_rpa"]
        acceptance = production["contract"]["strict_2d_sos_rpa"]["k_mesh_acceptance"]

        self.assertEqual(historical["capabilities"]["strict_2d_sos_rpa"]["status"], "TESTABLE")
        self.assertEqual(historical["capabilities"]["strict_2d_sos_rpa"]["admission_level"], "L3")
        self.assertEqual(route["status"], "ENABLED")
        self.assertEqual(route["admission_level"], "L4")
        self.assertEqual(route["benchmark_id"], BENCHMARK_ID)
        self.assertEqual(acceptance["acceptance_model"], "reference_bounded_four_mesh")
        self.assertEqual(acceptance["benchmark_id"], BENCHMARK_ID)
        self.assertEqual(acceptance["required_meshes"], [8, 10, 12, 16])
        self.assertFalse(acceptance["require_stable_asymptotic_fit"])
        self.assertTrue(acceptance["forbid_convergence_exponent_claim"])
        self.assertEqual(production["components"], historical["components"])

    def test_production_profile_rejects_a_missing_or_relaxed_benchmark_binding(self):
        profile = load_profile(profile_id=PRODUCTION_PROFILE_ID)
        profile["contract"]["strict_2d_sos_rpa"]["k_mesh_acceptance"][
            "benchmark_id"
        ] = "unregistered"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "drifted-production.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ProfileError, "benchmark"):
                load_profile(path)

    def test_profile_requires_a_stable_asymptotic_fit_before_promotion(self):
        profile = load_profile(profile_id=PROFILE_ID)
        profile["admission"]["promotion"][
            "mesh_series_is_convergence_evidence_without_stable_fit"
        ] = True
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "promoted-without-stable-fit.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ProfileError, "stable asymptotic fit"):
                load_profile(path)

    def test_profile_rejects_headwing_contract_drift(self):
        profile = load_profile(profile_id=PROFILE_ID)
        profile["contract"]["strict_2d_sos_rpa"]["required_input"][
            "use_2d_dielectric"
        ] = False
        with tempfile.TemporaryDirectory() as tmpdir:
            path = pathlib.Path(tmpdir) / "drifted.json"
            path.write_text(json.dumps(profile), encoding="utf-8")
            with self.assertRaisesRegex(ProfileError, "qavg input"):
                load_profile(path)

    def test_controlled_evolution_keeps_nfreq_fixed_and_only_scans_physical_2d_axes(self):
        self.assertEqual(
            ROUTE_MUTATION_AXES["strict_2d_sos_rpa"],
            frozenset({"in_plane_kgrid", "vacuum"}),
        )

    def test_packaged_profile_matches_repository_audit_copy(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        repository = json.loads((root / "profiles" / PROFILE_NAME).read_text(encoding="utf-8"))
        packaged = json.loads((root / "oml_mcp" / "profiles" / PROFILE_NAME).read_text(encoding="utf-8"))

        self.assertEqual(packaged, repository)

        production_repository = json.loads(
            (root / "profiles" / PRODUCTION_PROFILE_NAME).read_text(encoding="utf-8")
        )
        production_packaged = json.loads(
            (root / "oml_mcp" / "profiles" / PRODUCTION_PROFILE_NAME).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(production_packaged, production_repository)

    def test_user_facing_rpa_guidance_names_the_strict2d_replay_exception(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        texts = [
            (root / "skills" / "abacus-librpa-rpa" / "SKILL.md").read_text(encoding="utf-8"),
            (root / "skills" / "abacus-librpa-version-guard" / "SKILL.md").read_text(encoding="utf-8"),
            (root / "skills" / "oh-my-librpa" / "references" / "rpa-route.md").read_text(encoding="utf-8"),
        ]

        for text in texts:
            self.assertIn(PROFILE_ID, text)
            self.assertIn("strict_2d_sos_rpa", text)
            self.assertIn("qavg", text)
            self.assertIn("librpa_2d_coulomb_head.dat", text)
            self.assertIn("no ABACUS/PyATB rerun", text)

        rpa_skill = texts[0]
        self.assertIn("$librpa-openmp-mkl-threading", rpa_skill)
        self.assertIn("OMP_NUM_THREADS == MKL_NUM_THREADS", rpa_skill)

    def test_live_benchmark_keeps_result_gates_and_remaining_convergence_separate(self):
        path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "docs"
            / "live-benchmarks"
            / "2026-09-02-df-dcu-strict2d-sos-rpa.md"
        )
        text = path.read_text(encoding="utf-8")

        for phrase in (
            "21833983",
            "21836052",
            "21834156",
            "21836055",
            "c87103df00b772ddbfc21597884c2787cf685037",
            "strict_2d_sos_rpa",
            "RESULT",
            "GATES",
            "REMAINING",
            "four meshes establish functional and numerical route consistency",
            "no N^-3 claim",
            "diagnostic failure-mode control",
        ):
            self.assertIn(phrase, text)

    def test_readme_and_installation_guide_expose_the_new_profile_and_manifest(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        for path in (root / "README.md", root / "docs" / "guide" / "installation.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn(PROFILE_ID, text)
            self.assertIn(MANIFEST_ID, text)
            self.assertIn("strict_2d_sos_rpa", text)
            self.assertIn("TESTABLE", text)
            self.assertIn("N=8/10/12/16", text)
            self.assertIn("stable asymptotic", text)
            self.assertNotIn("N=8/N=12", text)

    def test_plan_case_selects_a_librpa_only_strict2d_sos_rpa_replay(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            plan = plan_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                headwing=True,
                use_symmetry=True,
                profile_id=PROFILE_ID,
            )

        self.assertEqual(plan.route, "strict_2d_sos_rpa")
        self.assertEqual(plan.stages, ("librpa",))
        self.assertEqual(plan.options["capability_id"], "strict_2d_sos_rpa")
        self.assertEqual(plan.options["reader_format"], "v1")
        self.assertEqual(plan.options["nfreq"], 16)
        self.assertEqual(plan.options["headwing"], "qavg")
        self.assertFalse(plan.options["head_only"])
        self.assertFalse(plan.options["allow_abacus_rerun"])
        self.assertFalse(plan.options["allow_pyatb_rerun"])
        self.assertEqual(plan.gates[0].status, "WARN")
        self.assertTrue(any("stable asymptotic regime" in item for item in plan.assumptions))

    def test_plan_case_selects_the_l4_reference_bounded_route(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            plan = plan_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                headwing=True,
                use_symmetry=True,
                profile_id=PRODUCTION_PROFILE_ID,
            )

        self.assertEqual(plan.route, "strict_2d_sos_rpa")
        self.assertEqual(plan.options["capability"]["status"], "ENABLED")
        self.assertEqual(plan.options["benchmark_id"], BENCHMARK_ID)
        self.assertEqual(plan.gates[0].status, "PASS")
        self.assertTrue(any("reference-bounded" in item for item in plan.assumptions))
        self.assertTrue(any("does not establish an asymptotic exponent" in item for item in plan.assumptions))

    def test_validate_case_accepts_the_l4_profile_input_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            report = validate_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                use_symmetry=True,
                headwing=True,
                profile_id=PRODUCTION_PROFILE_ID,
                stage="input",
            )

        self.assertTrue(report.accepted, report.to_dict())
        gates = {gate.gate_id: gate for gate in report.gates}
        self.assertEqual(gates["route.strict_2d_sos_rpa"].status, "PASS")
        self.assertEqual(gates["librpa.strict_2d_sos_rpa"].status, "PASS")

    def test_plan_case_rejects_headwing_off_and_non_sos_response(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            with self.assertRaisesRegex(PlanError, "head/wing"):
                plan_case(
                    root,
                    task="rpa",
                    system_type="2d",
                    response_method="sos",
                    headwing=False,
                    profile_id=PROFILE_ID,
                )
            with self.assertRaisesRegex(PlanError, "SOS"):
                plan_case(
                    root,
                    task="rpa",
                    system_type="2d",
                    response_method="sternheimer",
                    headwing=True,
                    profile_id=PROFILE_ID,
                )
            with self.assertRaisesRegex(PlanError, "only admits"):
                plan_case(
                    root,
                    task="gw",
                    system_type="2d",
                    headwing=True,
                    profile_id=PROFILE_ID,
                )

    def test_validate_case_accepts_the_pinned_input_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            report = validate_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                use_symmetry=True,
                headwing=True,
                profile_id=PROFILE_ID,
                stage="input",
            )

        self.assertTrue(report.accepted, report.to_dict())
        gates = {gate.gate_id: gate for gate in report.gates}
        self.assertEqual(gates["route.strict_2d_sos_rpa"].status, "PASS")
        self.assertEqual(gates["librpa.strict_2d_sos_rpa"].status, "PASS")
        self.assertEqual(gates["pyatb.policy"].status, "PASS")

    def test_validate_case_rejects_head_only_and_frequency_drift(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self.make_case(root)
            librpa = root / "librpa.in"
            librpa.write_text(
                librpa.read_text(encoding="utf-8").replace("nfreq = 16", "nfreq = 14")
                + "head_only = t\n",
                encoding="utf-8",
            )
            report = validate_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                use_symmetry=True,
                headwing=True,
                profile_id=PROFILE_ID,
                stage="input",
            )

        self.assertFalse(report.accepted)
        gates = {gate.gate_id: gate for gate in report.gates}
        self.assertEqual(gates["librpa.frequency_grid"].status, "FAIL")
        self.assertEqual(gates["librpa.strict_2d_sos_rpa"].status, "FAIL")

    def test_pre_librpa_validation_requires_the_coulomb_head_artifact(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            test_validators.WorkflowValidatorTest().make_case(
                root,
                task="rpa",
                headwing=True,
                use_symmetry=True,
            )
            librpa = root / "librpa.in"
            librpa.write_text(
                librpa.read_text(encoding="utf-8")
                + "nfreq = 16\n"
                + "option_dielect_func = 3\n"
                + "use_2d_dielectric = t\n"
                + "use_pyatb = t\n"
                + "rpa_headwing_mode = qavg\n"
                + "rpa_headwing_body_start = 1\n",
                encoding="utf-8",
            )
            missing = validate_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                use_symmetry=True,
                headwing=True,
                profile_id=PROFILE_ID,
                stage="pre_librpa",
            )
            head_artifact = root / "dataset" / "librpa_2d_coulomb_head.dat"
            head_artifact.touch()
            empty = validate_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                use_symmetry=True,
                headwing=True,
                profile_id=PROFILE_ID,
                stage="pre_librpa",
            )
            head_artifact.write_text(
                "validated producer artifact\n",
                encoding="utf-8",
            )
            present = validate_case(
                root,
                task="rpa",
                system_type="2d",
                response_method="sos",
                use_symmetry=True,
                headwing=True,
                profile_id=PROFILE_ID,
                stage="pre_librpa",
            )

        missing_gate = {gate.gate_id: gate for gate in missing.gates}["strict2d.coulomb_head"]
        empty_gate = {gate.gate_id: gate for gate in empty.gates}["strict2d.coulomb_head"]
        present_gate = {gate.gate_id: gate for gate in present.gates}["strict2d.coulomb_head"]
        self.assertEqual(missing_gate.status, "FAIL")
        self.assertEqual(empty_gate.status, "FAIL")
        self.assertEqual(present_gate.status, "PASS")
        self.assertTrue(present.accepted, present.to_dict())

    def test_admission_manifest_records_four_validated_meshes_and_nohw_controls(self):
        manifest = load_admission_manifest(manifest_id=MANIFEST_ID)
        gates = {
            gate
            for level in manifest["levels"]
            for case in level["cases"]
            for gate in case["gates"]
        }

        self.assertEqual(manifest["profile_id"], PROFILE_ID)
        self.assertEqual(manifest["host"]["partition"], "normal")
        self.assertEqual(manifest["host"]["remote_root"], "/work1/ghj/strict2d_rpa_validation_20260901")
        self.assertEqual(manifest["route"]["route_id"], "strict_2d_sos_rpa")
        self.assertEqual(manifest["route"]["status"], "TESTABLE")
        self.assertEqual(
            {case["mesh"] for case in manifest["validated_cases"]},
            {8, 10, 12, 16},
        )
        self.assertTrue(all(case["status"] == "PASS" for case in manifest["validated_cases"]))
        self.assertEqual(
            {case["mesh"] for case in manifest["validation_controls"]},
            {8, 10, 12, 16},
        )
        self.assertTrue(
            all(
                case["route"] == "diagnostic_no_headwing"
                and case["physical_route"] is False
                and case["status"] == "PASS_FINITE_Q_CONTROL_RAW_GAMMA_COMPLEX"
                for case in manifest["validation_controls"]
            )
        )
        self.assertFalse(manifest["k_mesh_claim"]["convergence_exponent_established"])
        self.assertFalse(manifest["k_mesh_claim"]["asymptotic_fit_stable"])
        self.assertEqual(manifest["k_mesh_claim"]["mesh_count"], 4)
        self.assertEqual(manifest["k_mesh_claim"]["observed_free_power"], 2.642)
        self.assertLess(manifest["k_mesh_claim"]["fixed_n_minus_3_rms_millihartree"], 0.5)
        self.assertTrue(
            {
                "source_tests_pass",
                "producer_complete",
                "duplicate_job_check",
                "partition_normal",
                "work_paths_under_work1",
                "mpi_world_size_4",
                "qavg_weight_sum",
                "finite_energies",
                "negligible_imaginary_energy",
                "qsum_matches_total",
                "lu_info_zero",
                "mpi_singleton_consistency",
                "k_mesh_validation_scope",
            }.issubset(gates)
        )

    def test_packaged_manifest_matches_repository_audit_copy(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        name = f"{MANIFEST_ID}.json"
        repository = json.loads((root / "admission" / name).read_text(encoding="utf-8"))
        packaged = json.loads(
            (root / "oml_mcp" / "admission_manifests" / name).read_text(encoding="utf-8")
        )

        self.assertEqual(packaged, repository)

    def test_admission_manifest_rejects_debug_or_an_asymptotic_convergence_claim(self):
        manifest = load_admission_manifest(manifest_id=MANIFEST_ID)
        manifest["host"]["partition"] = "debug"
        with self.assertRaisesRegex(AdmissionManifestError, "normal"):
            validate_admission_manifest(manifest)

        manifest = load_admission_manifest(manifest_id=MANIFEST_ID)
        manifest["k_mesh_claim"]["convergence_exponent_established"] = True
        with self.assertRaisesRegex(AdmissionManifestError, "convergence"):
            validate_admission_manifest(manifest)

    def test_admission_manifest_rejects_remote_receipt_drift(self):
        manifest = load_admission_manifest(manifest_id=MANIFEST_ID)
        manifest["validated_cases"][0]["validation_sha256"] = "0" * 64

        with self.assertRaisesRegex(AdmissionManifestError, "immutable remote receipt"):
            validate_admission_manifest(manifest)


class Strict2dSosRpaServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_plan_and_validate_expose_the_registered_route(self):
        server = build_server()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            Strict2dSosRpaProfileTest.make_case(root)
            planned = await server.call_tool(
                "plan_case",
                {
                    "path": str(root),
                    "task": "rpa",
                    "system_type": "2d",
                    "response_method": "sos",
                    "headwing": True,
                    "use_symmetry": True,
                    "profile_id": PROFILE_ID,
                },
            )
            validated = await server.call_tool(
                "validate_case",
                {
                    "path": str(root),
                    "task": "rpa",
                    "system_type": "2d",
                    "response_method": "sos",
                    "headwing": True,
                    "use_symmetry": True,
                    "profile_id": PROFILE_ID,
                    "stage": "input",
                },
            )

        self.assertFalse(planned.is_error, planned.content)
        self.assertEqual(planned.structured_content["route"], "strict_2d_sos_rpa")
        self.assertFalse(validated.is_error, validated.content)
        self.assertTrue(validated.structured_content["accepted"], validated.structured_content)

    async def test_mcp_inspects_the_registered_df_dcu_admission_manifest(self):
        server = build_server()
        result = await server.call_tool(
            "inspect_admission_manifest",
            {"manifest_id": MANIFEST_ID},
        )

        self.assertFalse(result.is_error, result.content)
        self.assertEqual(result.structured_content["manifest_id"], MANIFEST_ID)
        self.assertEqual(result.structured_content["route"]["route_id"], "strict_2d_sos_rpa")


if __name__ == "__main__":
    unittest.main()
