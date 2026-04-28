"""Timeline analysis deployment package.

Owns the modules that build and refine the song timeline: global tempo analysis,
phrase slicing, phrase-level lyric/note alignment, and stitching aligned
fragments into a song-level timeline.

This package is separate from source separation because it should not inherit
heavy separator model or GPU dependencies. Tempo and phrase slicing stay
together because they may share audio-analysis dependencies such as librosa or
future Essentia-based runtimes.
"""

from autoscore.packages.timeline.align import AlignedFragment, PhraseAlignment, TimedFragment, align_fragments
from autoscore.packages.timeline.phrases import PhraseSlice
from autoscore.packages.timeline.stitch import StitchedTimeline, stitch_fragments
from autoscore.packages.timeline.tempo import DEFAULT_TIMEBASE, TempoCandidate, TempoTimeline, ms_to_tick, tick_to_ms

__all__ = [
    "DEFAULT_TIMEBASE",
    "AlignedFragment",
    "PhraseAlignment",
    "PhraseSlice",
    "StitchedTimeline",
    "TempoCandidate",
    "TempoTimeline",
    "TimedFragment",
    "align_fragments",
    "ms_to_tick",
    "stitch_fragments",
    "tick_to_ms",
]
