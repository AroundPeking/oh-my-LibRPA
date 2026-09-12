"""Fast full-pipeline ABACUS + LibRPA benchmark registry.

This is the "fast benchmark" the user asked for: it runs the WHOLE compute
pipeline (ABACUS SCF -> PyATB/NSCF -> preprocess -> LibRPA) but on small
systems that finish in seconds or minutes, exactly like the upstream LibRPA
``regression_tests`` suite. It is NOT a slow convergence ladder and NOT a
file-only diagnostic: every case is a real end-to-end calculation with a
frozen numerical reference.

Why small systems are enough
----------------------------
The benchmark's job is to detect *regressions in the workflow and its input
parameters*, not to establish converged physics. A 2x2x2-k BN cell exercises
every code path (reader-v1 handoff, head/wing, shrink, symmetry, EXX, GW
self-energy) that a converged cell does, but returns in seconds. That makes
the loop fast enough to iterate on.

Reference semantics
-------------------
Each case carries the validators copied from the upstream suite: a regex that
extracts a scalar (bandgap, correlation energy, a QP-energy sequence) plus an
absolute tolerance (upstream default ``1e-4``). A case PASSes only when every
validator is within tolerance against the frozen reference. A case with no
usable reference stays ``NOT_EVALUATED`` - it is never silently passed.

Upstream cases whose staged inputs use the legacy (pre reader-v1) handoff are
marked ``reference_status: "LEGACY_HANDOFF"`` so the registry is honest about
which cases can be replayed by the current reader-v1 pipeline.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable


FAST_CASE_SCHEMA = "oml.fast-case.v1"
FAST_SUITE_SCHEMA = "oml.fast-suite.v1"
PACKAGED_FAST_CASE_ROOT = Path(__file__).with_name("fast_cases")

CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")

# Stage sets. "full" is the whole controlled pipeline; "librpa_only" replays
# only the LibRPA stage against staged upstream inputs.
FULL_PIPELINE_STAGES = ("scf", "pyatb", "nscf", "preprocess", "librpa")
LIBRPA_ONLY_STAGES = ("librpa",)

DEFAULT_TOLERANCE = 1.0e-4


class FastCaseError(ValueError):
    """Raised when a fast-benchmark case or suite is malformed."""


@dataclass(frozen=True)
class CaseValidator:
    """One scalar reference check copied from the upstream suite."""

    name: str
    regex: str
    tolerance: float = DEFAULT_TOLERANCE
    file: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise FastCaseError("validator name must be a non-empty string")
        if not isinstance(self.regex, str) or not self.regex:
            raise FastCaseError("validator regex must be a non-empty string")
        try:
            compiled = re.compile(self.regex)
        except re.error as exc:
            raise FastCaseError(f"validator regex is invalid: {exc}") from exc
        if compiled.groups < 1:
            raise FastCaseError("validator regex must capture at least one value")
        if (
            isinstance(self.tolerance, bool)
            or not isinstance(self.tolerance, (int, float))
            or self.tolerance <= 0
        ):
            raise FastCaseError("validator tolerance must be a positive number")

    def extract(self, text: str) -> list[float]:
        """Return every captured value in file order."""
        values: list[float] = []
        pattern = re.compile(self.regex, re.MULTILINE)
        for match in pattern.finditer(text):
            raw = match.group(1)
            try:
                values.append(float(raw))
            except (TypeError, ValueError):
                continue
        return values

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(asdict(self))


@dataclass(frozen=True)
class FastCase:
    """A small, fast, end-to-end case with a frozen numerical reference."""

    case_id: str
    title: str
    system: str
    task: str
    system_type: str
    soc: bool
    nspin: int
    stages: tuple[str, ...]
    validators: tuple[CaseValidator, ...]
    output_files: tuple[str, ...]
    upstream_directory: str | None = None
    upstream_groups: tuple[str, ...] = ()
    reference_status: str = "REFERENCE_AVAILABLE"
    route: str = "periodic_3d_gw"
    use_symmetry: bool = False
    headwing: bool | None = None
    material_class: str | None = None
    estimated_seconds: int = 60
    note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or CASE_ID_PATTERN.fullmatch(self.case_id) is None:
            raise FastCaseError(f"invalid fast-case id: {self.case_id!r}")
        for label in ("title", "system", "task", "system_type"):
            if not isinstance(getattr(self, label), str) or not getattr(self, label):
                raise FastCaseError(f"fast-case {label} must be a non-empty string")
        if self.reference_status not in {
            "REFERENCE_AVAILABLE",
            "LEGACY_HANDOFF",
            "REFERENCE_PENDING",
        }:
            raise FastCaseError(
                "fast-case reference_status must be REFERENCE_AVAILABLE, "
                "LEGACY_HANDOFF, or REFERENCE_PENDING"
            )
        if (
            isinstance(self.estimated_seconds, bool)
            or not isinstance(self.estimated_seconds, int)
            or self.estimated_seconds <= 0
        ):
            raise FastCaseError("fast-case estimated_seconds must be a positive integer")
        for stage in self.stages:
            if stage not in FULL_PIPELINE_STAGES:
                raise FastCaseError(f"fast-case uses an unknown stage: {stage}")
        if not self.stages:
            raise FastCaseError("fast-case must declare at least one stage")

    @property
    def evaluable(self) -> bool:
        """Whether this case can produce a real numerical verdict."""
        return (
            self.reference_status == "REFERENCE_AVAILABLE"
            and bool(self.validators)
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["validators"] = [validator.to_dict() for validator in self.validators]
        data["stages"] = list(self.stages)
        data["output_files"] = list(self.output_files)
        data["upstream_groups"] = list(self.upstream_groups)
        data["evaluable"] = self.evaluable
        return json.loads(json.dumps(data, sort_keys=True))


def _case_from_json(value: dict[str, Any]) -> FastCase:
    if value.get("schema") != FAST_CASE_SCHEMA:
        raise FastCaseError(f"fast-case schema must be {FAST_CASE_SCHEMA}")
    validators = tuple(
        CaseValidator(
            name=item["name"],
            regex=item["regex"],
            tolerance=float(item.get("tolerance", DEFAULT_TOLERANCE)),
            file=item.get("file"),
        )
        for item in value.get("validators", [])
    )
    return FastCase(
        case_id=value["case_id"],
        title=value["title"],
        system=value["system"],
        task=value["task"],
        system_type=value["system_type"],
        soc=bool(value.get("soc", False)),
        nspin=int(value.get("nspin", 1)),
        stages=tuple(value.get("stages", FULL_PIPELINE_STAGES)),
        validators=validators,
        output_files=tuple(value.get("output_files", ())),
        upstream_directory=value.get("upstream_directory"),
        upstream_groups=tuple(value.get("upstream_groups", ())),
        reference_status=value.get("reference_status", "REFERENCE_AVAILABLE"),
        route=value.get("route", "periodic_3d_gw"),
        use_symmetry=bool(value.get("use_symmetry", False)),
        headwing=(None if value.get("headwing") is None else bool(value.get("headwing"))),
        material_class=value.get("material_class"),
        estimated_seconds=int(value.get("estimated_seconds", 60)),
        note=value.get("note"),
    )


def list_fast_cases() -> tuple[FastCase, ...]:
    """Return every packaged fast case in deterministic order."""
    cases: list[FastCase] = []
    for path in sorted(PACKAGED_FAST_CASE_ROOT.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FastCaseError(f"cannot read fast case {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise FastCaseError(f"fast-case root must be an object: {path}")
        cases.append(_case_from_json(value))
    return tuple(cases)


def load_fast_case(case_id: str) -> FastCase:
    """Load one fast case by id."""
    if not isinstance(case_id, str) or CASE_ID_PATTERN.fullmatch(case_id) is None:
        raise FastCaseError(f"invalid fast-case id: {case_id!r}")
    path = PACKAGED_FAST_CASE_ROOT / f"{case_id}.json"
    if not path.is_file():
        raise FastCaseError(f"fast case is not available: {case_id}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FastCaseError(f"cannot read fast case {path}: {exc}") from exc
    return _case_from_json(value)


def select_fast_cases(
    *,
    task: str | None = None,
    system_type: str | None = None,
    soc: bool | None = None,
    evaluable_only: bool = False,
    max_estimated_seconds: int | None = None,
) -> tuple[FastCase, ...]:
    """Filter the registry for a fast benchmark run.

    ``evaluable_only`` keeps only cases that can return a real numerical
    verdict, which is the right setting for a regression run.
    """
    selected = []
    for case in list_fast_cases():
        if task is not None and case.task != task:
            continue
        if system_type is not None and case.system_type != system_type:
            continue
        if soc is not None and case.soc != soc:
            continue
        if evaluable_only and not case.evaluable:
            continue
        if (
            max_estimated_seconds is not None
            and case.estimated_seconds > max_estimated_seconds
        ):
            continue
        selected.append(case)
    return tuple(selected)


def evaluate_case_against_reference(
    case: FastCase,
    reference: dict[str, str],
    observed: dict[str, str],
) -> dict[str, Any]:
    """Compare a produced case against its frozen reference.

    ``reference`` and ``observed`` map a validator's source file name to that
    file's text. A validator whose file is absent on either side cannot be
    evaluated, so it is reported as ``NOT_EVALUATED`` and the overall case
    verdict becomes ``NOT_EVALUATED`` - never a silent pass.
    """
    if not case.evaluable:
        return {
            "schema": "oml.fast-case-result.v1",
            "case_id": case.case_id,
            "status": "NOT_EVALUATED",
            "reason_code": f"CASE_{case.reference_status}",
            "validators": [],
        }

    reports: list[dict[str, Any]] = []
    accepted = True
    unevaluated = False
    for validator in case.validators:
        key = validator.file
        if key is None:
            keys = sorted(set(reference) & set(observed))
            if len(keys) != 1:
                reports.append(
                    {
                        "name": validator.name,
                        "status": "NOT_EVALUATED",
                        "reason": "validator does not name a file and the case is not single-file",
                    }
                )
                unevaluated = True
                continue
            key = keys[0]
        reference_text = reference.get(key)
        observed_text = observed.get(key)
        if reference_text is None or observed_text is None:
            reports.append(
                {
                    "name": validator.name,
                    "status": "NOT_EVALUATED",
                    "reason": f"missing file: {key}",
                }
            )
            unevaluated = True
            continue
        expected = validator.extract(reference_text)
        actual = validator.extract(observed_text)
        if not expected or not actual:
            reports.append(
                {
                    "name": validator.name,
                    "status": "NOT_EVALUATED",
                    "reason": "regex matched no value on one or both sides",
                    "file": key,
                }
            )
            unevaluated = True
            continue
        if len(expected) != len(actual):
            # A sequence of a different length means the definition changed
            # (state window, k set, or output format). Comparing only the
            # overlapping prefix would silently hide that, so this is a FAIL.
            reports.append(
                {
                    "name": validator.name,
                    "status": "FAIL",
                    "reason": "SEQUENCE_LENGTH_MISMATCH",
                    "file": key,
                    "reference_count": len(expected),
                    "observed_count": len(actual),
                    "reference_values": expected,
                    "observed_values": actual,
                }
            )
            accepted = False
            continue
        paired = list(zip(expected, actual))
        worst = max(abs(a - b) for a, b in paired)
        matches = worst <= validator.tolerance
        accepted = accepted and matches
        reports.append(
            {
                "name": validator.name,
                "status": "PASS" if matches else "FAIL",
                "file": key,
                "tolerance": validator.tolerance,
                "max_abs_diff": worst,
                "value_count": len(paired),
                "reference_values": expected,
                "observed_values": actual,
            }
        )

    if not accepted:
        status = "FAIL"
        reason = "REFERENCE_TOLERANCE_EXCEEDED"
    elif unevaluated:
        status = "NOT_EVALUATED"
        reason = "VALIDATOR_INCOMPLETE"
    else:
        status = "PASS"
        reason = "WITHIN_REFERENCE_TOLERANCE"
    return {
        "schema": "oml.fast-case-result.v1",
        "case_id": case.case_id,
        "route": case.route,
        "material_class": case.material_class,
        "status": status,
        "reason_code": reason,
        "promotion_eligibility": "ENABLED" if status == "PASS" else "BLOCKED",
        "validators": reports,
    }


def aggregate_fast_results(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-case results into a fast-suite verdict.

    The aggregate is FAIL if any case failed, NOT_EVALUATED if any case could
    not be evaluated, and PASS only when every case passed. This keeps the
    no-false-pass rule at suite level too.
    """
    results = tuple(results)
    statuses = [result.get("status") for result in results]
    if "FAIL" in statuses:
        status = "FAIL"
    elif not statuses:
        status = "NOT_EVALUATED"
    elif any(item != "PASS" for item in statuses):
        status = "NOT_EVALUATED"
    else:
        status = "PASS"
    return {
        "schema": "oml.fast-suite-result.v1",
        "status": status,
        "case_count": len(results),
        "passed_cases": [r["case_id"] for r in results if r.get("status") == "PASS"],
        "failed_cases": [r["case_id"] for r in results if r.get("status") == "FAIL"],
        "not_evaluated_cases": [
            r["case_id"] for r in results if r.get("status") == "NOT_EVALUATED"
        ],
        "cases": list(results),
    }
