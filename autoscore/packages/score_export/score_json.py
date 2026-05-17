"""Mock score JSON export package boundary."""

from __future__ import annotations

import json
from typing import Any

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.core.problems import ProblemRecord


def run_mock_score_json_builder(envelope: Any, store: LocalArtifactStore) -> Any:
    """Write a placeholder score.json from the stitched song timeline."""

    from autoscore.core.tasks import ExecutionInfo, TaskResult

    stitched_artifact = _find_required_input_artifact(envelope, "artifact_stitched_timeline_json")

    stitched_timeline = json.loads(store.materialize(stitched_artifact).read_text(encoding="utf-8"))
    notes = list(stitched_timeline.get("notes", []))
    lyrics = list(stitched_timeline.get("lyrics", []))

    score = {
        "schema": "autoscore.score.mock.v1",
        "source": "mock-score-json",
        "inputs": {
            "stitchedTimelineArtifactId": stitched_artifact.artifact_id,
        },
        "meter": stitched_timeline.get("meter"),
        "barDurationMs": stitched_timeline.get("barDurationMs"),
        "lyricNoteAlignments": stitched_timeline.get("lyricNoteAlignments", []),
        "phrases": [
            _score_phrase(phrase, notes=notes, lyrics=lyrics)
            for phrase in stitched_timeline.get("phrases", [])
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
            "stitchedTimelineArtifactId": stitched_artifact.artifact_id,
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
                "mock buildScoreJson exported placeholder score JSON from stitched timeline without notation layout",
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
        "startMs": note.get("globalStartMs"),
        "endMs": note.get("globalEndMs"),
        "pitch": note.get("pitch"),
        "velocity": note.get("velocity"),
        "source": note.get("source"),
    }


def _score_lyric(lyric: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": lyric.get("id"),
        "startMs": lyric.get("globalStartMs"),
        "endMs": lyric.get("globalEndMs"),
        "text": lyric.get("text"),
        "source": lyric.get("source"),
    }


def _find_required_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef:
    artifact = envelope.input_artifact_index.get(artifact_id)
    if artifact is not None:
        return artifact
    raise KeyError(artifact_id)
