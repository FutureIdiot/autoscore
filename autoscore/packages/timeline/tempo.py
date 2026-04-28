"""Tempo timeline helpers.

This module intentionally contains only deterministic tempo math for now. Real
tempo estimation through librosa or Essentia can be added behind the same package
boundary later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
            warnings=list(data.get("warnings", [])),
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
