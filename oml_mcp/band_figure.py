"""Render the KS / EXX / GW band-structure figure.

A gap number on its own cannot tell whether a band table is physical: it hides
a collapsed dispersion, a broken layer ordering, or a single absurd eigenvalue.
The band figure is therefore the acceptance artifact for the periodic GW
routes, and gap agreement with a database record is advisory only - it is
recorded next to the figure, not used to reject a run whose bands look right.

The renderer is deliberately dependency-light: matplotlib's non-interactive
"Agg" backend, one panel per layer, energies referenced to each layer's own
VBM so the three panels can be compared band-by-band.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .band_analysis import BandLayer, BandAnalysisError, gaps
from .scientific_bands import ScientificBandError, parse_band_table

LAYERS = ("ks", "exx", "gw")
LAYER_TITLES = {"ks": "KS (PBE)", "exx": "EXX", "gw": "G0W0"}

DEFAULT_FIGURE_NAME = "band_structure.png"
# The figure is judged over the frontier window, not the whole 44-state stack;
# deep semicore-like states would otherwise flatten the interesting region.
DEFAULT_WINDOW_EV = 8.0


def _load_for_plot(path: str | Path, quantity: str) -> BandLayer:
    """Load a band table for plotting, tolerating path revisits of a k node.

    A high-symmetry path can pass the same node twice (Gamma -> X ... Gamma ->
    L). That is a legitimate path point, so the strict duplicate-coordinate gate
    used by the numerical analysis must not block the figure.
    """
    try:
        table = parse_band_table(path, quantity=quantity, allow_kpoint_revisits=True)
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


def _cumulative_distance(kpoints: Sequence[Sequence[float]]) -> list[float]:
    """Return the path coordinate in units of the reciprocal-lattice vector."""
    coords = [0.0]
    for previous, current in zip(kpoints, kpoints[1:]):
        step = math.sqrt(sum((b - a) ** 2 for a, b in zip(previous, current)))
        coords.append(coords[-1] + step)
    return coords


def _layer_window(layer: BandLayer, occupied_bands: int, window_ev: float) -> tuple[float, float]:
    vbm = max(row[occupied_bands - 1] for row in layer.energies)
    cbm = min(row[occupied_bands] for row in layer.energies)
    return vbm - window_ev, cbm + window_ev


def render_band_figure(
    roots: Mapping[str, str | Path],
    output_path: str | Path,
    *,
    occupied_bands: int | None = None,
    title: str | None = None,
    window_ev: float = DEFAULT_WINDOW_EV,
    reference_gap_ev: float | None = None,
    kpath_labels: Sequence[tuple[float, str]] | None = None,
) -> dict[str, Any]:
    """Write a three-panel band figure and return a description of it.

    ``roots`` must carry the ``ks``, ``exx`` and ``gw`` band tables produced by
    the LibRPA band stage (``*_band_spin_1.dat``). ``kpath_labels`` optionally
    marks high-symmetry nodes as ``(path coordinate, label)``.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for layer in LAYERS:
        if layer not in roots:
            raise BandAnalysisError(f"band figure needs the {layer!r} band table")
    layers = {layer: _load_for_plot(roots[layer], layer) for layer in LAYERS}
    report = {layer: gaps(layers[layer], occupied_bands=occupied_bands) for layer in LAYERS}
    n_occupied = report["ks"]["occupied_bands"]
    for layer in LAYERS:
        if report[layer]["occupied_bands"] != n_occupied:
            raise BandAnalysisError("KS, EXX and GW tables disagree on the occupied-band count")

    coords = _cumulative_distance(layers["ks"].kpoints)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    figure, axes = plt.subplots(1, 3, figsize=(13.5, 5.2), sharey=True)
    low, high = _layer_window(layers["ks"], n_occupied, window_ev)
    for axis, layer_name in zip(axes, LAYERS):
        layer = layers[layer_name]
        vbm = report[layer_name]["vbm_ev"]
        for band in range(layer.nbands):
            energies = [row[band] - vbm for row in layer.energies]
            axis.plot(coords, energies, color="#1f4e79" if band < n_occupied else "#a33a3a", lw=1.0)
        axis.axhline(0.0, color="#666666", lw=0.8, ls="--")
        axis.set_title(
            f"{LAYER_TITLES[layer_name]}\n"
            f"gap {report[layer_name]['indirect_gap_ev']:.3f} eV "
            f"(direct {report[layer_name]['direct_gap_ev']:.3f})",
            fontsize=10,
        )
        axis.set_xlim(coords[0], coords[-1])
        axis.set_ylim(low - report["ks"]["vbm_ev"], high - report["ks"]["vbm_ev"])
        axis.grid(alpha=0.25, lw=0.5)
        if kpath_labels:
            for coordinate, label in kpath_labels:
                axis.axvline(coordinate, color="#999999", lw=0.6)
                axis.text(coordinate, axis.get_ylim()[1], label, ha="center", va="bottom", fontsize=8)
    axes[0].set_ylabel("E - E_VBM (eV)")
    for axis in axes:
        axis.set_xlabel("k path")
    heading = title or "Band structure: KS vs EXX vs G0W0"
    if reference_gap_ev is not None:
        heading += (
            f"\nGW gap {report['gw']['indirect_gap_ev']:.3f} eV "
            f"vs reference {reference_gap_ev:.3f} eV (advisory)"
        )
    figure.suptitle(heading, fontsize=11)
    figure.tight_layout()
    figure.savefig(target, dpi=160)
    plt.close(figure)

    return {
        "path": str(target),
        "layers": list(LAYERS),
        "occupied_bands": n_occupied,
        "gaps_ev": {layer: report[layer]["indirect_gap_ev"] for layer in LAYERS},
        "direct_gaps_ev": {layer: report[layer]["direct_gap_ev"] for layer in LAYERS},
        "window_ev": window_ev,
        "reference_gap_ev": reference_gap_ev,
    }
