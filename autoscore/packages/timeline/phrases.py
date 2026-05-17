"""Phrase slice timeline models."""

from __future__ import annotations

import json
import re
import shutil
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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
            warnings=list(data.get("warnings") or []),
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
HARD_MAX_BARS = 32
PADDING_MS = 400
MOCK_VOCAL_LEAD_IN_MS = 1200
MOCK_SILENCE_GAP_MS = 600
MIN_MOCK_PHRASE_MS = 1200
TEMPO_ADVISORY_PHRASE_BARS = 4

_LRC_TIMESTAMP_PATTERN = re.compile(
    r"\[(?P<minutes>\d{1,3}):(?P<seconds>\d{2})(?:[.:](?P<fraction>\d{1,3}))?\]"
)
_SRT_TIMESTAMP_PATTERN = re.compile(
    r"(?P<hours>\d{1,2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})(?:[,.](?P<millis>\d{1,3}))?"
)


@dataclass(frozen=True, slots=True)
class TimedLyricLine:
    start_ms: int
    text: str


class PhraseTaskEnvelope(Protocol):
    task_id: str
    project_id: str
    task_type: str
    input_artifact_index: dict[str, ArtifactRef]


@dataclass(slots=True)
class PhraseDetectorInputs:
    vocals_artifact: ArtifactRef
    vocals_path: Path
    global_tempo: float
    meter: dict[str, int]
    total_duration_ms: int
    lyric_lines: list[str]
    timed_lyrics: list[TimedLyricLine]
    warnings: list[ProblemRecord]


def run_mock_phrase_detector(envelope: PhraseTaskEnvelope, store: LocalArtifactStore) -> Any:
    """Write deterministic phrase slices from lyric/vocal-like phrase evidence."""

    from autoscore.core.tasks import ExecutionInfo, TaskResult

    inputs = _parse_phrase_detector_inputs(envelope, store)
    bar_ms = _bar_duration_ms(inputs.global_tempo, inputs.meter)
    phrases = _detect_mock_phrase_slices(inputs, bar_ms=bar_ms)
    output_artifacts, phrase_slices = _write_phrase_outputs(
        phrases,
        vocals_artifact=inputs.vocals_artifact,
        vocals_path=inputs.vocals_path,
        store=store,
    )
    output_artifacts.insert(
        0,
        _write_phrase_timeline(
            phrase_slices,
            meter=inputs.meter,
            bar_ms=bar_ms,
            store=store,
        ),
    )
    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=output_artifacts,
        warnings=inputs.warnings,
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="timeline-local"),
    )


def _parse_phrase_detector_inputs(envelope: PhraseTaskEnvelope, store: LocalArtifactStore) -> PhraseDetectorInputs:
    warnings = []
    vocals_artifact = _find_required_input_artifact(envelope, "artifact_vocals_wav")
    tempo_data, tempo_warnings = _load_tempo_data(envelope, store)
    metadata, metadata_warnings = _load_manual_metadata(envelope, store)
    warnings.extend(tempo_warnings)
    warnings.extend(metadata_warnings)

    global_tempo = float(tempo_data["globalTempo"])
    meter = _normalize_meter(metadata.get("meter"))
    bar_ms = _bar_duration_ms(global_tempo, meter)
    vocals_path = store.materialize(vocals_artifact)
    lyrics_artifact = _find_optional_input_artifact(envelope, "artifact_lyrics_txt")
    lyric_lines, timed_lyrics = _load_lyric_evidence(lyrics_artifact, store)
    total_duration_ms = _resolve_total_duration_ms(
        vocals_path,
        timed_lyrics=timed_lyrics,
        lyric_phrase_count=len(lyric_lines),
        bar_ms=bar_ms,
        lyrics_provided=lyrics_artifact is not None,
        warnings=warnings,
    )
    return PhraseDetectorInputs(
        vocals_artifact=vocals_artifact,
        vocals_path=vocals_path,
        global_tempo=global_tempo,
        meter=meter,
        total_duration_ms=total_duration_ms,
        lyric_lines=lyric_lines,
        timed_lyrics=timed_lyrics,
        warnings=warnings,
    )


