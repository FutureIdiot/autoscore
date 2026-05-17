"""Mock score JSON export package boundary."""

from __future__ import annotations

import json
from typing import Any

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.core.problems import ProblemRecord


def run_mock_score_json_builder(envelope: Any, store: LocalArtifactStore) -> Any:
    """Write a placeholder score.json from current mock timeline artifacts."""

    from autoscore.core.tasks import ExecutionInfo, TaskResult

    phrase_artifact = _find_required_input_artifact(envelope, "artifact_phrase_timeline_json")
    notes_artifact = _find_required_input_artifact(envelope, "artifact_midi_notes_json")
    lyrics_artifact = _find_required_input_artifact(envelope, "artifact_lyric_fragments_json")

    phrase_timeline = json.loads(store.materialize(phrase_artifact).read_text(encoding="utf-8"))
    note_data = json.loads(store.materialize(notes_artifact).read_text(encoding="utf-8"))
    lyric_data = json.loads(store.materialize(lyrics_artifact).read_text(encoding="utf-8"))
    notes = list(note_data.get("notes", []))
    lyrics = list(lyric_data.get("lyrics", []))

    score = {
        "schema": "autoscore.score.mock.v1",
        "source": "mock-score-json",
        "inputs": {
            "phraseTimelineArtifactId": phrase_artifact.artifact_id,
            "midiNotesArtifactId": notes_artifact.artifact_id,
            "lyricFragmentsArtifactId": lyrics_artifact.artifact_id,
        },
        "meter": phrase_timeline.get("meter"),
        "barDurationMs": phrase_timeline.get("barDurationMs"),
        "phrases": [
            _score_phrase(phrase, notes=notes, lyrics=lyrics)
            for phrase in phrase_timeline.get("phrases", [])
        ],
    }
    target = store.resolve_relative_path("score/score.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(score, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    score_artifact = store.create_ref(
        artifact_id="artifact_score_json",
        kind="application/json",
        relative_path="score/score.json",
        metadata={
            "mock": True,
            "source": "mock-score-json",
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
        output_artifacts=[score_artifact],
        warnings=[
            ProblemRecord.warning(
                "score.mock_export",
                "mock buildScoreJson exported placeholder score JSON without phrase alignment or notation layout",
            )
        ],
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="score-export-local"),
    )


def _score_phrase(
    phrase: dict[str, Any],
    *,
    notes: list[object],
    lyrics: list[object],
) -> dict[str, Any]:
    phrase_id = str(phrase["id"])
    phrase_notes = [
        _score_note(note)
        for note in notes
        if isinstance(note, dict) and note.get("phraseId") == phrase_id
    ]
    phrase_lyrics = [
        _score_lyric(lyric)
        for lyric in lyrics
        if isinstance(lyric, dict) and lyric.get("phraseId") == phrase_id
    ]
    return {
        "id": phrase_id,
        "index": phrase.get("index"),
        "phraseStartMs": phrase.get("phraseStartMs"),
        "phraseEndMs": phrase.get("phraseEndMs"),
        "notes": phrase_notes,
        "lyrics": phrase_lyrics,
    }


def _score_note(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": note.get("id"),
        "startMs": note.get("unalignedGlobalStartMs"),
        "endMs": note.get("unalignedGlobalEndMs"),
        "pitch": note.get("pitch"),
        "velocity": note.get("velocity"),
        "source": note.get("source"),
    }


def _score_lyric(lyric: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": lyric.get("id"),
        "startMs": lyric.get("unalignedGlobalStartMs"),
        "endMs": lyric.get("unalignedGlobalEndMs"),
        "text": lyric.get("text"),
        "source": lyric.get("source"),
    }


def _find_required_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef:
    artifact = envelope.input_artifact_index.get(artifact_id)
    if artifact is not None:
        return artifact
    raise KeyError(artifact_id)
