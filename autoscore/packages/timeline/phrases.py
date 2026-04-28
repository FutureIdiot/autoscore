"""Phrase slice timeline models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autoscore.core.artifacts import ArtifactRef


@dataclass(slots=True)
class PhraseSlice:
    """A vocal phrase and its padded slice artifact."""

    phrase_id: str
    index: int
    phrase_start_ms: int
    phrase_end_ms: int
    slice_start_ms: int
    slice_end_ms: int
    audio_artifact: ArtifactRef | None = None

    def __post_init__(self) -> None:
        if not self.phrase_id:
            raise ValueError("phrase_id is required")
        if self.index < 0:
            raise ValueError("index must be non-negative")
        if self.phrase_start_ms < 0:
            raise ValueError("phrase_start_ms must be non-negative")
        if self.phrase_end_ms <= self.phrase_start_ms:
            raise ValueError("phrase_end_ms must be greater than phrase_start_ms")
        if self.slice_start_ms < 0:
            raise ValueError("slice_start_ms must be non-negative")
        if self.slice_end_ms <= self.slice_start_ms:
            raise ValueError("slice_end_ms must be greater than slice_start_ms")
        if self.slice_start_ms > self.phrase_start_ms:
            raise ValueError("slice_start_ms must be at or before phrase_start_ms")
        if self.slice_end_ms < self.phrase_end_ms:
            raise ValueError("slice_end_ms must be at or after phrase_end_ms")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhraseSlice":
        artifact_data = data.get("audioArtifact")
        return cls(
            phrase_id=data["id"],
            index=int(data["index"]),
            phrase_start_ms=int(data["phraseStartMs"]),
            phrase_end_ms=int(data["phraseEndMs"]),
            slice_start_ms=int(data["sliceStartMs"]),
            slice_end_ms=int(data["sliceEndMs"]),
            audio_artifact=ArtifactRef.from_dict(artifact_data) if artifact_data else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.phrase_id,
            "index": self.index,
            "phraseStartMs": self.phrase_start_ms,
            "phraseEndMs": self.phrase_end_ms,
            "sliceStartMs": self.slice_start_ms,
            "sliceEndMs": self.slice_end_ms,
            "audioArtifact": self.audio_artifact.to_dict() if self.audio_artifact else None,
        }