def _load_tempo_data(envelope: PhraseTaskEnvelope, store: LocalArtifactStore) -> tuple[dict[str, Any], list[ProblemRecord]]:
    tempo_artifact = _find_optional_input_artifact(envelope, "artifact_tempo_timeline_json")
    if tempo_artifact is not None:
        return json.loads(store.materialize(tempo_artifact).read_text(encoding="utf-8")), []
    return {"globalTempo": 120}, [
        ProblemRecord.warning(
            "phrases.missing_tempo",
            "tempo timeline was not provided; detectPhrases defaulted to 120 BPM",
        )
    ]


def _load_manual_metadata(
    envelope: PhraseTaskEnvelope,
    store: LocalArtifactStore,
) -> tuple[dict[str, Any], list[ProblemRecord]]:
    metadata_artifact = _find_optional_input_artifact(envelope, "artifact_manual_metadata_json")
    if metadata_artifact is not None:
        return json.loads(store.materialize(metadata_artifact).read_text(encoding="utf-8")), []
    return {}, [
        ProblemRecord.warning(
            "phrases.missing_metadata",
            "manual metadata was not provided; detectPhrases defaulted to 4/4 meter",
        )
    ]


def _load_lyric_evidence(
    lyrics_artifact: ArtifactRef | None,
    store: LocalArtifactStore,
) -> tuple[list[str], list[TimedLyricLine]]:
    if lyrics_artifact is None:
        return [], []
    lyrics_path = store.materialize(lyrics_artifact)
    return _untimed_lyric_phrases(lyrics_path), _timed_lyric_lines(lyrics_path)


def _resolve_total_duration_ms(
    vocals_path: Path,
    *,
    timed_lyrics: list[TimedLyricLine],
    lyric_phrase_count: int,
    bar_ms: float,
    lyrics_provided: bool,
    warnings: list[ProblemRecord],
) -> int:
    total_duration_ms = _audio_duration_ms(vocals_path)
    if total_duration_ms is not None:
        if not lyrics_provided:
            warnings.append(
                ProblemRecord.warning(
                    "phrases.missing_lyrics",
                    "lyrics were not provided; detectPhrases used audio duration only",
                )
            )
        return total_duration_ms

    if not lyrics_provided:
        warnings.append(
            ProblemRecord.warning(
                "phrases.missing_lyrics",
                "lyrics were not provided and audio duration could not be read; mock detectPhrases emitted one vocal-like phrase",
            )
        )
    return _mock_duration_from_evidence(
        timed_lyrics=timed_lyrics,
        lyric_phrase_count=lyric_phrase_count,
        bar_ms=bar_ms,
    )


def _detect_mock_phrase_slices(inputs: PhraseDetectorInputs, *, bar_ms: float) -> list[PhraseSlice]:
    if inputs.timed_lyrics:
        return _build_mock_phrases_from_timed_lyrics(
            inputs.timed_lyrics,
            total_duration_ms=inputs.total_duration_ms,
            bar_ms=bar_ms,
        )
    if inputs.lyric_lines:
        return _build_mock_phrases_from_lyrics(
            inputs.lyric_lines,
            total_duration_ms=inputs.total_duration_ms,
            bar_ms=bar_ms,
        )
    return _build_mock_phrases_from_vocal_activity(total_duration_ms=inputs.total_duration_ms, bar_ms=bar_ms)


def _write_phrase_outputs(
    phrases: list[PhraseSlice],
    *,
    vocals_artifact: ArtifactRef,
    vocals_path: Path,
    store: LocalArtifactStore,
) -> tuple[list[ArtifactRef], list[PhraseSlice]]:
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
    return output_artifacts, phrase_slices


def _write_phrase_timeline(
    phrase_slices: list[PhraseSlice],
    *,
    meter: dict[str, int],
    bar_ms: float,
    store: LocalArtifactStore,
) -> ArtifactRef:
    timeline = {
        "source": "mock-vocal-phrase",
        "meter": meter,
        "settings": {
            "tempoAdvisoryPhraseBars": TEMPO_ADVISORY_PHRASE_BARS,
            "hardMaxBars": HARD_MAX_BARS,
            "paddingMs": PADDING_MS,
            "mockVocalLeadInMs": MOCK_VOCAL_LEAD_IN_MS,
            "mockSilenceGapMs": MOCK_SILENCE_GAP_MS,
        },
        "barDurationMs": bar_ms,
        "phrases": [phrase.to_dict() for phrase in phrase_slices],
    }
    target = store.resolve_relative_path("timeline/phrases.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return store.create_ref(
        artifact_id="artifact_phrase_timeline_json",
        kind="application/json",
        relative_path="timeline/phrases.json",
        metadata={"mock": True, "source": "mock-vocal-phrase"},
    )

