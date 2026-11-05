"""Audit a LibRPA ``librpa.in`` before staging or submitting it.

LibRPA silently ignores keys it does not recognise. That turns two common
mistakes into wrong physics instead of an error:

* rebuilding the input from the driver parameter dump uses the dump name
  ``cs_R_threshold`` while the input key is ``cs_threshold``; the line is
  dropped and ``cs_threshold`` falls back to its 1e-6 default;
* reusing a strict-2D input for a 3D system keeps
  ``option_dielect_func = 4`` and ``use_fullcoul_wc = t``.

This module rejects those inputs and checks that the 3D/2D dielectric switches
agree with the route. It is intentionally conservative: it fails on a
dump-shaped file, on duplicate keys, on a missing required threshold, and on a
2D/3D switch mismatch; it does not try to whitelist every valid LibRPA key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Names that appear in the LibRPA driver parameter dump but are not input
# keys. cs_threshold is the input key (driver.cpp prints cs_R_threshold).
DUMP_ONLY_KEYS = frozenset({"cs_R_threshold", "regulation"})
DUMP_MARKERS = (
    "begin driver parameters",
    "begin control parameters",
    "end control parameters",
)


@dataclass(frozen=True)
class Finding:
    gate_id: str
    status: str
    message: str
    repair: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "message": self.message,
            "repair": self.repair,
        }


@dataclass(frozen=True)
class Report:
    path: str
    keys: dict[str, str]
    duplicates: tuple[str, ...]
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        return all(finding.status != "FAIL" for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "keys": dict(sorted(self.keys.items())),
            "duplicates": list(self.duplicates),
            "findings": [finding.to_dict() for finding in self.findings],
            "ok": self.ok,
        }


def parse_librpa_in(path: str | Path) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    """Return ``(key -> value, duplicate keys, raw lines)``."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    values: dict[str, str] = {}
    duplicates: list[str] = []
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name, separator, value = stripped.partition("=")
        if not separator:
            continue
        key = name.strip()
        token = value.split("#", 1)[0].strip()
        if key in values:
            duplicates.append(key)
            continue
        values[key] = token
    return values, tuple(dict.fromkeys(duplicates)), tuple(lines)


def _as_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    token = value.strip().lower()
    if token in {"t", "true", ".true.", "1", "on", "yes"}:
        return True
    if token in {"f", "false", ".false.", "0", "off", "no"}:
        return False
    return None


def _as_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _dielect_finding(dimension: str, keys: dict[str, str]) -> Finding | None:
    dielect = _as_int(keys.get("option_dielect_func"))
    fullcoul = _as_bool(keys.get("use_fullcoul_wc"))
    if dimension == "3d":
        if dielect == 4:
            return Finding(
                "librpa.input.dielect",
                "FAIL",
                "option_dielect_func = 4 is the strict-2D dielectric path on a 3D run",
                "use option_dielect_func = 3 for the 3D route",
            )
        if fullcoul is True:
            return Finding(
                "librpa.input.dielect",
                "FAIL",
                "use_fullcoul_wc = t on a 3D run makes Wc use the untruncated Coulomb",
                "use use_fullcoul_wc = f for the 3D route",
            )
        return None
    if dimension == "2d":
        problems = []
        if dielect != 4:
            problems.append(f"option_dielect_func={keys.get('option_dielect_func')!r} expected 4")
        if fullcoul is not True:
            problems.append(f"use_fullcoul_wc={keys.get('use_fullcoul_wc')!r} expected t")
        if _as_bool(keys.get("use_2d_dielectric")) is not True:
            problems.append("use_2d_dielectric must be t")
        if (keys.get("rpa_headwing_mode") or "").strip().lower() != "qavg":
            problems.append(f"rpa_headwing_mode={keys.get('rpa_headwing_mode')!r} expected qavg")
        if problems:
            return Finding(
                "librpa.input.dielect",
                "FAIL",
                "librpa.in does not match the strict-2D dielectric contract: "
                + "; ".join(problems),
                "use the strict-2D input (option_dielect_func=4, use_fullcoul_wc=t, "
                "use_2d_dielectric=t, rpa_headwing_mode=qavg)",
            )
        return None
    return Finding(
        "librpa.input.dielect",
        "FAIL",
        f"unknown dimension {dimension!r}; use 3d or 2d",
        "pass --dimension 3d/2d",
    )


