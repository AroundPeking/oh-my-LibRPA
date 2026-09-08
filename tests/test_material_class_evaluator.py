import copy
import pathlib
import tempfile
import unittest


from oml_mcp.material_class_evaluator import (
    MaterialClassEvaluationError,
    evaluate_material_class,
)
from oml_mcp.scientific_bands import (
    ScientificBandError,
    load_band_bundle,
    select_spin_resolved_window,
)
from oml_mcp.server import build_server


# Frozen identity asset hashes (from oml_mcp/material_classes/*.json).
ALTE_ASSETS = {
    "pseudopotentials": {
        "Mn.upf": "b10dafc764626a02dc590b2e9789989f480d866f65c4974692422d8cd07da7c0",
        "Te.upf": "3bbcefd1a5d6ff89c1d4d94f27abec6f1702bb5fc2d7fda701369d4fbda53116",
    },
    "orbitals": {
        "Mn_gga_10au_100Ry_6s3p3d2f.orb": "4ce1a91eef11dd95f5f17a9ecb07bdcef2eddde7dc6f1caeda5c5b50137b0539",
        "Te_gga_10au_100Ry_3s3p3d2f.orb": "da8b64515933d34464497dcbf4c84e1484d4cfc7a7a00045ce44aff6bc7bb4bc",
    },
    "auxiliary_bases": {
        "Mn_gth_10au_6s3p3d2f1g_pca1e-4_naux356.abfs": "40cfb935e191483c8abdff494f02c0db46c1dfd029675ee83b47e829530b2e7f",
        "Te_gth_10au_3s3p3d2f1g_pca1e-4_naux356.abfs": "6ac010348b31b3bba6eda1f9135a1969ed80d4e38f5abefd1b8e917c83687c30",
    },
}

PERO_ASSETS = {
    "pseudopotentials": {
        "Sr.upf": "1c3bc7a8bcda41b8d18dd308015102e6c96aedf3c90af7cfad2ef2d3087b70ef",
        "Ti.upf": "c33e68554a687043cdd03f175f0c482b4ba30c41b93cb5f75ee46da96fcc4506",
        "O.upf": "2a543889f6522e2a1f94e2c2ff1477e61cb89f25c67b27c54940e8263ec6fb11",
    },
    "orbitals": {
        "Sr_gga_10au_100Ry_6s3p2d.orb": "50dcca7713720aaf1ec1e4c849dd2794892a6ec48df45af45e0ed95eb50256ce",
        "Ti_gga_10au_100Ry_6s3p3d2f.orb": "9c756a056d24ef27460283525f678b2e050cfe5e81dd8635baf9e8799ae85c0b",
        "O_gga_10au_100Ry_3s3p2d.orb": "b3b513a19280916a2230f4699c54e5ec1f22a705d735b3a4ac772f637c9bd29f",
    },
    "auxiliary_bases": None,
}


def _make_run(material_class_id: str, *, nspin: int, soc: bool, states):
    if material_class_id == "altermagnet_gw":
        assets = copy.deepcopy(ALTE_ASSETS)
    elif material_class_id == "perovskite_gw":
        assets = copy.deepcopy(PERO_ASSETS)
    else:
        raise AssertionError(f"unhandled class in fixture: {material_class_id}")
    return {
        "assets": assets,
        "nspin": nspin,
        "soc": soc,
        "occupied_value": 1.0 if nspin >= 2 else 2.0,
        "padding": 3,
        "window": {
            "spins": list(range(1, nspin + 1)),
            "nbands": 12,
            "states": states,
        },
    }


def _kpoint(k_index: int) -> list[float]:
    return [0.375, 0.0, 0.1667 * (k_index + 1)]


def _states(*, nspin: int, nkpoints: int, nbands: int, occupied_per_spin: int):
    """Build an insulating state window. Occupation is 2.0 (nspin=1) or 1.0 (nspin>=2)."""
    occ_value = 2.0 if nspin == 1 else 1.0
    states = []
    for spin in range(1, nspin + 1):
        for k_index in range(nkpoints):
            kpoint = _kpoint(k_index)
            for band in range(1, nbands + 1):
                occ = occ_value if band <= occupied_per_spin else 0.0
                states.append({
                    "spin": spin,
                    "kpoint": kpoint,
                    "band": band,
                    "occupation": occ,
                    "ks_ev": 2.0 + band,
                    "exx_ev": 1.5 + band,
                    "gw_ev": 1.0 + band,
                })
    return states


def _altermagnet_run():
    return _make_run(
        "altermagnet_gw",
        nspin=2,
        soc=False,
        states=_states(nspin=2, nkpoints=2, nbands=12, occupied_per_spin=4),
    )


def _perovskite_run():
    return _make_run(
        "perovskite_gw",
        nspin=1,
        soc=False,
        states=_states(nspin=1, nkpoints=2, nbands=12, occupied_per_spin=4),
    )


