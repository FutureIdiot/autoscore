"""Phrase slice timeline models."""

from __future__ import annotations

import json
import shutil
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.core.problems import ProblemRecord


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
    start_bar: float | None = None
    end_bar: float | None = None
    boundary_source: str | None = None
    boundary_confidence: float | None = None
    warnings: list[str] | None = None

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
        if self.boundary_confidence is not None and not 0 <= self.boundary_confidence <= 1:
            raise ValueError("boundary_confidence must be between 0 and 1")
        if self.warnings is None:
            self.warnings = []

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
            start_bar=float(data["startBar"]) if data.get("startBar") is not None else None,
            end_bar=float(data["endBar"]) if data.get("endBar") is not None else None,
            boundary_source=data.get("boundarySource"),
            boundary_confidence=(
                float(data["boundaryConfidence"]) if data.get("boundaryConfidence") is not None else None
            ),
            warnings=list(data.get("warnings", [])),
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
            "startBar": self.start_bar,
            "endBar": self.end_bar,
            "boundarySource": self.boundary_source,
            "boundaryConfidence": self.boundary_confidence,
            "warnings": self.warnings or [],
        }


DEFAULT_METER = {"numerator": 4, "denominator": 4}
TARGET_PHRASE_BARS = 8
MIN_PHRASE_BARS = 7
TARGET_WINDOW_BARS = 1
HARD_MAX_BARS = 32
PADDING_MS = 400


def run_mock_phrase_detector(envelope: Any, store: LocalArtifactStore) -> Any:
    """Write deterministic phrase slices from tempo/meter context."""

    from autoscore.runtime.tasks import ExecutionInfo, TaskResult

    warnings = []
    vocals_artifact = _find_required_input_artifact(envelope, "artifact_vocals_wav")
    tempo_artifact = _find_required_input_artifact(envelope, "artifact_tempo_timeline_json")
    lyrics_artifact = _find_optional_input_artifact(envelope, "artifact_lyrics_txt")
    metadata_artifact = _find_optional_input_artifact(envelope, "artifact_manual_metadata_json")

    vocals_path = store.materialize(vocals_artifact)
    tempo_data = json.loads(store.materialize(tempo_artifact).read_text(encoding="utf-8"))
    if metadata_artifact is None:
        metadata = {}
        warnings.append(
            ProblemRecord.warning(
                "phrases.missing_metadata",
                "manual metadata was not provided; detectPhrases defaulted to 4/4 meter",
            )
        )
    else:
        metadata = json.loads(store.materialize(metadata_artifact).read_text(encoding="utf-8"))

    global_tempo = float(tempo_data["globalTempo"])
    meter = _normalize_meter(metadata.get("meter"))
    bar_ms = _bar_duration_ms(global_tempo, meter)
    target_phrase_ms = round(TARGET_PHRASE_BARS * bar_ms)
    total_duration_ms = _audio_duration_ms(vocals_path)
    if total_duration_ms is None and lyrics_artifact is not None:
        total_duration_ms = _mock_duration_from_lyrics(store.materialize(lyrics_artifact), target_phrase_ms)
    if total_duration_ms is None:
        total_duration_ms = target_phrase_ms
        warnings.append(
            ProblemRecord.warning(
                "phrases.missing_lyrics",
                "lyrics were not provided and audio duration could not be read; mock detectPhrases emitted one target-length phrase",
            )
        )
    elif lyrics_artifact is None:
        warnings.append(
            ProblemRecord.warning(
                "phrases.missing_lyrics",
                "lyrics were not provided; detectPhrases used audio duration only",
            )
        )

    phrases = _build_mock_phrases(total_duration_ms=total_duration_ms, bar_ms=bar_ms)
    output_artifacts: list[ArtifactRef] = []
    phrase_slices: list[PhraseSlice] = []
    for phrase in phrases:
        relative_path = f"phrases/{phrase.phrase_id}/vocals.wav"
        target = store.resolve_relative_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vocals_path, target)
        audio_artifact = store.create_ref(
            artifact_id=f"artifact_{phrase.phrase_id}_vocals_wav",
            kind="audio/wav",
            relative_path=relative_path,
            metadata={
                "mock": True,
                "mockSourceArtifactId": vocals_artifact.artifact_id,
                "phraseId": phrase.phrase_id,
                "sliceStartMs": phrase.slice_start_ms,
                "sliceEndMs": phrase.slice_end_ms,
            },
        )
        output_artifacts.append(audio_artifact)
        phrase.audio_artifact = audio_artifact
        phrase_slices.append(phrase)

    timeline = {
        "source": "mock-bar-window",
        "meter": meter,
        "settings": {
            "targetPhraseBars": TARGET_PHRASE_BARS,
            "minPhraseBars": MIN_PHRASE_BARS,
            "targetWindowBars": TARGET_WINDOW_BARS,
            "hardMaxBars": HARD_MAX_BARS,
            "paddingMs": PADDING_MS,
        },
        "barDurationMs": bar_ms,
        "phrases": [phrase.to_dict() for phrase in phrase_slices],
    }
    target = store.resolve_relative_path("timeline/phrases.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    output_artifacts.insert(
        0,
        store.create_ref(
            artifact_id="artifact_phrase_timeline_json",
            kind="application/json",
            relative_path="timeline/phrases.json",
            metadata={"mock": True, "source": "mock-bar-window"},
        ),
    )
    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=output_artifacts,
        warnings=warnings,
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="timeline-local"),
    )


