from __future__ import annotations

from typing import Any, Iterable


class OMLError(RuntimeError):
    """Stable structured error returned by the OML control plane."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        evidence: Iterable[str] = (),
        recovery: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.evidence = tuple(evidence)
        self.recovery = recovery
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "evidence": list(self.evidence),
                "recovery": self.recovery,
                "details": self.details,
            },
        }
