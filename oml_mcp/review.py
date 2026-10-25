"""Settings review: show every critical production value and flag deviations.

The 0.1 shrink incident was not a policy gap but a settings gap: a replay
value silently became the production value and the run was wasted. This module
turns the effective definition into a review card. Deviations from the
production defaults are visible before submission; a run with deviations needs
an explicit acknowledgement.
"""

from __future__ import annotations

from typing import Any, Mapping


PRODUCTION_DEFAULTS: dict[str, Any] = {
    "nfreq": 16,
    "n_params_anacon": -1,
    "use_qpe_adaptive_damp": True,
    "libri_exx_threshold_V": 1e-2,
    "shrink_abfs_pca_thr": 1e-4,
    "scf_kgrid": [8, 8, 8],
    "use_fullcoul_exx": True,
}


def _note(key: str, value: Any, default: Any) -> str:
    if key == "nfreq" and isinstance(value, (int, float)) and isinstance(default, (int, float)) and value > default:
        return f"nfreq={value} costs about {value / default:.2f}x the default response work"
    if key == "n_params_anacon" and isinstance(value, (int, float)) and value != -1:
        return "a fixed Pade order differs from -1 (all nfreq points); the BN 24-point reference pinned 6"
    if key == "use_qpe_adaptive_damp" and value is False:
        return "adaptive QPE damping is off; the default keeps it on for stability"
    if key == "libri_exx_threshold_V" and isinstance(value, (int, float)) and value > default:
        return "a looser Coulomb screening threshold increases the LibRI error"
    if key == "shrink_abfs_pca_thr" and isinstance(value, (int, float)) and value > default:
        return "a looser shrink threshold keeps fewer auxiliary functions and can bias EXX/GW"
    if key == "scf_kgrid" and isinstance(value, (list, tuple)) and list(value) != list(default):
        return "the k grid differs from the standard; a ladder step must be declared"
    if key == "use_fullcoul_exx" and value is False:
        return "cut-Coulomb EXX is a different physical definition"
    return ""


def settings_review(
    definition: Mapping[str, Any],
    *,
    provenance: Mapping[str, Any] | None = None,
    policy_mode: str = "production",
) -> dict[str, Any]:
    """Return the review card for the critical production settings."""
    if policy_mode != "production":
        return {"applicable": False, "rows": [], "deviations": [], "needs_review": False}
    rows = []
    for key, default in PRODUCTION_DEFAULTS.items():
        present = key in definition
        value = definition.get(key)
        if not present:
            status = "missing"
        elif value == default:
            status = "default"
        else:
            status = "deviation"
        rows.append(
            {
                "key": key,
                "value": value,
                "default": default,
                "status": status,
                "note": _note(key, value, default),
                "source": list((provenance or {}).get(key, [])),
            }
        )
    deviations = [row for row in rows if row["status"] == "deviation"]
    return {
        "applicable": True,
        "rows": rows,
        "deviations": deviations,
        "needs_review": bool(deviations),
    }
