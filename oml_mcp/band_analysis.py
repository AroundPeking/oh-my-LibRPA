"""Band-structure analysis gates for the automated loop.

The parser is the existing ``scientific_bands`` ABACUS reader, so the files
must keep their ``KS_band_spin_<n>.dat`` / ``EXX_...`` / ``GW_...`` names. On top
of it this module provides the checks the retry rules need:

* nearest-neighbour band reordering (for smoothness and plotting),
* a curvature (second-difference) smoothness gate with a robust threshold,
* layer localization (EXX-relative-to-KS versus GW-relative-to-EXX),
* indirect/direct gaps and a reference-gap comparison.

These are reference-free diagnostics: a pass means "no detectable artifact",
not "physically validated".
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .scientific_bands import ScientificBandError, parse_band_table


LAYERS = ("ks", "exx", "gw")
DEFAULT_SMOOTHNESS_FLOOR_EV = 0.05
DEFAULT_LOCALIZATION_FLOOR_EV = 0.02
DEFAULT_LOCALIZATION_Z = 6.0
LARGE_RANGE_FRACTION = 0.20
# A curvature gate on fewer than five k points measures the path segments,
# not the band shape; coarse paths are reported as not evaluated instead of
# producing false alarms.
MIN_CURVATURE_KPOINTS = 5


class BandAnalysisError(ValueError):
    """Raised when band tables cannot be aligned or interpreted."""


@dataclass(frozen=True)
class BandLayer:
    quantity: str
    kpoints: tuple[tuple[float, float, float], ...]
    energies: tuple[tuple[float, ...], ...]
    occupations: tuple[tuple[float, ...], ...]

    @property
    def nkpoints(self) -> int:
        return len(self.energies)

    @property
    def nbands(self) -> int:
        return len(self.energies[0]) if self.energies else 0


def load_layer(path: str | Path, *, quantity: str) -> BandLayer:
    try:
        table = parse_band_table(path, quantity=quantity)
    except ScientificBandError as exc:
        raise BandAnalysisError(str(exc)) from exc
    rows = table["rows"]
    if not rows:
        raise BandAnalysisError(f"{path}: no k-point rows")
    return BandLayer(
        quantity=quantity,
        kpoints=tuple(tuple(row["kpoint"]) for row in rows),
        energies=tuple(tuple(row["energies_ev"]) for row in rows),
        occupations=tuple(tuple(row["occupations"]) for row in rows),
    )


def _median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def _mad(values: Sequence[float], center: float) -> float:
    return _median([abs(value - center) for value in values])


def reorder_by_nearest(layer: BandLayer) -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[float, ...], ...]]:
    """Track each band across k by nearest energy; return original indices and energies."""
    if layer.nkpoints == 0 or layer.nbands == 0:
        raise BandAnalysisError("cannot reorder an empty band table")
    orders: list[tuple[int, ...]] = [tuple(range(layer.nbands))]
    rows: list[tuple[float, ...]] = [layer.energies[0]]
    for k in range(1, layer.nkpoints):
        previous = rows[-1]
        current = layer.energies[k]
        remaining = list(range(layer.nbands))
        row = [0.0] * layer.nbands
        order = [0] * layer.nbands
        for band, target in enumerate(previous):
            best = min(remaining, key=lambda candidate: (abs(current[candidate] - target), candidate))
            row[band] = current[best]
            order[band] = best
            remaining.remove(best)
        rows.append(tuple(row))
        orders.append(tuple(order))
    return tuple(orders), tuple(rows)


def _second_differences(rows: Sequence[Sequence[float]]) -> list[list[float]]:
    if len(rows) < 3:
        return []
    nbands = len(rows[0])
    return [
        [rows[k + 1][band] - 2.0 * rows[k][band] + rows[k - 1][band] for band in range(nbands)]
        for k in range(1, len(rows) - 1)
    ]


def smoothness(
    rows: Sequence[Sequence[float]],
    *,
    z_threshold: float = DEFAULT_LOCALIZATION_Z,
    floor_ev: float = DEFAULT_SMOOTHNESS_FLOOR_EV,
) -> dict[str, Any]:
    """Flag bands whose second difference along k exceeds a robust threshold."""
    curvature = _second_differences(rows)
    if len(rows) < MIN_CURVATURE_KPOINTS:
        return {
            "evaluated": False,
            "smooth": None,
            "reason": f"at least {MIN_CURVATURE_KPOINTS} k points are required for a curvature gate",
            "max_curvature_ev": None,
            "outliers": [],
        }
    magnitudes = [abs(value) for row in curvature for value in row]
    center = _median(magnitudes)
    spread = _mad(magnitudes, center)
    outliers = []
    for k_index, row in enumerate(curvature, start=1):
        for band, value in enumerate(row):
            limit = max(floor_ev, center + z_threshold * spread)
            if abs(value) > limit:
                outliers.append(
                    {
                        "k_index": k_index,
                        "band": band,
                        "curvature_ev": value,
                    }
                )
    return {
        "evaluated": True,
        "smooth": not outliers,
        "max_curvature_ev": max(magnitudes),
        "median_curvature_ev": center,
        "threshold_ev": max(floor_ev, center + z_threshold * spread),
        "outliers": outliers,
    }


def _layer_extent(
    delta: Sequence[Sequence[float]],
    *,
    z_threshold: float,
    floor_ev: float,
) -> dict[str, Any]:
    curvature = _second_differences(delta)
    if not curvature:
        return {
            "evaluated": False,
            "anomaly_count": 0,
            "extent": 0.0,
            "classification": "not_evaluated",
            "outliers": [],
        }
    magnitudes = [abs(value) for row in curvature for value in row]
    center = _median(magnitudes)
    spread = _mad(magnitudes, center)
    limit = max(floor_ev, center + z_threshold * spread)
    outliers = []
    for k_index, row in enumerate(curvature, start=1):
        for band, value in enumerate(row):
            if abs(value) > limit and abs(value) > floor_ev:
                outliers.append({"k_index": k_index, "band": band, "curvature_ev": value})
    total = len(curvature) * len(curvature[0])
    extent = len(outliers) / total if total else 0.0
    return {
        "evaluated": True,
        "anomaly_count": len(outliers),
        "extent": extent,
        "classification": (
            "large_range" if outliers and extent >= LARGE_RANGE_FRACTION
            else ("small_range" if outliers else "none")
        ),
        "threshold_ev": limit,
        "outliers": outliers,
    }


def localization(
    ks: BandLayer,
    exx: BandLayer,
    gw: BandLayer,
    *,
    z_threshold: float = DEFAULT_LOCALIZATION_Z,
    floor_ev: float = DEFAULT_LOCALIZATION_FLOOR_EV,
) -> dict[str, Any]:
    """Locate which layer (EXX or GW) introduces the larger anomaly."""
    for layer in (exx, gw):
        if layer.nkpoints != ks.nkpoints or layer.nbands != ks.nbands:
            raise BandAnalysisError("KS, EXX and GW tables must share the k grid and state count")
    if ks.nkpoints < MIN_CURVATURE_KPOINTS:
        return {
            "evaluated": False,
            "layer": "not_evaluated",
            "consistent": None,
            "reason": f"at least {MIN_CURVATURE_KPOINTS} k points are required for layer localization",
            "exx_minus_ks": {"evaluated": False, "anomaly_count": 0, "extent": 0.0, "classification": "not_evaluated", "outliers": []},
            "gw_minus_exx": {"evaluated": False, "anomaly_count": 0, "extent": 0.0, "classification": "not_evaluated", "outliers": []},
        }
    exx_delta = [
        [exx.energies[k][band] - ks.energies[k][band] for band in range(ks.nbands)]
        for k in range(ks.nkpoints)
    ]
    gw_delta = [
        [gw.energies[k][band] - exx.energies[k][band] for band in range(ks.nbands)]
        for k in range(ks.nkpoints)
    ]
    exx_report = _layer_extent(exx_delta, z_threshold=z_threshold, floor_ev=floor_ev)
    gw_report = _layer_extent(gw_delta, z_threshold=z_threshold, floor_ev=floor_ev)
    exx_count = exx_report["anomaly_count"]
    gw_count = gw_report["anomaly_count"]
    if exx_count and gw_count:
        if exx_count >= 1.5 * gw_count:
            layer = "exx"
        elif gw_count >= 1.5 * exx_count:
            layer = "gw"
        else:
            layer = "both"
    elif exx_count:
        layer = "exx"
    elif gw_count:
        layer = "gw"
    else:
        layer = "none"
    return {
        "evaluated": True,
        "layer": layer,
        "exx_minus_ks": exx_report,
        "gw_minus_exx": gw_report,
        "consistent": layer == "none",
    }


def gaps(layer: BandLayer, *, occupied_bands: int | None = None) -> dict[str, Any]:
    """Return VBM/CBM and indirect/direct gaps from occupations or a band count."""
    if occupied_bands is None:
        counts = [sum(1 for value in row if value > 0.5) for row in layer.occupations]
        if not counts or min(counts) == 0:
            raise BandAnalysisError("cannot derive the occupied-band count from occupations")
        occupied_bands = min(counts)
    if occupied_bands <= 0 or occupied_bands >= layer.nbands:
        raise BandAnalysisError(
            f"occupied band count {occupied_bands} must leave at least one empty band"
        )
    vbm = max(layer.energies[k][occupied_bands - 1] for k in range(layer.nkpoints))
    cbm = min(layer.energies[k][occupied_bands] for k in range(layer.nkpoints))
    direct = min(
        layer.energies[k][occupied_bands] - layer.energies[k][occupied_bands - 1]
        for k in range(layer.nkpoints)
    )
    return {
        "occupied_bands": occupied_bands,
        "vbm_ev": vbm,
        "cbm_ev": cbm,
        "indirect_gap_ev": cbm - vbm,
        "direct_gap_ev": direct,
    }


def compare_gap(
    value_ev: float,
    reference_ev: float,
    *,
    tolerance_ev: float = 0.2,
) -> dict[str, Any]:
    delta = value_ev - reference_ev
    return {
        "value_ev": value_ev,
        "reference_ev": reference_ev,
        "delta_ev": delta,
        "tolerance_ev": tolerance_ev,
        "pass": abs(delta) <= tolerance_ev,
    }


def analyze_band_set(
    roots: dict[str, str | Path],
    *,
    occupied_bands: int | None = None,
    gap_reference_ev: float | None = None,
    gap_tolerance_ev: float = 0.2,
    smoothness_floor_ev: float = DEFAULT_SMOOTHNESS_FLOOR_EV,
    localization_floor_ev: float = DEFAULT_LOCALIZATION_FLOOR_EV,
) -> dict[str, Any]:
    """Run the reference-free band gates on a KS/EXX/GW triple."""
    paths = {layer: Path(roots[layer]) for layer in LAYERS}
    layers = {layer: load_layer(paths[layer], quantity=layer) for layer in LAYERS}
    for layer in ("exx", "gw"):
        if layers[layer].nkpoints != layers["ks"].nkpoints or layers[layer].nbands != layers["ks"].nbands:
            raise BandAnalysisError("KS, EXX and GW tables must share the k grid and state count")

    reordered = {layer: reorder_by_nearest(layers[layer])[1] for layer in LAYERS}
    smoothness_reports = {
        layer: smoothness(reordered[layer], floor_ev=smoothness_floor_ev) for layer in LAYERS
    }
    localization_report = localization(
        layers["ks"], layers["exx"], layers["gw"], floor_ev=localization_floor_ev
    )
    gap_reports = {
        layer: gaps(layers[layer], occupied_bands=occupied_bands) for layer in LAYERS
    }
    gap_check = None
    if gap_reference_ev is not None:
        gap_check = compare_gap(
            gap_reports["gw"]["indirect_gap_ev"],
            gap_reference_ev,
            tolerance_ev=gap_tolerance_ev,
        )

    reasons: list[str] = []
    for layer, report in smoothness_reports.items():
        if report["evaluated"] and not report["smooth"]:
            reasons.append(f"non-smooth bands in {layer}")
    if localization_report.get("evaluated") and not localization_report["consistent"]:
        reasons.append(f"layer anomaly located in {localization_report['layer']}")
    if gap_check is not None and not gap_check["pass"]:
        reasons.append(
            f"GW gap {gap_check['value_ev']:.3f} eV differs from the reference by "
            f"{gap_check['delta_ev']:+.3f} eV (tolerance {gap_check['tolerance_ev']} eV)"
        )
    evaluated_any = (
        any(report["evaluated"] for report in smoothness_reports.values())
        or bool(localization_report.get("evaluated"))
        or gap_check is not None
    )
    if not evaluated_any:
        reasons.append("no band gate was evaluable (coarse k path and no gap reference)")
    accepted = evaluated_any and not reasons
    return {
        "accepted": accepted,
        "reasons": reasons,
        "smoothness": smoothness_reports,
        "localization": localization_report,
        "gaps": gap_reports,
        "gap_check": gap_check,
        "sources": {layer: str(path) for layer, path in paths.items()},
    }
