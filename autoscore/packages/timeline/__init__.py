"""Timeline analysis deployment package.

Owns the modules that build and refine the song timeline: global tempo analysis,
phrase slicing, phrase-level lyric/note alignment, and stitching aligned
fragments into a song-level timeline.

This package is separate from source separation because it should not inherit
heavy separator model or GPU dependencies. Tempo and phrase slicing stay
together because they may share audio-analysis dependencies such as librosa or
future Essentia-based runtimes.
"""
