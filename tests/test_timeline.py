import tempfile
import unittest
from pathlib import Path

from autoscore.core.artifacts import ArtifactRef
from autoscore.packages.timeline.phrases import _timed_lyric_lines
from autoscore.packages.timeline import (
    AlignedFragment,
    LyricNoteAlignment,
    PhraseAlignment,
    PhraseSlice,
    TempoCandidate,
    TempoTimeline,
    TimedFragment,
    align_fragments,
    match_lyrics_to_notes,
    ms_to_tick,
    stitch_fragments,
    tick_to_ms,
)


class TempoTimelineTests(unittest.TestCase):
    def test_ms_tick_round_trip_uses_grid_offset(self) -> None:
        tempo = TempoTimeline(global_tempo=120, source="manual", grid_offset_ms=100, timebase=480)

        self.assertEqual(tempo.ms_to_tick(600), 480)
        self.assertEqual(tempo.tick_to_ms(480), 600)
        self.assertEqual(ms_to_tick(600, bpm=120, grid_offset_ms=100), 480)
        self.assertEqual(tick_to_ms(480, bpm=120, grid_offset_ms=100), 600)

    def test_tempo_candidate_round_trip_uses_contract_names(self) -> None:
        candidate = TempoCandidate(bpm=119.8, source="librosa", warning="manual tempo wins")
        data = candidate.to_dict()

        self.assertEqual(data["bpm"], 119.8)
        self.assertEqual(TempoCandidate.from_dict(data), candidate)


class PhraseSliceTests(unittest.TestCase):
    def test_phrase_slice_round_trip_uses_contract_names(self) -> None:
        artifact = ArtifactRef(
            artifact_id="artifact_phrase_001_wav",
            kind="audio/wav",
            relative_path="phrases/phrase_001.wav",
        )
        phrase = PhraseSlice(
            phrase_id="phrase_001",
            index=0,
            phrase_start_ms=1000,
            phrase_end_ms=4200,
            slice_start_ms=800,
            slice_end_ms=4400,
            audio_artifact=artifact,
        )

        data = phrase.to_dict()

        self.assertEqual(data["phraseStartMs"], 1000)
        self.assertEqual(data["sliceStartMs"], 800)
        self.assertEqual(PhraseSlice.from_dict(data), phrase)

    def test_rejects_slice_that_does_not_cover_phrase(self) -> None:
        with self.assertRaises(ValueError):
            PhraseSlice(
                phrase_id="phrase_001",
                index=0,
                phrase_start_ms=1000,
                phrase_end_ms=4200,
                slice_start_ms=1200,
                slice_end_ms=4400,
            )

    def test_srt_timed_lyrics_preserve_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lyrics_path = Path(temp_dir) / "lyrics.srt"
            lyrics_path.write_text(
                "1\n"
                "00:00:02,500 --> 00:00:05,000\n"
                "first line\n"
                "\n"
                "2\n"
                "00:00:08,000 --> 00:00:12,000\n"
                "second line\n",
                encoding="utf-8",
            )

            timed_lines = _timed_lyric_lines(lyrics_path)

        self.assertEqual([line.start_ms for line in timed_lines], [2500, 8000])
        self.assertEqual([line.text for line in timed_lines], ["first line", "second line"])