class SpinResolvedWindowTest(unittest.TestCase):
    def _write_bundle(self, root, *, nspin, nkpoints, nbands, occ_by_spin):
        for spin in range(1, nspin + 1):
            occupations = occ_by_spin[spin]
            ks = [tuple(2.0 + b for b in range(nbands)) for _ in range(nkpoints)]
            exx = [tuple(1.5 + b for b in range(nbands)) for _ in range(nkpoints)]
            gw = [tuple(1.0 + b for b in range(nbands)) for _ in range(nkpoints)]
            for quantity, energies in (("KS", ks), ("EXX", exx), ("GW", gw)):
                rows = []
                for k_index, (occ_row, ks_row) in enumerate(zip(occupations, energies, strict=True)):
                    kpoint = _kpoint(k_index)
                    tokens = [str(k_index + 1), *(f"{v:.8f}" for v in kpoint)]
                    for occupation, energy in zip(occ_row, ks_row, strict=True):
                        tokens.extend((f"{occupation:.8f}", str(energy)))
                    rows.append(" ".join(tokens))
                (root / f"{quantity}_band_spin_{spin}.dat").write_text(
                    "\n".join(rows) + "\n", encoding="utf-8"
                )

    def test_select_spin_resolved_window_supports_nspin2(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            occ = ([1.0, 1.0, 1.0, 1.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
            self._write_bundle(root, nspin=2, nkpoints=2, nbands=6, occ_by_spin={1: occ, 2: occ})
            bundle = load_band_bundle(root)
            window = select_spin_resolved_window(bundle, occupied_value=1.0, padding=2)

        self.assertEqual(window["spins"], [1, 2])
        self.assertEqual(window["vbm_band_by_spin"], {1: 4, 2: 4})
        self.assertEqual(window["cbm_band_by_spin"], {1: 5, 2: 5})
        # padding=2 -> bands 2..6 (5 bands) per spin, 2 spins, 2 k-points.
        self.assertEqual(window["state_count"], 5 * 2 * 2)
        self.assertEqual(len(window["spin_windows"]), 2)
        self.assertIn("fundamental_gw_gap_ev", window)
        self.assertIsInstance(window["fundamental_gw_gap_ev"], float)

    def test_select_spin_resolved_window_rejects_partial_occupation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            occ = ([1.0, 1.0, 1.0, 1.0, 0.0, 0.0], [1.0, 1.0, 1.0, 0.5, 0.0, 0.0])
            self._write_bundle(root, nspin=2, nkpoints=2, nbands=6, occ_by_spin={1: occ, 2: occ})
            bundle = load_band_bundle(root)
            with self.assertRaisesRegex(ScientificBandError, "partial occupations"):
                select_spin_resolved_window(bundle, occupied_value=1.0, padding=2)

    def test_select_spin_resolved_window_rejects_varying_occupation_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            occ = ([1.0, 1.0, 1.0, 1.0, 0.0, 0.0], [1.0, 1.0, 1.0, 0.0, 0.0, 0.0])
            self._write_bundle(root, nspin=2, nkpoints=2, nbands=6, occ_by_spin={1: occ, 2: occ})
            bundle = load_band_bundle(root)
            with self.assertRaisesRegex(ScientificBandError, "occupied-band count changes"):
                select_spin_resolved_window(bundle, occupied_value=1.0, padding=2)

    def test_select_spin_resolved_window_global_gap_crosses_spins(self):
        # Spin 1 has a higher VBM than spin 2, so the fundamental gap must be taken
        # across the whole spin manifold (max VBM, min CBM), not per spin.
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            # nkpoints=1 so the occupation pattern is trivially constant.
            occ = ([1.0, 1.0, 1.0, 1.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
            # Custom energies: make spin 2's VBM (band 4) higher in GW than spin 1's.
            for quantity, base in (("KS", 2.0), ("EXX", 1.5), ("GW", 1.0)):
                for spin in (1, 2):
                    kpoint = (0.375, 0.0, 0.1667)
                    tokens = ["1", *(f"{v:.8f}" for v in kpoint)]
                    for band in range(1, 7):
                        energy = base + band
                        if quantity == "GW" and spin == 2 and band == 4:
                            energy = base + band + 3.0
                        tokens.extend((f"{occ[spin-1][band-1]:.8f}", str(energy)))
                    (root / f"{quantity}_band_spin_{spin}.dat").write_text(
                        " ".join(tokens) + "\n", encoding="utf-8"
                    )
            bundle = load_band_bundle(root)
            window = select_spin_resolved_window(bundle, occupied_value=1.0, padding=2)

        # Spin 2 VBM gw = 1.0+4+3.0 = 8.0, which is the global max VBM.
        self.assertEqual(window["vbm_state"]["spin"], 2)
        self.assertEqual(window["vbm_state"]["gw_ev"], 8.0)
        self.assertEqual(window["fundamental_gw_gap_ev"], 1.0 + 5.0 - 8.0)


class MaterialClassEvaluatorTest(unittest.TestCase):
    def test_pending_altermagnet_blocks_but_freezes_identity(self):
        result = evaluate_material_class("altermagnet_gw", _altermagnet_run())

        self.assertEqual(result["material_class_id"], "altermagnet_gw")
        self.assertEqual(result["reference_status"], "REFERENCE_PENDING")
        self.assertEqual(result["status"], "REFERENCE_PENDING")
        self.assertEqual(result["scientific_status"], "NOT_EVALUATED")
        self.assertEqual(result["promotion_eligibility"], "BLOCKED")
        gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
        self.assertEqual(gates["identity.assets.pseudopotentials"], "PASS")
        self.assertEqual(gates["identity.assets.orbitals"], "PASS")
        self.assertEqual(gates["identity.assets.auxiliary_bases"], "PASS")
        self.assertEqual(gates["identity.assets.present"], "PASS")
        self.assertEqual(gates["identity.software"], "PASS")
        self.assertEqual(gates["contract.spin"], "PASS")
        self.assertEqual(gates["window.valid"], "PASS")
        self.assertEqual(gates["reference.status"], "FAIL")
        self.assertEqual(result["window"]["spins"], [1, 2])

    def test_asset_hash_mismatch_fails_identity_gate(self):
        run = _altermagnet_run()
        run["assets"]["pseudopotentials"]["Mn.upf"] = "0" * 64

        result = evaluate_material_class("altermagnet_gw", run)

        gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
        self.assertEqual(gates["identity.assets.pseudopotentials"], "FAIL")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["promotion_eligibility"], "BLOCKED")

    def test_missing_identity_asset_fails(self):
        run = _altermagnet_run()
        del run["assets"]["orbitals"]["Mn_gga_10au_100Ry_6s3p3d2f.orb"]

        result = evaluate_material_class("altermagnet_gw", run)

        gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
        self.assertEqual(gates["identity.assets.orbitals"], "FAIL")
        self.assertEqual(result["status"], "FAIL")

    def test_spin_contract_mismatch_fails(self):
        # The altermagnet identity requires nspin=2. A nspin=1 run (with a valid
        # non-magnetic occupation pattern) must fail the spin contract.
        run = _make_run(
            "altermagnet_gw",
            nspin=1,
            soc=False,
            states=_states(nspin=1, nkpoints=2, nbands=12, occupied_per_spin=4),
        )

        result = evaluate_material_class("altermagnet_gw", run)

        gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
        self.assertEqual(gates["contract.spin"], "FAIL")
        self.assertEqual(result["status"], "FAIL")

    def test_soc_contract_mismatch_fails(self):
        run = _altermagnet_run()
        run["soc"] = True

        result = evaluate_material_class("altermagnet_gw", run)

        gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
        self.assertEqual(gates["contract.spin"], "FAIL")

    def test_non_insulating_window_fails(self):
        run = _altermagnet_run()
        run["window"]["states"][0]["occupation"] = 0.5

        with self.assertRaisesRegex(MaterialClassEvaluationError, "WINDOW_INVALID"):
            evaluate_material_class("altermagnet_gw", run)

    def test_perovskite_accepts_nspin1_contract(self):
        result = evaluate_material_class("perovskite_gw", _perovskite_run())

        self.assertEqual(result["reference_status"], "REFERENCE_PENDING")
        gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
        self.assertEqual(gates["contract.spin"], "PASS")
        self.assertEqual(gates["window.valid"], "PASS")
        self.assertEqual(gates["reference.status"], "FAIL")
        self.assertEqual(result["window"]["spins"], [1])

    def test_perovskite_rejects_spin2_run(self):
        # The perovskite identity is non-magnetic nspin=1. A spin-2 run must fail
        # the contract even if its occupations form a valid insulating pattern.
        run = _make_run(
            "perovskite_gw",
            nspin=2,
            soc=False,
            states=_states(nspin=2, nkpoints=2, nbands=12, occupied_per_spin=4),
        )
        result = evaluate_material_class("perovskite_gw", run)

        gates = {gate["gate_id"]: gate["status"] for gate in result["gates"]}
        self.assertEqual(gates["contract.spin"], "FAIL")
        self.assertEqual(result["status"], "FAIL")


class MaterialClassServerTest(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_inspects_material_class(self):
        server = build_server()
        inspected = await server.call_tool(
            "inspect_material_class", {"material_class_id": "altermagnet_gw"}
        )
        self.assertFalse(inspected.is_error, inspected.content)
        self.assertEqual(inspected.structured_content["reference_status"], "REFERENCE_PENDING")

    async def test_mcp_lists_material_classes(self):
        server = build_server()
        listed = await server.call_tool("list_material_classes", {})
        self.assertFalse(listed.is_error, listed.content)
        self.assertIn("altermagnet_gw", listed.structured_content["material_classes"])

    async def test_mcp_evaluates_material_class(self):
        server = build_server()
        result = await server.call_tool(
            "evaluate_material_class",
            {"material_class_id": "altermagnet_gw", "run": _altermagnet_run()},
        )
        self.assertFalse(result.is_error, result.content)
        payload = result.structured_content
        self.assertEqual(payload["material_class_id"], "altermagnet_gw")
        self.assertEqual(payload["reference_status"], "REFERENCE_PENDING")
        self.assertEqual(payload["status"], "REFERENCE_PENDING")


if __name__ == "__main__":
    unittest.main()
