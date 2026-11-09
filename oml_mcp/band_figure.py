"""Render the band figure with the LibRPA-database standard.

A gap number on its own cannot tell whether a band table is physical: it hides
a collapsed dispersion, a broken layer ordering, or a single absurd eigenvalue.
The band figure is the acceptance artifact for the periodic GW routes, and gap
agreement with a database record is advisory only.

OML used to draw its own three-panel matplotlib PNG. That made the loop's
acceptance artifact a different object from the figure a database record
carries, so the two could disagree about the same band table. The rendering
rules now come from ``AroundPeking/LibRPA-database`` (vendored in
``oml_mcp/band_frontier.py`` at commit ``8adb1dc``), which means:

* one white-background SVG per method (``ks_frontier.svg`` and friends);
* a frozen raw band selection (3 occupied + 4 empty by default), never "every
  band within N eV" - a window that moves with the data can hide a band;
* per-k energy-rank ordering inside each manifold, with the raw mapping kept;
* alignment to the sampled-path VBM of that frozen selection;
* SCF-mesh dots: only path samples whose fractional k sits on the
  self-consistent mesh carry that mesh's information, and only those get a
  filled dot;
* a JSON sidecar per figure with source SHA-256 values, the frozen window, the
  ordering map and the full audit, so a figure cannot be edited without the
  sidecar disagreeing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import band_frontier
from .band_analysis import BandAnalysisError

LAYERS = ("ks", "exx", "gw")
METHODS = {"ks": "KS", "exx": "EXX", "gw": "GW"}
LAYER_TITLES = {"ks": "KS (PBE)", "exx": "EXX", "gw": "G0W0"}

# The figure set is a directory: one SVG per method plus the audit sidecars.
DEFAULT_FIGURE_NAME = "band_figures"
SIDECAR_NAME = "band_frontier_metadata.json"
DEFAULT_OCCUPIED_WINDOW = 3
DEFAULT_EMPTY_WINDOW = 4


def _figure_paths(output_dir: Path) -> dict[str, Path]:
    return {layer: output_dir / f"{layer}_frontier.svg" for layer in LAYERS}


def render_band_figure(
    roots: Mapping[str, str | Path],
    output_path: str | Path,
    *,
    occupied_bands: int | None = None,
    title: str | None = None,
    scf_kpt: str | Path | None = None,
    kpath_labels: Sequence[dict] | None = None,
    occupied_window: int = DEFAULT_OCCUPIED_WINDOW,
    empty_window: int = DEFAULT_EMPTY_WINDOW,
    known_pathological: Mapping[str, bool] | None = None,
) -> dict[str, Any]:
    """Write the database-standard figure set and return a description of it.

    ``roots`` must carry the ``ks``, ``exx`` and ``gw`` band tables produced by
    the LibRPA band stage (``*_band_spin_1.dat``). ``scf_kpt`` is the KPT file
    of the self-consistent run: when given, path samples that coincide with
    that mesh are marked with filled dots. ``kpath_labels`` optionally marks
    high-symmetry nodes as ``{"x": <path coordinate>, "label": <name>}``.

    The returned report keeps the keys the loop already consumes (``path``,
    ``layers``, ``occupied_bands``, ``gaps_ev``) and adds the per-method audit
    verdict from the database analysis, so a diagnostic figure can never be
    mistaken for an accepted one.
    """
    target = Path(output_path)
    # Accept a legacy ``*.png`` argument by writing the figure set next to it;
    # the artifact is now a directory and the caller must not have to guess.
    if target.suffix.lower() in {".png", ".svg", ".pdf"}:
        target = target.parent / DEFAULT_FIGURE_NAME
    target.mkdir(parents=True, exist_ok=True)

    for layer in LAYERS:
        if layer not in roots:
            raise BandAnalysisError(f"band figure needs the {layer!r} band table")

    grid = None
    if scf_kpt is not None:
        kpt_path = Path(scf_kpt)
        if kpt_path.is_file():
            try:
                grid = band_frontier.parse_scf_grid(kpt_path)
            except ValueError as exc:
                raise BandAnalysisError(f"cannot read the SCF grid {kpt_path}: {exc}") from exc

    figures = _figure_paths(target)
    methods: dict[str, Any] = {}
    gaps: dict[str, float | None] = {}
    diagnostics: dict[str, list[str]] = {}
    grid_rows: dict[str, list[int]] = {}
    occupied_seen: int | None = None

    for layer in LAYERS:
        method = METHODS[layer]
        table_path = Path(roots[layer])
        try:
            table = band_frontier.parse_abacus_band_table(table_path)
        except ValueError as exc:
            raise BandAnalysisError(f"{table_path}: {exc}") from exc
        rows = band_frontier.grid_path_kpoints(table, grid) if grid is not None else []
        try:
            analysis = band_frontier.analyze_frontier(
                table,
                occupied_count=occupied_bands,
                occupied_window=occupied_window,
                empty_window=empty_window,
                known_pathological=bool((known_pathological or {}).get(layer)),
                allow_nonfinite_display=True,
            )
        except ValueError as exc:
            raise BandAnalysisError(f"{method} frontier analysis refused: {exc}") from exc

        boundary = analysis["raw_audit"]["occupied_band_count"]
        if occupied_seen is None:
            occupied_seen = boundary
        elif occupied_seen != boundary:
            raise BandAnalysisError(
                f"{method} reports {boundary} occupied bands, KS reported {occupied_seen}"
            )

        svg = band_frontier.render_frontier_svg(
            table,
            analysis,
            list(kpath_labels or ()),
            title or "Band structure",
            method,
            rows,
        )
        figure_path = figures[layer]
        if not figure_path.exists() or figure_path.read_text(encoding="utf-8") != svg:
            figure_path.write_text(svg, encoding="utf-8")

        sidecar = band_frontier.write_sidecar(
            figure_path,
            calculation_id=title or target.name,
            input_sha256=_sha256(table_path),
            table_path=table_path,
            labels=list(kpath_labels or ()),
        )
        sidecar["analysis"] = analysis
        sidecar["scf_grid"] = grid
        sidecar["scf_grid_rows"] = rows
        figures[layer].with_suffix(".json").write_text(
            json.dumps(sidecar, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )

        methods[method] = {
            "figure": str(figure_path),
            "sidecar": str(figure_path.with_suffix(".json")),
            "status": analysis["status"],
            "gap_status": analysis["gap_status"],
            "sampled_path_gap_ev": analysis["sampled_path_gap_ev"],
            "selected_window_path_gap_ev": analysis["selected_window_path_gap_ev"],
            "occupied_band_count": boundary,
            "raw_selected_occupied_bands": analysis["raw_selected_occupied_bands"],
            "raw_selected_empty_bands": analysis["raw_selected_empty_bands"],
            "y_limits_ev": analysis["y_limits_ev"],
            "scf_grid_rows": rows,
            "diagnostic_reasons": analysis["diagnostic_reasons"],
        }
        gaps[layer] = analysis["sampled_path_gap_ev"]
        if analysis["diagnostic_reasons"]:
            diagnostics[method] = list(analysis["diagnostic_reasons"])
        grid_rows[method] = rows

    metadata_path = target / SIDECAR_NAME
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "calculation_id": title or target.name,
                "standard": {
                    "source": "AroundPeking/LibRPA-database",
                    "file": "scripts/plot_bands.py",
                    "commit": band_frontier.UPSTREAM_COMMIT,
                    "vendored_as": "oml_mcp/band_frontier.py",
                },
                "occupied_bands": occupied_seen,
                "windows": {"occupied": occupied_window, "empty": empty_window},
                "scf_grid": grid,
                "methods": methods,
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "path": str(target),
        "figures": {layer: str(path) for layer, path in figures.items()},
        "metadata": str(metadata_path),
        "layers": list(LAYERS),
        "occupied_bands": occupied_seen,
        "gaps_ev": gaps,
        "methods": methods,
        "diagnostics": diagnostics,
        "scf_grid": grid,
        "windows": {"occupied": occupied_window, "empty": empty_window},
        "render_standard": "LibRPA-database scripts/plot_bands.py",
    }


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()