def audit_librpa_in(
    path: str | Path,
    *,
    dimension: str,
    require_cs_threshold: bool = False,
    control_in: str | Path | None = None,
) -> Report:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        finding = Finding(
            "librpa.input.parse",
            "FAIL",
            f"librpa.in does not exist: {file_path}",
            "stage the original LibRPA input; do not rebuild it from the parameter dump",
        )
        return Report(str(file_path), {}, (), (finding,))
    keys, duplicates, lines = parse_librpa_in(file_path)
    findings: list[Finding] = []

    lowered = "\n".join(line.strip().lower() for line in lines)
    if any(marker in lowered for marker in DUMP_MARKERS):
        findings.append(
            Finding(
                "librpa.input.dump_shape",
                "FAIL",
                "the file contains a LibRPA driver parameter dump header",
                "use the original librpa.in; do not rebuild it from the dump",
            )
        )
    aliases = sorted(set(keys) & DUMP_ONLY_KEYS)
    if aliases:
        findings.append(
            Finding(
                "librpa.input.dump_alias",
                "FAIL",
                f"dump-only key(s) present: {aliases}; LibRPA ignores them, so the "
                "intended value silently falls back to the default",
                "replace cs_R_threshold with cs_threshold; keep the original input file",
            )
        )
    if duplicates:
        findings.append(
            Finding(
                "librpa.input.duplicates",
                "FAIL",
                f"duplicate keys: {list(duplicates)}",
                "keep one definition per key; the parser keeps the first one",
            )
        )
    if not keys:
        findings.append(
            Finding(
                "librpa.input.parse",
                "FAIL",
                "no `key = value` entries were found",
                "use a LibRPA input file, not a log or dump",
            )
        )

    dielect = _dielect_finding(dimension, keys)
    if dielect is not None:
        findings.append(dielect)

    if require_cs_threshold and "cs_threshold" not in keys:
        findings.append(
            Finding(
                "librpa.input.cs_threshold",
                "FAIL",
                "cs_threshold is absent; LibRPA will silently use its 1e-6 default, "
                "which filters RI coefficients that the reference keeps",
                "write cs_threshold explicitly (the production 3D reference uses 0)",
            )
        )
    penalty = keys.get("regularization")
    if penalty is not None:
        try:
            penalty_value = float(penalty)
        except ValueError:
            findings.append(
                Finding(
                    "librpa.input.penalty",
                    "FAIL",
                    f"regularization={penalty!r} is not a number",
                    "write the Tikhonov coefficient as a positive float (production 1e-12)",
                )
            )
        else:
            if penalty_value < 0:
                findings.append(
                    Finding(
                        "librpa.input.penalty",
                        "FAIL",
                        f"regularization={penalty_value} is negative",
                        "use a non-negative Tikhonov coefficient (production 1e-12)",
                    )
                )
            elif penalty_value != 1e-12:
                findings.append(
                    Finding(
                        "librpa.input.penalty",
                        "WARN",
                        f"regularization={penalty_value} differs from the production 1e-12",
                        "use 1e-12 unless a paired run shows that another value is needed",
                    )
                )
    nfreq = _as_int(keys.get("nfreq"))
    if nfreq is not None and not 1 <= nfreq <= 128:
        findings.append(
            Finding(
                "librpa.input.nfreq",
                "FAIL",
                f"nfreq={nfreq} is outside 1..128",
                "use a physically meaningful frequency count",
            )
        )

    if control_in is not None:
        control_path = Path(control_in).expanduser().resolve()
        if control_path.is_file():
            points = None
            for line in control_path.read_text(encoding="utf-8", errors="replace").splitlines():
                fields = line.split()
                if fields[:1] == ["frequency_points"] and len(fields) >= 2:
                    points = _as_int(fields[1])
            if points is not None and nfreq is not None and points != nfreq:
                findings.append(
                    Finding(
                        "librpa.input.frequency_pair",
                        "FAIL",
                        f"control.in frequency_points={points} but librpa.in nfreq={nfreq}",
                        "the FHI-aims Matsubara grid and the LibRPA frequency count must match",
                    )
                )

    if not findings:
        findings.append(
            Finding("librpa.input", "PASS", "librpa.in passes the input contract")
        )
    return Report(str(file_path), keys, duplicates, tuple(findings))


def check_regularization_echo(
    librpa_path: str | Path,
    log_paths: tuple[str | Path, ...],
) -> Finding | None:
    """Require the LibRPA driver dump to echo the declared regularization.

    LibRPA ignores unknown input keys. If the build does not know
    ``regularization``, the run silently uses 0 and nothing in the output looks
    wrong. The driver parameter dump is written by the build itself, so the
    declared value must appear there.
    """
    try:
        keys, _, _ = parse_librpa_in(librpa_path)
    except OSError:
        return None
    if "regularization" not in keys:
        return None
    try:
        target = float(keys["regularization"])
    except ValueError:
        return None
    pattern = re.compile(
        r"(?i)\b(regularization|regulation)\s*=\s*([0-9eE+.+-]+)"
    )
    seen: list[float] = []
    dump_seen = False
    for log in log_paths:
        try:
            text = Path(log).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "Begin driver parameters" in text:
            dump_seen = True
        for match in pattern.finditer(text):
            try:
                seen.append(float(match.group(2)))
            except ValueError:
                continue
    if seen:
        tolerance = max(1e-30, abs(target) * 1e-12)
        mismatched = [value for value in seen if abs(value - target) > tolerance]
        if mismatched:
            return Finding(
                "librpa.input.penalty_echo",
                "FAIL",
                f"the driver dump reports regularization={mismatched[0]!r} but the input declares {target!r}",
                "stage the input that matches the submitted run; do not mix librpa.in files",
            )
        return Finding(
            "librpa.input.penalty_echo",
            "PASS",
            f"the driver dump echoes regularization={target:g}",
        )
    if dump_seen:
        return Finding(
            "librpa.input.penalty_echo",
            "FAIL",
            "the driver parameter dump does not contain regularization; the build may ignore the key",
            "confirm the LibRPA build exposes the regularization input, or do not claim the penalty was applied",
        )
    return Finding(
        "librpa.input.penalty_echo",
        "WARN",
        "no LibRPA driver parameter dump was found to confirm the regularization",
        "keep the LibRPA rank-0 output in the run directory",
    )
