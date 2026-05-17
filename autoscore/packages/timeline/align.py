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
            warnings=list(data.get("warnings") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "targetAnchorMs": self.target_anchor_ms,
            "detectedAnchorMs": self.detected_anchor_ms,
            "phraseOffsetMs": self.phrase_offset_ms,
            "warnings": self.warnings,
        }


@dataclass(slots=True)
class LyricNoteAlignment:
    """Alignment from one lyric timestamp fragment to one or more note fragments."""

    alignment_id: str
    lyric_id: str
    note_ids: list[str]
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.alignment_id:
            raise ValueError("alignment_id is required")
        if not self.lyric_id:
            raise ValueError("lyric_id is required")
        if not self.note_ids:
            raise ValueError("note_ids are required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LyricNoteAlignment":
        return cls(
            alignment_id=data["id"],
            lyric_id=data["lyricId"],
            note_ids=list(data["noteIds"]),
            confidence=data.get("confidence"),
            warnings=list(data.get("warnings") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.alignment_id,
            "lyricId": self.lyric_id,
            "noteIds": self.note_ids,
            "confidence": self.confidence,
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


def match_lyrics_to_notes(
    lyrics: list[AlignedFragment],
    notes: list[AlignedFragment],
    *,
    max_nearest_distance_ms: int = 250,
) -> list[LyricNoteAlignment]:
    """Create initial lyric-to-note alignments from aligned fragment timing.

    The first rule is overlap-based and supports one lyric mapped to multiple
    notes. If a lyric has no overlapping note in the same phrase, the nearest
    note center is selected and the alignment is marked with a warning.
    """

    if max_nearest_distance_ms < 0:
        raise ValueError("max_nearest_distance_ms must be non-negative")

    notes_by_phrase: dict[str, list[AlignedFragment]] = {}
    for note in notes:
        notes_by_phrase.setdefault(note.phrase_id, []).append(note)
    for phrase_notes in notes_by_phrase.values():
        phrase_notes.sort(key=lambda note: (note.global_start_ms, note.global_end_ms, note.fragment_id))

    alignments: list[LyricNoteAlignment] = []
    for index, lyric in enumerate(sorted(lyrics, key=lambda item: (item.global_start_ms, item.global_end_ms, item.fragment_id)), start=1):
        phrase_notes = notes_by_phrase.get(lyric.phrase_id, [])
        warnings: list[str] = []
        matched_notes = [note for note in phrase_notes if _overlap_ms(lyric, note) > 0]

        if not matched_notes and phrase_notes:
            nearest_note, distance = _nearest_note(lyric, phrase_notes)
            if distance <= max_nearest_distance_ms:
                matched_notes = [nearest_note]
                warnings.append(f"lyric matched to nearest note at distance {distance}ms")
            else:
                warnings.append(f"nearest note is {distance}ms away, above threshold {max_nearest_distance_ms}ms")

        if not matched_notes:
            warnings.append("no note match found")
            continue

        alignments.append(
            LyricNoteAlignment(
                alignment_id=f"align_{index:03d}",
                lyric_id=lyric.fragment_id,
                note_ids=[note.fragment_id for note in matched_notes],
                warnings=warnings,
            )
        )

    return alignments


def _overlap_ms(left: AlignedFragment, right: AlignedFragment) -> int:
    return max(0, min(left.global_end_ms, right.global_end_ms) - max(left.global_start_ms, right.global_start_ms))


def _nearest_note(lyric: AlignedFragment, notes: list[AlignedFragment]) -> tuple[AlignedFragment, int]:
    lyric_center = (lyric.global_start_ms + lyric.global_end_ms) // 2
    nearest = min(notes, key=lambda note: abs(((note.global_start_ms + note.global_end_ms) // 2) - lyric_center))
    distance = abs(((nearest.global_start_ms + nearest.global_end_ms) // 2) - lyric_center)
    return nearest, distance
