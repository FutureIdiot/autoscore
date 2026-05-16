"""Mock MIDI analysis package boundary."""

from __future__ import annotations

import json
from typing import Any

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.core.problems import ProblemRecord


PITCH_PATTERN = (60, 62, 64, 65, 67, 69, 71, 72)
NOTES_PER_PHRASE = 4


def run_mock_midi_analyzer(envelope: Any, store: LocalArtifactStore) -> Any:
    """Write deterministic note fragments from phrase timing and a MIDI input."""

    from autoscore.runtime.tasks import ExecutionInfo, TaskResult

    midi_artifact = _find_required_input_artifact(envelope, "artifact_melody_midi")
    phrase_timeline_artifact = _find_required_input_artifact(envelope, "artifact_phrase_timeline_json")
    store.materialize(midi_artifact)
    phrase_timeline = json.loads(store.materialize(phrase_timeline_artifact).read_text(encoding="utf-8"))

    notes = []
    note_index = 1
    for phrase in phrase_timeline.get("phrases", []):
        phrase_id = str(phrase["id"])
        phrase_start_ms = int(phrase["phraseStartMs"])
        phrase_end_ms = int(phrase["phraseEndMs"])
        phrase_duration_ms = max(1, phrase_end_ms - phrase_start_ms)
        for local_start_ms, local_end_ms in _note_windows(phrase_duration_ms):
            pitch = PITCH_PATTERN[(note_index - 1) % len(PITCH_PATTERN)]
            notes.append(
                {
                    "id": f"note_{note_index:03d}",
                    "phraseId": phrase_id,
                    "localStartMs": local_start_ms,
                    "localEndMs": local_end_ms,
                    "unalignedGlobalStartMs": phrase_start_ms + local_start_ms,
                    "unalignedGlobalEndMs": phrase_start_ms + local_end_ms,
                    "source": "midi",
                    "pitch": pitch,
                    "velocity": 88,
                    "channel": 0,
                }
            )
            note_index += 1

    payload = {
        "source": "mock-midi-analysis",
        "midiArtifact": midi_artifact.to_dict(),
        "phraseTimelineArtifact": phrase_timeline_artifact.to_dict(),
        "settings": {
            "notesPerPhrase": NOTES_PER_PHRASE,
            "pitchPattern": list(PITCH_PATTERN),
        },
        "notes": notes,
    }
    target = store.resolve_relative_path("midi/notes.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    notes_artifact = store.create_ref(
        artifact_id="artifact_midi_notes_json",
        kind="application/json",
        relative_path="midi/notes.json",
        metadata={
            "mock": True,
            "source": "mock-midi-analysis",
            "midiArtifactId": midi_artifact.artifact_id,
            "phraseTimelineArtifactId": phrase_timeline_artifact.artifact_id,
        },
    )
    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=[notes_artifact],
        warnings=[
            ProblemRecord.warning(
                "midi.mock_analysis",
                "mock analyzeMidi generated deterministic notes from phrase timing without parsing MIDI events",
            )
        ],
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="midi-local"),
    )


def _note_windows(duration_ms: int) -> list[tuple[int, int]]:
    windows = []
    for index in range(NOTES_PER_PHRASE):
        local_start_ms = round(index * duration_ms / NOTES_PER_PHRASE)
        local_end_ms = round((index + 1) * duration_ms / NOTES_PER_PHRASE)
        if local_end_ms <= local_start_ms:
            local_end_ms = local_start_ms + 1
        windows.append((local_start_ms, local_end_ms))
    return windows


def _find_required_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef:
    for artifact in envelope.input_artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    raise KeyError(artifact_id)
