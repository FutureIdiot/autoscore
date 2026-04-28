import unittest

from autoscore.core.artifacts import ArtifactRef


class ArtifactRefTests(unittest.TestCase):
    def test_round_trip_uses_contract_field_names(self) -> None:
        ref = ArtifactRef(
            artifact_id="artifact_phrase_001_wav",
            kind="audio/wav",
            relative_path="phrases/phrase_001.wav",
            sha256="abc123",
            size_bytes=42,
        )

        data = ref.to_dict()

        self.assertEqual(data["artifactId"], "artifact_phrase_001_wav")
        self.assertEqual(data["relativePath"], "phrases/phrase_001.wav")
        self.assertEqual(ArtifactRef.from_dict(data), ref)

    def test_rejects_absolute_relative_path(self) -> None:
        with self.assertRaises(ValueError):
            ArtifactRef(
                artifact_id="artifact_original_audio",
                kind="audio/wav",
                relative_path="D:\\input\\song.wav",
            )

    def test_requires_local_or_remote_location(self) -> None:
        with self.assertRaises(ValueError):
            ArtifactRef(artifact_id="artifact_missing", kind="audio/wav")


if __name__ == "__main__":
    unittest.main()
