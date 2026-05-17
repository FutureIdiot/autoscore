"""Mock lyric analysis package boundary."""

from __future__ import annotations

import json
from typing import Any

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.core.problems import ProblemRecord


def run_mock_lyric_analyzer(envelope: Any, store: LocalArtifactStore) -> Any:
    """Write deterministic lyric fragments from lyrics text and phrase timing."""

    from autoscore.runtime.tasks import ExecutionInfo, TaskResult

    lyrics_artifact = _find_required_input_artifact(envelope, "artifact_lyrics_txt")
    phrase_timeline_artifact = _find_required_input_artifact(envelope, "artifact_phrase_timeline_json")
    lyrics_path = store.materialize(lyrics_artifact)
    phrase_timeline = json.loads(store.materialize(phrase_timeline_artifact).read_text(encoding="utf-8"))
    lyric_lines = [line.strip() for line in lyrics_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    warnings = []
    if not lyric_lines:
        warnings.append(
            ProblemRecord.warning(
                "lyrics.empty",
                "lyrics text was empty; mock analyzeLyrics emitted no lyric fragments",
            )
        )

    fragments = []
    lyric_index = 1
    phrases = list(phrase_timeline.get("phrases", []))
    for phrase_index, phrase in enumerate(phrases):
        phrase_lines = _lines_for_phrase(lyric_lines, phrase_index, len(phrases))
        if not phrase_lines:
            continue
        phrase_id = str(phrase["id"])
        phrase_start_ms = int(phrase["phraseStartMs"])
        phrase_end_ms = int(phrase["phraseEndMs"])
        phrase_duration_ms = max(1, phrase_end_ms - phrase_start_ms)
        for local_start_ms, local_end_ms, text in _line_windows(phrase_lines, phrase_duration_ms):
            fragments.append(
                {
                    "id": f"lyric_{lyric_index:03d}",
                    "phraseId": phrase_id,
                    "localStartMs": local_start_ms,
                    "localEndMs": local_end_ms,
                    "unalignedGlobalStartMs": phrase_start_ms + local_start_ms,
                    "unalignedGlobalEndMs": phrase_start_ms + local_end_ms,
                    "source": "lyrics",
                    "text": text,
                }
            )
            lyric_index += 1

    payload = {
        "source": "mock-lyric-analysis",
        "lyricsArtifact": lyrics_artifact.to_dict(),
        "phraseTimelineArtifact": phrase_timeline_artifact.to_dict(),
        "lyrics": fragments,
    }
    target = store.resolve_relative_path("lyrics/fragments.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    fragments_artifact = store.create_ref(
        artifact_id="artifact_lyric_fragments_json",
        kind="application/json",
        relative_path="lyrics/fragments.json",
        metadata={
            "mock": True,
            "source": "mock-lyric-analysis",
            "lyricsArtifactId": lyrics_artifact.artifact_id,
            "phraseTimelineArtifactId": phrase_timeline_artifact.artifact_id,
        },
    )
    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=[fragments_artifact],
        warnings=warnings
        + [
            ProblemRecord.warning(
                "lyrics.mock_analysis",
                "mock analyzeLyrics distributed lyric lines across phrase timing without running forced alignment",
            )
        ],
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="lyric-local"),
    )


def _lines_for_phrase(lines: list[str], phrase_index: int, phrase_count: int) -> list[str]:
    if not lines or phrase_count <= 0:
        return []
    start = round(phrase_index * len(lines) / phrase_count)
    end = round((phrase_index + 1) * len(lines) / phrase_count)
    return lines[start:end]


def _line_windows(lines: list[str], duration_ms: int) -> list[tuple[int, int, str]]:
    windows = []
    for index, text in enumerate(lines):
        local_start_ms = round(index * duration_ms / len(lines))
        local_end_ms = round((index + 1) * duration_ms / len(lines))
        if local_end_ms <= local_start_ms:
            local_end_ms = local_start_ms + 1
        windows.append((local_start_ms, local_end_ms, text))
    return windows


def _find_required_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef:
    artifact = envelope.input_artifact_index.get(artifact_id)
    if artifact is not None:
        return artifact
    raise KeyError(artifact_id)
