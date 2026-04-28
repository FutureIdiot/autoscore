import unittest

from autoscore.core.artifacts import ArtifactRef
from autoscore.packages.timeline import (
    AlignedFragment,
    PhraseAlignment,
    PhraseSlice,
    TempoCandidate,
    TempoTimeline,
    TimedFragment,
    align_fragments,
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
            source="game",
        )

        aligned = align_fragments([fragment], PhraseAlignment(target_anchor_ms=1000, detected_anchor_ms=1034))

        self.assertEqual(aligned[0].global_start_ms, 1000)
        self.assertEqual(aligned[0].global_end_ms, 1333)
        self.assertEqual(aligned[0].to_dict()["globalStartMs"], 1000)


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
            source="game",
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
            source="game",
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
            source="game",
        )

        timeline = stitch_fragments([phrase], notes=[fragment])

        self.assertTrue(any("unknown phrase" in warning for warning in timeline.warnings))


if __name__ == "__main__":
    unittest.main()
