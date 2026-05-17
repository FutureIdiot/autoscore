"""Stitch phrase-level aligned fragments into a song timeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.core.problems import ProblemRecord
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


def run_mock_phrase_stitcher(envelope: Any, store: LocalArtifactStore) -> Any:
    """Write a song-level stitched timeline from phrase alignment artifacts."""

    from autoscore.core.tasks import ExecutionInfo, TaskResult

    phrase_artifact = _find_required_input_artifact(envelope, "artifact_phrase_timeline_json")
    aligned_artifact = _find_required_input_artifact(envelope, "artifact_aligned_timeline_json")

    phrase_timeline = json.loads(store.materialize(phrase_artifact).read_text(encoding="utf-8"))
    aligned_data = json.loads(store.materialize(aligned_artifact).read_text(encoding="utf-8"))
    phrases = [PhraseSlice.from_dict(phrase) for phrase in phrase_timeline.get("phrases", [])]
    notes = [AlignedFragment.from_dict(note) for note in aligned_data.get("notes", [])]
    lyrics = [AlignedFragment.from_dict(lyric) for lyric in aligned_data.get("lyrics", [])]
    alignments = {
        phrase_id: PhraseAlignment.from_dict(alignment)
        for phrase_id, alignment in aligned_data.get("phraseAlignments", {}).items()
    }
    timeline = stitch_fragments(
        phrases,
        notes=notes,
        lyrics=lyrics,
        alignments=alignments,
    )
    payload = {
        "schema": "autoscore.stitched_timeline.mock.v1",
        "source": "mock-phrase-stitch",
        "phraseTimelineArtifact": phrase_artifact.to_dict(),
        "alignedTimelineArtifact": aligned_artifact.to_dict(),
        "meter": phrase_timeline.get("meter"),
        "barDurationMs": phrase_timeline.get("barDurationMs"),
        "lyricNoteAlignments": aligned_data.get("lyricNoteAlignments", []),
        **timeline.to_dict(),
    }
    target = store.resolve_relative_path("timeline/stitched.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    stitched_artifact = store.create_ref(
        artifact_id="artifact_stitched_timeline_json",
        kind="application/json",
        relative_path="timeline/stitched.json",
        metadata={
            "mock": True,
            "source": "mock-phrase-stitch",
            "phraseTimelineArtifactId": phrase_artifact.artifact_id,
            "alignedTimelineArtifactId": aligned_artifact.artifact_id,
        },
    )
    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=[stitched_artifact],
        warnings=[
            ProblemRecord.warning(
                "timeline.mock_stitch",
                "mock stitchPhrases assembled aligned phrase fragments into a global timeline",
            )
        ],
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="timeline-local"),
    )


def _find_required_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef:
    artifact = envelope.input_artifact_index.get(artifact_id)
    if artifact is not None:
        return artifact
    raise KeyError(artifact_id)