def _build_mock_phrases(*, total_duration_ms: int, bar_ms: float) -> list[PhraseSlice]:
    phrase_ms = round(TARGET_PHRASE_BARS * bar_ms)
    if phrase_ms <= 0:
        raise ValueError("phrase duration must be positive")
    phrase_count = max(1, round(total_duration_ms / phrase_ms))
    phrases = []
    for index in range(phrase_count):
        start_ms = round(index * total_duration_ms / phrase_count)
        end_ms = round((index + 1) * total_duration_ms / phrase_count)
        if end_ms <= start_ms:
            end_ms = start_ms + 1
        phrase_id = f"phrase_{index + 1:03d}"
        phrases.append(
            PhraseSlice(
                phrase_id=phrase_id,
                index=index,
                phrase_start_ms=start_ms,
                phrase_end_ms=end_ms,
                slice_start_ms=max(0, start_ms - PADDING_MS),
                slice_end_ms=end_ms + PADDING_MS,
                start_bar=start_ms / bar_ms,
                end_bar=end_ms / bar_ms,
                boundary_source="mock-bar-window",
                boundary_confidence=0.25,
                warnings=["mock slice uses copied vocals; real audio trimming is not enabled yet"],
            )
        )
    return phrases


def _mock_duration_from_lyrics(lyrics_path: Path, target_phrase_ms: int) -> int:
    text = lyrics_path.read_text(encoding="utf-8")
    nonempty_lines = [line for line in text.splitlines() if line.strip()]
    phrase_count = max(1, len(nonempty_lines))
    return phrase_count * target_phrase_ms


def _audio_duration_ms(path: Path) -> int | None:
    try:
        with wave.open(str(path), "rb") as handle:
            frame_rate = handle.getframerate()
            if frame_rate <= 0:
                return None
            return round(handle.getnframes() / frame_rate * 1000)
    except (wave.Error, EOFError):
        return None


def _bar_duration_ms(bpm: float, meter: dict[str, int]) -> float:
    beat_unit_ms = 60000 / bpm * (4 / meter["denominator"])
    return beat_unit_ms * meter["numerator"]


def _normalize_meter(data: object) -> dict[str, int]:
    if not isinstance(data, dict) or not data:
        return dict(DEFAULT_METER)
    numerator = int(data.get("numerator", DEFAULT_METER["numerator"]))
    denominator = int(data.get("denominator", DEFAULT_METER["denominator"]))
    if numerator <= 0 or denominator <= 0:
        raise ValueError("meter numerator and denominator must be positive")
    return {"numerator": numerator, "denominator": denominator}


def _find_required_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef:
    for artifact in envelope.input_artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    raise KeyError(f"missing required input artifact: {artifact_id}")


def _find_optional_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef | None:
    for artifact in envelope.input_artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    return None
