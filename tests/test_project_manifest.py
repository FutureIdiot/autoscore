import json
import tempfile
import unittest
from pathlib import Path

from autoscore.core.artifacts import ArtifactRef
from autoscore.core.projects import ManifestStep, ProjectManifest


class ProjectManifestTests(unittest.TestCase):
    def test_registers_artifacts_and_steps(self) -> None:
        manifest = ProjectManifest(project_id="project_001", project_dir="workspaces/project_001")
        artifact = ArtifactRef(
            artifact_id="artifact_original_audio",
            kind="audio/wav",
            relative_path="input/original_audio.wav",
        )

        manifest.register_artifact(artifact)
        step = manifest.set_step_status(
            "createProject",
            "succeeded",
            output_artifact_ids=["artifact_original_audio"],
        )

        self.assertEqual(manifest.get_artifact("artifact_original_audio"), artifact)
        self.assertEqual(step.status, "succeeded")
        self.assertEqual(step.output_artifact_ids, ["artifact_original_audio"])

    def test_json_save_and_load_round_trip(self) -> None:
        manifest = ProjectManifest(
            project_id="project_001",
            project_dir="workspaces/project_001",
            metadata={"title": "demo"},
        )
        manifest.register_artifact(
            ArtifactRef(
                artifact_id="artifact_vocals_wav",
                kind="audio/wav",
                relative_path="audio/vocals.wav",
            )
        )
        manifest.set_step(
            ManifestStep(
                task_type="separateAudio",
                status="ready",
                input_artifact_ids=["artifact_original_audio"],
            )
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "manifest.json"
            manifest.save(path)
            loaded = ProjectManifest.load(path)

        self.assertEqual(loaded.project_id, manifest.project_id)
        self.assertEqual(loaded.project_dir, str(path.parent))
        self.assertEqual(loaded.metadata, {"title": "demo"})
        self.assertIn("artifact_vocals_wav", loaded.artifacts)
        self.assertEqual(loaded.steps["separateAudio"].status, "ready")

    def test_rejects_invalid_task_state(self) -> None:
        manifest = ProjectManifest(project_id="project_001", project_dir="workspaces/project_001")

        with self.assertRaises(ValueError):
            manifest.set_step_status("analyzeMidi", "done")

    def test_rejects_camel_case_step_update_arguments(self) -> None:
        manifest = ProjectManifest(project_id="project_001", project_dir="workspaces/project_001")

        with self.assertRaises(TypeError):
            manifest.set_step_status(
                "createProject",
                "succeeded",
                outputArtifactIds=["artifact_original_audio"],  # type: ignore[call-arg]
            )

    def test_schema_version_mismatch_records_warning(self) -> None:
        manifest = ProjectManifest(
            project_id="project_001",
            project_dir="workspaces/project_001",
            schema_version=999,
        )

        self.assertEqual(manifest.schema_version, 999)
        self.assertTrue(any("schemaVersion 999 differs" in warning for warning in manifest.warnings))

    def test_load_migrates_manifest_dict_before_construction(self) -> None:
        manifest = ProjectManifest.from_dict(
            {
                "schemaVersion": 999,
                "projectId": "project_001",
                "projectDir": "workspaces/project_001",
                "warnings": ["existing warning"],
            }
        )

        self.assertIn("existing warning", manifest.warnings)
        self.assertTrue(any("no automatic migration" in warning for warning in manifest.warnings))

    def test_load_uses_manifest_file_location_for_project_dir(self) -> None:
        manifest_data = {
            "schemaVersion": 1,
            "projectId": "project_001",
            "projectDir": "/old/location/project_001",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "project_001" / "manifest.json"
            path.parent.mkdir()
            path.write_text(json.dumps(manifest_data), encoding="utf-8")
            loaded = ProjectManifest.load(path)

        self.assertEqual(loaded.project_dir, str(path.parent))


if __name__ == "__main__":
    unittest.main()
