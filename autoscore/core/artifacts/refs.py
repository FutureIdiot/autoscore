"""Artifact reference model used by local and remote task payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any


def _is_absolute_path(path: str) -> bool:
    return PureWindowsPath(path).is_absolute() or PurePosixPath(path).is_absolute()


@dataclass(slots=True)
class ArtifactRef:
    """Portable reference to a pipeline artifact.

    `relative_path` is project-relative for local mode. `uri` is available for
    remote transport. At least one of them must be present.
    """

    artifact_id: str
    kind: str
    relative_path: str | None = None
    uri: str | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise ValueError("artifact_id is required")
        if not self.kind:
            raise ValueError("kind is required")
        if not self.relative_path and not self.uri:
            raise ValueError("relative_path or uri is required")
        if self.relative_path and _is_absolute_path(self.relative_path):
            raise ValueError("relative_path must not be absolute")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactRef":
        return cls(
            artifact_id=data["artifactId"],
            kind=data["kind"],
            relative_path=data.get("relativePath"),
            uri=data.get("uri"),
            sha256=data.get("sha256"),
            size_bytes=data.get("sizeBytes"),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "kind": self.kind,
            "relativePath": self.relative_path,
            "uri": self.uri,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
            "metadata": self.metadata,
        }

