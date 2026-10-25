import unittest

from oml_mcp.evolution import EvolutionBudget, EvolutionUsage
from oml_mcp.parameter_prescriptions import (
    ParameterPrescriptionError,
    apply_prescription,
    load_prescription,
    tune_parameter,
)


class ParameterPrescriptionTest(unittest.TestCase):
    def test_default_route_prescription_loads(self):
        prescription = load_prescription("periodic_3d_gw", "default")

        self.assertEqual(prescription.route_id, "periodic_3d_gw")
        self.assertEqual(prescription.material_class, "default")
        self.assertIn("exx_cs_inv_thr", prescription.parameters)
        self.assertIn("basis_family", prescription.parameters)
        self.assertIn("nbands", prescription.parameters)
        self.assertEqual(prescription.parameters["exx_cs_inv_thr"].default, -1.0)

    def test_material_class_falls_back_to_the_single_default(self):
        default = load_prescription("periodic_3d_gw", "default")
        material = load_prescription("periodic_3d_gw", "transition_metal_oxide_gw")

        self.assertEqual(set(material.parameters), set(default.parameters))
        self.assertEqual(material.parameters["exx_cs_inv_thr"].default, -1.0)
        self.assertEqual(material.parameters["exx_cs_inv_thr"].target, 1e-5)
        self.assertEqual(material.parameters["nfreq"].target, 16)

    def test_apply_prescription_fills_only_absent_keys(self):
        definition = {"nfreq": 32, "nbands": 48, "screening_kgrid": [4, 4, 4]}
        result = apply_prescription(
            "periodic_3d_gw", "transition_metal_oxide_gw", definition=definition
        )

        # The candidate definition WINS on every key it carries: a prescription
        # baseline may only fill keys the definition does not declare, or an
        # evolution round would silently run the defaults instead of the
        # proposed definition (observed live: nfreq 24 -> prescription 8).
        self.assertEqual(
            result["applied"],
            {
                "exx_cs_inv_thr": 1e-5,
                "basis_family": "dojo_nc_sr_tzdp",
                "nao_family": "tzdp",
                "shrink_threshold": 0.001,
            },
        )
        self.assertEqual(result["definition"]["nfreq"], 32)
        self.assertEqual(result["definition"]["screening_kgrid"], [4, 4, 4])
        # nbands must equal nbasis (system-dependent), so it is never pinned.
        self.assertNotIn("nbands", result["applied"])
        self.assertEqual(result["definition"]["nbands"], 48)  # untouched

    def test_all_system_families_resolve_to_the_single_default(self):
        from oml_mcp.parameter_prescriptions import list_system_families

        baseline = apply_prescription("periodic_3d_gw", "default", definition={})["applied"]
        self.assertEqual(baseline["exx_cs_inv_thr"], 1e-5)
        self.assertEqual(baseline["nfreq"], 16)
        for family in list_system_families():
            if family == "isolated_molecule_rpa":
                continue
            with self.subTest(family=family):
                result = apply_prescription("periodic_3d_gw", family, definition={})
                self.assertEqual(result["applied"], baseline)

    def test_tune_parameter_is_proposal_only(self):
        proposal = tune_parameter(
            route_id="periodic_3d_gw",
            material_class="transition_metal_oxide_gw",
            baseline={"exx_cs_inv_thr": -1, "nfreq": 24},
            axis="exx_cs_inv_thr",
            value=1e-5,
        )

        self.assertEqual(proposal.status, "PROPOSAL_ONLY")
        self.assertEqual(proposal.changed_axis, "exx_cs_inv_thr")
        self.assertEqual(proposal.candidate["exx_cs_inv_thr"], 1e-5)
        self.assertNotIn("command", proposal.to_dict())
        self.assertNotIn("submit", proposal.to_dict())

    def test_tune_parameter_rejects_out_of_range_value(self):
        with self.assertRaisesRegex(ParameterPrescriptionError, "outside the allowed range"):
            tune_parameter(
                route_id="periodic_3d_gw",
                material_class="transition_metal_oxide_gw",
                baseline={"exx_cs_inv_thr": -1},
                axis="exx_cs_inv_thr",
                value=10.0,
            )

    def test_tune_parameter_rejects_unprescribed_axis(self):
        with self.assertRaisesRegex(ParameterPrescriptionError, "not prescribed"):
            tune_parameter(
                route_id="periodic_3d_gw",
                material_class="transition_metal_oxide_gw",
                baseline={"nfreq": 24},
                axis="vacuum",
                value=20.0,
            )

    def test_load_rejects_unregistered_route(self):
        with self.assertRaisesRegex(ParameterPrescriptionError, "not registered"):
            load_prescription("direct_mixed_fourier", "default")

    def test_load_rejects_unknown_material_class(self):
        with self.assertRaisesRegex(ParameterPrescriptionError, "no prescription"):
            load_prescription("periodic_3d_gw", "not_a_material")

    def test_symmetry_variant_is_folded_into_periodic_3d_gw(self):
        # The planner maps the symmetry variant to capability periodic_3d_gw, so
        # there is no separate periodic_3d_gw_symmetry mutation axis or prescription.
        with self.assertRaisesRegex(ParameterPrescriptionError, "not registered"):
            load_prescription("periodic_3d_gw_symmetry", "default")
        # The plain capability prescription carries the symmetry-aware rule for the
        # exx_cs_inv_thr axis.
        prescription = load_prescription("periodic_3d_gw", "default")
        self.assertEqual(prescription.parameters["exx_cs_inv_thr"].target, 1e-5)

    def test_apply_prescription_without_definition_returns_prescription_dict(self):
        result = apply_prescription("periodic_3d_gw", "default")

        self.assertEqual(result["schema"], "oml.parameter-prescription.v1")
        self.assertIn("parameters", result)


if __name__ == "__main__":
    unittest.main()
