"""Timeline analysis deployment package.

Owns the modules that build and refine the song timeline: global tempo analysis,
phrase slicing, phrase-level lyric/note alignment, and stitching aligned
fragments into a song-level timeline.

This package is separate from source separation because it should not inherit
heavy separator model or GPU dependencies. Tempo and phrase slicing stay
together because they may share audio-analysis dependencies such as librosa or
future Essentia-based runtimes.
"""

from autoscore.packages.timeline.align import (
    AlignedFragment,
    LyricNoteAlignment,
    PhraseAlignment,
    TimedFragment,
    align_fragments,
    match_lyrics_to_notes,
    run_mock_phrase_aligner,
)
from autoscore.packages.timeline.phrases import PhraseSlice, run_mock_phrase_detector
from autoscore.packages.timeline.stitch import StitchedTimeline, run_mock_phrase_stitcher, stitch_fragments
from autoscore.packages.timeline.tempo import DEFAULT_TIMEBASE, TempoCandidate, TempoTimeline, ms_to_tick, tick_to_ms

__all__ = [
    "DEFAULT_TIMEBASE",
    "AlignedFragment",
    "LyricNoteAlignment",
    "PhraseAlignment",
    "PhraseSlice",
    "StitchedTimeline",
    "TempoCandidate",
    "TempoTimeline",
    "TimedFragment",
    "align_fragments",
    "match_lyrics_to_notes",
    "ms_to_tick",
    "run_mock_phrase_aligner",
    "run_mock_phrase_detector",
    "run_mock_phrase_stitcher",
    "stitch_fragments",
    "tick_to_ms",
]
