"""Common warning and error record shapes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PROBLEM_SEVERITIES = {"warning", "error"}


@dataclass(slots=True)
class ProblemRecord:
    """Structured warning or error emitted by tasks and runtime layers."""

    severity: str
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.severity not in PROBLEM_SEVERITIES:
            raise ValueError(f"invalid problem severity: {self.severity}")
        if not self.code:
            raise ValueError("code is required")
        if not self.message:
            raise ValueError("message is required")

    @classmethod
    def warning(cls, code: str, message: str, *, details: dict[str, Any] | None = None) -> "ProblemRecord":
        return cls(severity="warning", code=code, message=message, details=details or {})

    @classmethod
    def error(cls, code: str, message: str, *, details: dict[str, Any] | None = None) -> "ProblemRecord":
        return cls(severity="error", code=code, message=message, details=details or {})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProblemRecord":
        return cls(
            severity=data["severity"],
            code=data["code"],
            message=data["message"],
            details=dict(data.get("details", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