def _build_mock_phrases_from_timed_lyrics(
    timed_lyrics: list[TimedLyricLine],
    *,
    total_duration_ms: int,
    bar_ms: float,
) -> list[PhraseSlice]:
    phrases = []
    ordered = sorted(timed_lyrics, key=lambda item: item.start_ms)
    default_phrase_ms = _advisory_phrase_ms(bar_ms)
    for index, line in enumerate(ordered):
        next_start_ms = ordered[index + 1].start_ms if index + 1 < len(ordered) else None
        end_limit = (
            total_duration_ms
            if next_start_ms is None
            else max(line.start_ms + 1, next_start_ms - MOCK_SILENCE_GAP_MS)
        )
        end_ms = min(end_limit, line.start_ms + default_phrase_ms)
        end_ms = max(line.start_ms + MIN_MOCK_PHRASE_MS, end_ms)
        end_ms = min(total_duration_ms, end_ms)
        phrase_id = f"phrase_{index + 1:03d}"
        phrases.append(
            PhraseSlice(
                phrase_id=phrase_id,
                index=index,
                phrase_start_ms=line.start_ms,
                phrase_end_ms=end_ms,
                slice_start_ms=max(0, line.start_ms - PADDING_MS),
                slice_end_ms=min(total_duration_ms, end_ms + PADDING_MS),
                start_bar=line.start_ms / bar_ms,
                end_bar=end_ms / bar_ms,
                boundary_source="timed-lyrics",
                boundary_confidence=0.8,
                warnings=["mock slice uses copied vocals; timed lyric anchors are not audio-trimmed yet"],
            )
        )
    return phrases


def _build_mock_phrases_from_lyrics(
    lyric_lines: list[str],
    *,
    total_duration_ms: int,
    bar_ms: float,
) -> list[PhraseSlice]:
    phrase_ms = _advisory_phrase_ms(bar_ms)
    phrases = []
    start_ms = min(MOCK_VOCAL_LEAD_IN_MS, max(0, total_duration_ms - MIN_MOCK_PHRASE_MS))
    for index, _line in enumerate(lyric_lines):
        remaining_phrases = len(lyric_lines) - index
        remaining_ms = max(MIN_MOCK_PHRASE_MS, total_duration_ms - start_ms)
        duration_ms = min(
            phrase_ms,
            max(MIN_MOCK_PHRASE_MS, round(remaining_ms / remaining_phrases) - MOCK_SILENCE_GAP_MS),
        )
        end_ms = min(total_duration_ms, start_ms + duration_ms)
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
                slice_end_ms=min(total_duration_ms, end_ms + PADDING_MS),
                start_bar=start_ms / bar_ms,
                end_bar=end_ms / bar_ms,
                boundary_source="mock-lyric-vocal-activity",
                boundary_confidence=0.45,
                warnings=["mock slice uses copied vocals; lyric phrases simulate vocal activity until real detection exists"],
            )
        )
        start_ms = end_ms + MOCK_SILENCE_GAP_MS
    return phrases


def _build_mock_phrases_from_vocal_activity(*, total_duration_ms: int, bar_ms: float) -> list[PhraseSlice]:
    start_ms = min(MOCK_VOCAL_LEAD_IN_MS, max(0, total_duration_ms - MIN_MOCK_PHRASE_MS))
    end_ms = min(total_duration_ms, start_ms + _advisory_phrase_ms(bar_ms))
    if end_ms <= start_ms:
        end_ms = start_ms + 1
    return [
        PhraseSlice(
            phrase_id="phrase_001",
            index=0,
            phrase_start_ms=start_ms,
            phrase_end_ms=end_ms,
            slice_start_ms=max(0, start_ms - PADDING_MS),
            slice_end_ms=min(total_duration_ms, end_ms + PADDING_MS),
            start_bar=start_ms / bar_ms,
            end_bar=end_ms / bar_ms,
            boundary_source="mock-vocal-activity",
            boundary_confidence=0.3,
            warnings=["mock slice uses copied vocals; real vocal activity detection is not enabled yet"],
        )
    ]


def _mock_duration_from_evidence(
    *,
    timed_lyrics: list[TimedLyricLine],
    lyric_phrase_count: int,
    bar_ms: float,
) -> int:
    phrase_ms = _advisory_phrase_ms(bar_ms)
    if timed_lyrics:
        return max(timed_lyrics[-1].start_ms + phrase_ms, phrase_ms)
    phrase_count = max(1, lyric_phrase_count)
    return MOCK_VOCAL_LEAD_IN_MS + phrase_count * phrase_ms + max(0, phrase_count - 1) * MOCK_SILENCE_GAP_MS


