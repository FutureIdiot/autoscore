"""Phrase-level note and lyric alignment helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TimedFragment:
    """Slice-local fragment projected into unaligned global time."""

    fragment_id: str
    phrase_id: str
    local_start_ms: int
    local_end_ms: int
    unaligned_global_start_ms: int
    unaligned_global_end_ms: int
    source: str

    def __post_init__(self) -> None:
        if not self.fragment_id:
            raise ValueError("fragment_id is required")
        if not self.phrase_id:
            raise ValueError("phrase_id is required")
        if self.local_start_ms < 0:
            raise ValueError("local_start_ms must be non-negative")
        if self.local_end_ms <= self.local_start_ms:
            raise ValueError("local_end_ms must be greater than local_start_ms")
        if self.unaligned_global_end_ms <= self.unaligned_global_start_ms:
            raise ValueError("unaligned_global_end_ms must be greater than unaligned_global_start_ms")
        if not self.source:
            raise ValueError("source is required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimedFragment":
        return cls(
            fragment_id=data["id"],
            phrase_id=data["phraseId"],
            local_start_ms=int(data["localStartMs"]),
            local_end_ms=int(data["localEndMs"]),
            unaligned_global_start_ms=int(data["unalignedGlobalStartMs"]),
            unaligned_global_end_ms=int(data["unalignedGlobalEndMs"]),
            source=data["source"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.fragment_id,
            "phraseId": self.phrase_id,
            "localStartMs": self.local_start_ms,
            "localEndMs": self.local_end_ms,
            "unalignedGlobalStartMs": self.unaligned_global_start_ms,
            "unalignedGlobalEndMs": self.unaligned_global_end_ms,
            "source": self.source,
        }


@dataclass(slots=True)
class AlignedFragment(TimedFragment):
    """Fragment after phrase offset has been applied."""

    global_start_ms: int = 0
    global_end_ms: int = 0

    def __post_init__(self) -> None:
        TimedFragment.__post_init__(self)
        if self.global_end_ms <= self.global_start_ms:
            raise ValueError("global_end_ms must be greater than global_start_ms")

    @classmethod
    def from_fragment(cls, fragment: TimedFragment, *, phrase_offset_ms: int) -> "AlignedFragment":
        return cls(
            fragment_id=fragment.fragment_id,
            phrase_id=fragment.phrase_id,
            local_start_ms=fragment.local_start_ms,
            local_end_ms=fragment.local_end_ms,
            unaligned_global_start_ms=fragment.unaligned_global_start_ms,
            unaligned_global_end_ms=fragment.unaligned_global_end_ms,
            source=fragment.source,
            global_start_ms=fragment.unaligned_global_start_ms + phrase_offset_ms,
            global_end_ms=fragment.unaligned_global_end_ms + phrase_offset_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        data = TimedFragment.to_dict(self)
        data.update(
            {
                "globalStartMs": self.global_start_ms,
                "globalEndMs": self.global_end_ms,
            }
        )
        return data


@dataclass(slots=True)
class PhraseAlignment:
    """Phrase-level anchor correction."""

    target_anchor_ms: int
    detected_anchor_ms: int
    phrase_offset_ms: int | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.target_anchor_ms < 0:
            raise ValueError("target_anchor_ms must be non-negative")
        if self.detected_anchor_ms < 0:
            raise ValueError("detected_anchor_ms must be non-negative")
        if self.phrase_offset_ms is None:
            self.phrase_offset_ms = self.target_anchor_ms - self.detected_anchor_ms

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PhraseAlignment":
        return cls(
            target_anchor_ms=int(data["targetAnchorMs"]),
            detected_anchor_ms=int(data["detectedAnchorMs"]),
            phrase_offset_ms=data.get("phraseOffsetMs"),
            warnings=list(data.get("warnings", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetAnchorMs": self.target_anchor_ms,
            "detectedAnchorMs": self.detected_anchor_ms,
            "phraseOffsetMs": self.phrase_offset_ms,
            "warnings": self.warnings,
        }


def align_fragments(fragments: list[TimedFragment], phrase_alignment: PhraseAlignment) -> list[AlignedFragment]:
    """Apply phrase offset to note or lyric fragments."""

    if phrase_alignment.phrase_offset_ms is None:
        raise ValueError("phrase_offset_ms is required")
    return [
        AlignedFragment.from_fragment(fragment, phrase_offset_ms=phrase_alignment.phrase_offset_ms)
        for fragment in fragments
    ]
