import tempfile
import unittest
from pathlib import Path

from autoscore.core.artifacts import (
    ArtifactRef,
    LocalArtifactStore,
    artifact_id_from_path,
    default_extension_for_kind,
    file_sha256,
)


class LocalArtifactStoreTests(unittest.TestCase):
    def test_import_file_copies_into_project_and_records_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.wav"
            source.write_bytes(b"demo audio")
            project_dir = root / "project_001"
            store = LocalArtifactStore(project_dir)

            ref = store.import_file(
                source,
                kind="audio/wav",
                relative_path="input/original_audio.wav",
            )

            target = project_dir / "input" / "original_audio.wav"
            self.assertEqual(target.read_bytes(), b"demo audio")
            self.assertEqual(ref.artifact_id, "artifact_input_original_audio_audio_wav")
            self.assertEqual(ref.relative_path, "input/original_audio.wav")
            self.assertEqual(ref.sha256, file_sha256(target))
            self.assertEqual(ref.size_bytes, len(b"demo audio"))

    def test_create_ref_for_existing_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "project_001"
            path = project_dir / "phrases" / "phrase_001.wav"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"phrase")
            store = LocalArtifactStore(project_dir)

            ref = store.create_ref(
                artifact_id="artifact_phrase_001_wav",
                kind="audio/wav",
                relative_path="phrases/phrase_001.wav",
            )

            self.assertEqual(ref.sha256, file_sha256(path))
            self.assertEqual(store.materialize(ref), path)

    def test_materialize_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "project_001"
            path = project_dir / "audio" / "vocals.wav"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"vocals")
            store = LocalArtifactStore(project_dir)
            ref = ArtifactRef(
                artifact_id="artifact_vocals_wav",
                kind="audio/wav",
                relative_path="audio/vocals.wav",
                sha256="not-a-real-hash",
            )

            with self.assertRaises(ValueError):
                store.materialize(ref)

    def test_rejects_path_traversal(self) -> None:
        store = LocalArtifactStore("workspaces/project_001")

        with self.assertRaises(ValueError):
            store.resolve_relative_path("../outside.wav")

    def test_artifact_id_generation_and_kind_extension(self) -> None:
        self.assertEqual(
            artifact_id_from_path("score/aligned_score.json", kind="application/json"),
            "artifact_score_aligned_score_application_json",
        )
        self.assertEqual(default_extension_for_kind("audio/wav"), ".wav")
        self.assertIsNone(default_extension_for_kind("application/octet-stream"))


if __name__ == "__main__":
    unittest.main()