def _advisory_phrase_ms(bar_ms: float) -> int:
    return max(MIN_MOCK_PHRASE_MS, round(TEMPO_ADVISORY_PHRASE_BARS * bar_ms))


def _untimed_lyric_phrases(lyrics_path: Path) -> list[str]:
    phrases = []
    for line in lyrics_path.read_text(encoding="utf-8").splitlines():
        cleaned = _strip_timestamps(line).strip()
        if cleaned:
            phrases.append(cleaned)
    return phrases


def _timed_lyric_lines(lyrics_path: Path) -> list[TimedLyricLine]:
    lines = [line.strip() for line in lyrics_path.read_text(encoding="utf-8").splitlines()]
    timed_lines: list[TimedLyricLine] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue

        lrc_matches = list(_LRC_TIMESTAMP_PATTERN.finditer(line))
        if lrc_matches:
            text = _strip_timestamps(line).strip()
            if text:
                for match in lrc_matches:
                    timed_lines.append(TimedLyricLine(start_ms=_lrc_match_to_ms(match), text=text))
            index += 1
            continue

        if _is_srt_sequence_number(line) and index + 1 < len(lines) and _is_srt_timestamp_line(lines[index + 1]):
            index += 1
            line = lines[index]

        srt_match = _SRT_TIMESTAMP_PATTERN.search(line)
        if srt_match and "-->" in line:
            text_lines = []
            index += 1
            while index < len(lines) and lines[index] and not _starts_srt_cue(lines, index):
                text_lines.append(lines[index])
                index += 1
            _append_pending_srt_line(timed_lines, _srt_match_to_ms(srt_match), text_lines)
            continue

        index += 1
    return _merge_timed_lyric_lines(timed_lines)


def _append_pending_srt_line(
    timed_lines: list[TimedLyricLine],
    start_ms: int | None,
    text_lines: list[str],
) -> None:
    if start_ms is None:
        return
    text = " ".join(line.strip() for line in text_lines if line.strip())
    if text:
        timed_lines.append(TimedLyricLine(start_ms=start_ms, text=text))


def _merge_timed_lyric_lines(timed_lines: list[TimedLyricLine]) -> list[TimedLyricLine]:
    merged: dict[int, list[str]] = {}
    for line in sorted(timed_lines, key=lambda item: item.start_ms):
        merged.setdefault(line.start_ms, []).append(line.text)
    return [
        TimedLyricLine(start_ms=start_ms, text=" ".join(texts))
        for start_ms, texts in sorted(merged.items())
    ]


def _strip_timestamps(line: str) -> str:
    stripped = _LRC_TIMESTAMP_PATTERN.sub("", line)
    stripped = _SRT_TIMESTAMP_PATTERN.sub("", stripped)
    return stripped.replace("-->", "").strip()


def _lrc_match_to_ms(match: re.Match[str]) -> int:
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    fraction = match.group("fraction") or "0"
    millis = int(fraction.ljust(3, "0")[:3])
    return minutes * 60_000 + seconds * 1000 + millis


def _srt_match_to_ms(match: re.Match[str]) -> int:
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    seconds = int(match.group("seconds"))
    millis = int((match.group("millis") or "0").ljust(3, "0")[:3])
    return hours * 3_600_000 + minutes * 60_000 + seconds * 1000 + millis


def _is_srt_sequence_number(line: str) -> bool:
    return line.isdecimal()


def _is_srt_timestamp_line(line: str) -> bool:
    return "-->" in line and _SRT_TIMESTAMP_PATTERN.search(line) is not None


def _starts_srt_cue(lines: list[str], index: int) -> bool:
    line = lines[index]
    if _is_srt_timestamp_line(line):
        return True
    return _is_srt_sequence_number(line) and index + 1 < len(lines) and _is_srt_timestamp_line(lines[index + 1])


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
    artifact = envelope.input_artifact_index.get(artifact_id)
    if artifact is not None:
        return artifact
    raise KeyError(f"missing required input artifact: {artifact_id}")


def _find_optional_input_artifact(envelope: Any, artifact_id: str) -> ArtifactRef | None:
    return envelope.input_artifact_index.get(artifact_id)
