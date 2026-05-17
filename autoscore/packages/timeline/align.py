"""Phrase-level note and lyric alignment helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.core.problems import ProblemRecord


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
    extras: dict[str, Any] = field(default_factory=dict)

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
            extras=_fragment_extras(data),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.fragment_id,
            "phraseId": self.phrase_id,
            "localStartMs": self.local_start_ms,
            "localEndMs": self.local_end_ms,
            "unalignedGlobalStartMs": self.unaligned_global_start_ms,
            "unalignedGlobalEndMs": self.unaligned_global_end_ms,
            "source": self.source,
        }
        data.update(self.extras)
        return data


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
            extras=dict(fragment.extras),
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlignedFragment":
        return cls(
            fragment_id=data["id"],
            phrase_id=data["phraseId"],
            local_start_ms=int(data["localStartMs"]),
            local_end_ms=int(data["localEndMs"]),
            unaligned_global_start_ms=int(data["unalignedGlobalStartMs"]),
            unaligned_global_end_ms=int(data["unalignedGlobalEndMs"]),
            source=data["source"],
            extras=_fragment_extras(data),
            global_start_ms=int(data["globalStartMs"]),
            global_end_ms=int(data["globalEndMs"]),
        )


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


_FRAGMENT_CONTRACT_KEYS = {
    "id",
    "phraseId",
    "localStartMs",
    "localEndMs",
    "unalignedGlobalStartMs",
    "unalignedGlobalEndMs",
    "globalStartMs",
    "globalEndMs",
    "source",
}


def _fragment_extras(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key not in _FRAGMENT_CONTRACT_KEYS}


def run_mock_phrase_aligner(envelope: Any, store: LocalArtifactStore) -> Any:
    """Align phrase-local note and lyric fragments with one phrase anchor each."""

    from autoscore.core.tasks import ExecutionInfo, TaskResult

    phrase_artifact = _find_required_input_artifact(envelope, "artifact_phrase_timeline_json")
    notes_artifact = _find_required_input_artifact(envelope, "artifact_midi_notes_json")
    lyrics_artifact = _find_required_input_artifact(envelope, "artifact_lyric_fragments_json")

    phrase_timeline = json.loads(store.materialize(phrase_artifact).read_text(encoding="utf-8"))
    note_data = json.loads(store.materialize(notes_artifact).read_text(encoding="utf-8"))
    lyric_data = json.loads(store.materialize(lyrics_artifact).read_text(encoding="utf-8"))

    notes = [TimedFragment.from_dict(note) for note in note_data.get("notes", [])]
    lyrics = [TimedFragment.from_dict(lyric) for lyric in lyric_data.get("lyrics", [])]
    phrase_alignments = _mock_phrase_alignments(
        phrase_timeline.get("phrases", []),
        notes=notes,
        lyrics=lyrics,
    )

    aligned_notes: list[AlignedFragment] = []
    aligned_lyrics: list[AlignedFragment] = []
    for phrase_id, alignment in phrase_alignments.items():
        aligned_notes.extend(align_fragments(_fragments_for_phrase(notes, phrase_id), alignment))
        aligned_lyrics.extend(align_fragments(_fragments_for_phrase(lyrics, phrase_id), alignment))

    lyric_note_alignments = match_lyrics_to_notes(aligned_lyrics, aligned_notes)

    payload = {
        "source": "mock-phrase-alignment",
        "phraseTimelineArtifact": phrase_artifact.to_dict(),
        "midiNotesArtifact": notes_artifact.to_dict(),
        "lyricFragmentsArtifact": lyrics_artifact.to_dict(),
        "notes": [note.to_dict() for note in sorted(aligned_notes, key=_fragment_sort_key)],
        "lyrics": [lyric.to_dict() for lyric in sorted(aligned_lyrics, key=_fragment_sort_key)],
        "phraseAlignments": {
            phrase_id: alignment.to_dict()
            for phrase_id, alignment in sorted(phrase_alignments.items())
        },
        "lyricNoteAlignments": [alignment.to_dict() for alignment in lyric_note_alignments],
    }
    target = store.resolve_relative_path("timeline/aligned.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    aligned_artifact = store.create_ref(
        artifact_id="artifact_aligned_timeline_json",
        kind="application/json",
        relative_path="timeline/aligned.json",
        metadata={
            "mock": True,
            "source": "mock-phrase-alignment",
            "phraseTimelineArtifactId": phrase_artifact.artifact_id,
            "midiNotesArtifactId": notes_artifact.artifact_id,
            "lyricFragmentsArtifactId": lyrics_artifact.artifact_id,
        },
    )
    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=[aligned_artifact],
        warnings=[
            ProblemRecord.warning(
                "timeline.mock_alignment",
                "mock alignPhrase aligned each phrase from first lyric and MIDI anchors without audio confidence scoring",
            )
        ],
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="timeline-local"),
    )


def _mock_phrase_alignments(
    phrases: list[object],
    *,
    notes: list[TimedFragment],
    lyrics: list[TimedFragment],
) -> dict[str, PhraseAlignment]:
    alignments: dict[str, PhraseAlignment] = {}
    notes_by_phrase = _fragments_by_phrase(notes)
    lyrics_by_phrase = _fragments_by_phrase(lyrics)
    for phrase in phrases:
        if not isinstance(phrase, dict):
            continue
        phrase_id = str(phrase["id"])
        phrase_start_ms = int(phrase["phraseStartMs"])
        phrase_notes = sorted(notes_by_phrase.get(phrase_id, []), key=_timed_fragment_sort_key)
        phrase_lyrics = sorted(lyrics_by_phrase.get(phrase_id, []), key=_timed_fragment_sort_key)
        anchor_note = phrase_notes[0] if phrase_notes else None
        anchor_lyric = phrase_lyrics[0] if phrase_lyrics else None
        detected_anchor_ms = anchor_note.unaligned_global_start_ms if anchor_note else phrase_start_ms
        target_anchor_ms = anchor_lyric.unaligned_global_start_ms if anchor_lyric else phrase_start_ms
        warnings: list[str] = []
        if anchor_note is None:
            warnings.append("no MIDI anchor found; phrase offset falls back to phrase start")
        if anchor_lyric is None:
            warnings.append("no lyric anchor found; phrase offset falls back to phrase start")
        alignments[phrase_id] = PhraseAlignment(
            target_anchor_ms=target_anchor_ms,
            detected_anchor_ms=detected_anchor_ms,
            warnings=warnings,
        )
    return alignments


def _fragments_by_phrase(fragments: list[TimedFragment]) -> dict[str, list[TimedFragment]]:
    grouped: dict[str, list[TimedFragment]] = {}
    for fragment in fragments:
        grouped.setdefault(fragment.phrase_id, []).append(fragment)
    return grouped


def _fragments_for_phrase(fragments: list[TimedFragment], phrase_id: str) -> list[TimedFragment]:
    return [fragment for fragment in fragments if fragment.phrase_id == phrase_id]


def _timed_fragment_sort_key(fragment: TimedFragment) -> tuple[int, int, str]:
    return (fragment.unaligned_global_start_ms, fragment.unaligned_global_end_ms, fragment.fragment_id)


def _fragment_sort_key(fragment: AlignedFragment) -> tuple[int, int, str]:
    return (fragment.global_start_ms, fragment.global_end_ms, fragment.fragment_id)


def _find_required_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef:
    artifact = envelope.input_artifact_index.get(artifact_id)
    if artifact is not None:
        return artifact
    raise KeyError(artifact_id)
