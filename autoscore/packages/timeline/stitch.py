"""Stitch phrase-level aligned fragments into a song timeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autoscore.packages.timeline.align import AlignedFragment, PhraseAlignment
from autoscore.packages.timeline.phrases import PhraseSlice


@dataclass(slots=True)
class StitchedTimeline:
    """Song-level timeline assembled from aligned phrase fragments."""

    phrases: list[PhraseSlice]
    notes: list[AlignedFragment] = field(default_factory=list)
    lyrics: list[AlignedFragment] = field(default_factory=list)
    alignments: dict[str, PhraseAlignment] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phrases": [phrase.to_dict() for phrase in self.phrases],
            "notes": [note.to_dict() for note in self.notes],
            "lyrics": [lyric.to_dict() for lyric in self.lyrics],
            "phraseAlignments": {
                phrase_id: alignment.to_dict()
                for phrase_id, alignment in sorted(self.alignments.items())
            },
            "warnings": self.warnings,
        }


def stitch_fragments(
    phrases: list[PhraseSlice],
    *,
    notes: list[AlignedFragment] | None = None,
    lyrics: list[AlignedFragment] | None = None,
    alignments: dict[str, PhraseAlignment] | None = None,
) -> StitchedTimeline:
    """Merge phrase-level fragments and report suspicious phrase ordering."""

    sorted_phrases = sorted(phrases, key=lambda phrase: (phrase.index, phrase.phrase_start_ms))
    warnings = _phrase_boundary_warnings(sorted_phrases)
    known_phrase_ids = {phrase.phrase_id for phrase in sorted_phrases}

    stitched_notes = _sorted_fragments(notes or [], known_phrase_ids, "note", warnings)
    stitched_lyrics = _sorted_fragments(lyrics or [], known_phrase_ids, "lyric", warnings)

    return StitchedTimeline(
        phrases=sorted_phrases,
        notes=stitched_notes,
        lyrics=stitched_lyrics,
        alignments=alignments or {},
        warnings=warnings,
    )


def _phrase_boundary_warnings(phrases: list[PhraseSlice]) -> list[str]:
    warnings: list[str] = []
    previous: PhraseSlice | None = None
    for phrase in phrases:
        if previous and phrase.phrase_start_ms < previous.phrase_end_ms:
            warnings.append(
                f"phrase {phrase.phrase_id} starts before previous phrase {previous.phrase_id} ends"
            )
        previous = phrase
    return warnings


def _sorted_fragments(
    fragments: list[AlignedFragment],
    known_phrase_ids: set[str],
    label: str,
    warnings: list[str],
) -> list[AlignedFragment]:
    for fragment in fragments:
        if fragment.phrase_id not in known_phrase_ids:
            warnings.append(f"{label} {fragment.fragment_id} references unknown phrase {fragment.phrase_id}")
    return sorted(fragments, key=lambda fragment: (fragment.global_start_ms, fragment.global_end_ms, fragment.fragment_id))
