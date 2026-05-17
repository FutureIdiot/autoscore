"""Tempo timeline helpers.

This module intentionally contains only deterministic tempo math for now. Real
tempo estimation through librosa or Essentia can be added behind the same package
boundary later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from autoscore.core.artifacts import LocalArtifactStore
from autoscore.core.problems import ProblemRecord

DEFAULT_TIMEBASE = 480


@dataclass(slots=True)
class TempoCandidate:
    """One advisory tempo estimate."""

    bpm: float
    source: str
    confidence: float | None = None
    warning: str | None = None

    def __post_init__(self) -> None:
        if self.bpm <= 0:
            raise ValueError("bpm must be positive")
        if not self.source:
            raise ValueError("source is required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TempoCandidate":
        return cls(
            bpm=float(data["bpm"]),
            source=data["source"],
            confidence=data.get("confidence"),
            warning=data.get("warning"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bpm": self.bpm,
            "source": self.source,
            "confidence": self.confidence,
            "warning": self.warning,
        }


@dataclass(slots=True)
class TempoTimeline:
    """Global tempo context used for timeline conversion."""

    global_tempo: float
    source: str
    grid_offset_ms: float = 0
    timebase: int = DEFAULT_TIMEBASE
    candidates: list[TempoCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.global_tempo <= 0:
            raise ValueError("global_tempo must be positive")
        if not self.source:
            raise ValueError("source is required")
        if self.timebase <= 0:
            raise ValueError("timebase must be positive")

    def ms_to_tick(self, ms: float) -> int:
        return ms_to_tick(ms, bpm=self.global_tempo, grid_offset_ms=self.grid_offset_ms, timebase=self.timebase)

    def tick_to_ms(self, tick: int | float) -> float:
        return tick_to_ms(tick, bpm=self.global_tempo, grid_offset_ms=self.grid_offset_ms, timebase=self.timebase)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TempoTimeline":
        return cls(
            global_tempo=float(data["globalTempo"]),
            source=data["source"],
            grid_offset_ms=float(data.get("gridOffsetMs", 0)),
            timebase=int(data.get("timebase", DEFAULT_TIMEBASE)),
            candidates=[TempoCandidate.from_dict(item) for item in data.get("candidates", [])],
            warnings=list(data.get("warnings") or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "globalTempo": self.global_tempo,
            "source": self.source,
            "gridOffsetMs": self.grid_offset_ms,
            "timebase": self.timebase,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "warnings": self.warnings,
        }


def ms_to_tick(ms: float, *, bpm: float, grid_offset_ms: float = 0, timebase: int = DEFAULT_TIMEBASE) -> int:
    """Convert milliseconds to nearest musical tick."""

    if bpm <= 0:
        raise ValueError("bpm must be positive")
    if timebase <= 0:
        raise ValueError("timebase must be positive")
    return round((ms - grid_offset_ms) / 60000 * bpm * timebase)


def tick_to_ms(tick: int | float, *, bpm: float, grid_offset_ms: float = 0, timebase: int = DEFAULT_TIMEBASE) -> float:
    """Convert musical tick to milliseconds."""

    if bpm <= 0:
        raise ValueError("bpm must be positive")
    if timebase <= 0:
        raise ValueError("timebase must be positive")
    return tick / timebase / bpm * 60000 + grid_offset_ms


def run_mock_tempo_estimator(envelope: Any, store: LocalArtifactStore) -> Any:
    """Write a deterministic tempo timeline artifact from manual metadata."""

    from autoscore.core.tasks import ExecutionInfo, TaskResult

    warnings = []
    metadata_artifact = _find_input_artifact(envelope, "artifact_manual_metadata_json")
    if metadata_artifact is None:
        metadata = {}
        warnings.append(
            ProblemRecord.warning(
                "tempo.missing_metadata",
                "manual metadata was not provided; mock tempo will use defaults",
            )
        )
    else:
        metadata_path = store.materialize(metadata_artifact)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    global_tempo = metadata.get("globalTempo")
    if global_tempo is None:
        global_tempo = 120
        source = "mock-default"
        warnings.append(
            ProblemRecord.warning(
                "tempo.mock_default",
                "manual tempo was not provided; mock tempo defaulted to 120 BPM",
            )
        )
    else:
        source = "manual"

    tempo = TempoTimeline(
        global_tempo=float(global_tempo),
        source=source,
        candidates=[
            TempoCandidate(
                bpm=float(global_tempo),
                source=source,
                confidence=1.0 if source == "manual" else 0.25,
            )
        ],
        warnings=[warning.message for warning in warnings],
    )
    target = store.resolve_relative_path("timeline/tempo.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(tempo.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    artifact = store.create_ref(
        artifact_id="artifact_tempo_timeline_json",
        kind="application/json",
        relative_path="timeline/tempo.json",
        metadata={"mock": True, "source": source},
    )
    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=[artifact],
        warnings=warnings,
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="timeline-local"),
    )


def _find_input_artifact(envelope: Any, artifact_id: str):
    return envelope.input_artifact_index.get(artifact_id)