class PhraseAlignmentTests(unittest.TestCase):
    def test_phrase_alignment_computes_offset(self) -> None:
        alignment = PhraseAlignment(target_anchor_ms=1000, detected_anchor_ms=1034)

        self.assertEqual(alignment.phrase_offset_ms, -34)

    def test_align_fragments_applies_phrase_offset(self) -> None:
        fragment = TimedFragment(
            fragment_id="note_001",
            phrase_id="phrase_001",
            local_start_ms=234,
            local_end_ms=567,
            unaligned_global_start_ms=1034,
            unaligned_global_end_ms=1367,
            source="midi",
        )

        aligned = align_fragments([fragment], PhraseAlignment(target_anchor_ms=1000, detected_anchor_ms=1034))

        self.assertEqual(aligned[0].global_start_ms, 1000)
        self.assertEqual(aligned[0].global_end_ms, 1333)
        self.assertEqual(aligned[0].to_dict()["globalStartMs"], 1000)

    def test_matches_one_lyric_to_multiple_overlapping_notes(self) -> None:
        lyric = AlignedFragment(
            fragment_id="lyric_001",
            phrase_id="phrase_001",
            local_start_ms=100,
            local_end_ms=500,
            unaligned_global_start_ms=1100,
            unaligned_global_end_ms=1500,
            global_start_ms=1000,
            global_end_ms=1400,
            source="lyrics",
        )
        first_note = AlignedFragment(
            fragment_id="note_001",
            phrase_id="phrase_001",
            local_start_ms=100,
            local_end_ms=250,
            unaligned_global_start_ms=1100,
            unaligned_global_end_ms=1250,
            global_start_ms=1000,
            global_end_ms=1150,
            source="midi",
        )
        second_note = AlignedFragment(
            fragment_id="note_002",
            phrase_id="phrase_001",
            local_start_ms=260,
            local_end_ms=520,
            unaligned_global_start_ms=1260,
            unaligned_global_end_ms=1520,
            global_start_ms=1160,
            global_end_ms=1420,
            source="midi",
        )

        alignments = match_lyrics_to_notes([lyric], [second_note, first_note])

        self.assertEqual(len(alignments), 1)
        self.assertEqual(alignments[0].lyric_id, "lyric_001")
        self.assertEqual(alignments[0].note_ids, ["note_001", "note_002"])
        self.assertEqual(alignments[0].warnings, [])

    def test_matches_nearest_note_when_no_note_overlaps(self) -> None:
        lyric = AlignedFragment(
            fragment_id="lyric_001",
            phrase_id="phrase_001",
            local_start_ms=100,
            local_end_ms=200,
            unaligned_global_start_ms=1100,
            unaligned_global_end_ms=1200,
            global_start_ms=1000,
            global_end_ms=1100,
            source="lyrics",
        )
        note = AlignedFragment(
            fragment_id="note_001",
            phrase_id="phrase_001",
            local_start_ms=250,
            local_end_ms=350,
            unaligned_global_start_ms=1250,
            unaligned_global_end_ms=1350,
            global_start_ms=1150,
            global_end_ms=1250,
            source="midi",
        )

        alignments = match_lyrics_to_notes([lyric], [note], max_nearest_distance_ms=200)

        self.assertEqual(alignments[0].note_ids, ["note_001"])
        self.assertTrue(any("nearest note" in warning for warning in alignments[0].warnings))

    def test_skips_lyric_when_nearest_note_exceeds_threshold(self) -> None:
        lyric = AlignedFragment(
            fragment_id="lyric_001",
            phrase_id="phrase_001",
            local_start_ms=100,
            local_end_ms=200,
            unaligned_global_start_ms=1100,
            unaligned_global_end_ms=1200,
            global_start_ms=1000,
            global_end_ms=1100,
            source="lyrics",
        )
        note = AlignedFragment(
            fragment_id="note_001",
            phrase_id="phrase_001",
            local_start_ms=800,
            local_end_ms=900,
            unaligned_global_start_ms=1800,
            unaligned_global_end_ms=1900,
            global_start_ms=1800,
            global_end_ms=1900,
            source="midi",
        )

        self.assertEqual(match_lyrics_to_notes([lyric], [note], max_nearest_distance_ms=100), [])

    def test_lyric_note_alignment_round_trip_uses_contract_names(self) -> None:
        alignment = LyricNoteAlignment(
            alignment_id="align_001",
            lyric_id="lyric_001",
            note_ids=["note_001", "note_002"],
            warnings=["uncertain"],
        )
        data = alignment.to_dict()

        self.assertEqual(data["lyricId"], "lyric_001")
        self.assertEqual(data["noteIds"], ["note_001", "note_002"])
        self.assertEqual(LyricNoteAlignment.from_dict(data), alignment)


class StitchTimelineTests(unittest.TestCase):
    def test_stitches_fragments_by_global_time(self) -> None:
        phrase = PhraseSlice(
            phrase_id="phrase_001",
            index=0,
            phrase_start_ms=1000,
            phrase_end_ms=4200,
            slice_start_ms=800,
            slice_end_ms=4400,
        )
        later = AlignedFragment(
            fragment_id="note_002",
            phrase_id="phrase_001",
            local_start_ms=400,
            local_end_ms=600,
            unaligned_global_start_ms=1200,
            unaligned_global_end_ms=1400,
            global_start_ms=1166,
            global_end_ms=1366,
            source="midi",
        )
        earlier = AlignedFragment(
            fragment_id="note_001",
            phrase_id="phrase_001",
            local_start_ms=200,
            local_end_ms=300,
            unaligned_global_start_ms=1000,
            unaligned_global_end_ms=1100,
            global_start_ms=966,
            global_end_ms=1066,
            source="midi",
        )

        timeline = stitch_fragments([phrase], notes=[later, earlier])

        self.assertEqual([note.fragment_id for note in timeline.notes], ["note_001", "note_002"])
        self.assertEqual(timeline.warnings, [])

    def test_warns_for_unknown_fragment_phrase(self) -> None:
        phrase = PhraseSlice(
            phrase_id="phrase_001",
            index=0,
            phrase_start_ms=1000,
            phrase_end_ms=4200,
            slice_start_ms=800,
            slice_end_ms=4400,
        )
        fragment = AlignedFragment(
            fragment_id="note_001",
            phrase_id="missing_phrase",
            local_start_ms=200,
            local_end_ms=300,
            unaligned_global_start_ms=1000,
            unaligned_global_end_ms=1100,
            global_start_ms=966,
            global_end_ms=1066,
            source="midi",
        )

        timeline = stitch_fragments([phrase], notes=[fragment])

        self.assertTrue(any("unknown phrase" in warning for warning in timeline.warnings))


if __name__ == "__main__":
    unittest.main()
