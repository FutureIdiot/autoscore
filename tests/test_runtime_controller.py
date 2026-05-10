import tempfile
import unittest
from pathlib import Path

from autoscore.cli.main import main
from autoscore.core.artifacts import ArtifactRef
from autoscore.core.projects import ProjectManifest
from autoscore.config import AppConfig
from autoscore.runtime import AutoscoreController, NodeRegistration, ProjectAlreadyProcessedError, project_id_from_name


def _write_audio(path: Path) -> Path:
    path.write_bytes(b"audio")
    return path


class AutoscoreControllerTests(unittest.TestCase):
    def test_lists_default_local_nodes(self) -> None:
        nodes = AutoscoreController().list_nodes()

        self.assertIn("timeline-local", {node.node_id for node in nodes})
        timeline_node = next(node for node in nodes if node.node_id == "timeline-local")
        self.assertIn("tempo-node", timeline_node.capabilities)
        self.assertIn("stitchPhrases", timeline_node.supported_tasks)
        self.assertEqual(timeline_node.transport, "local")

    def test_accepts_explicit_node_registry(self) -> None:
        controller = AutoscoreController(
            nodes=[
                NodeRegistration(
                    node_id="custom-node",
                    package_id="custom-package",
                    capabilities=("custom-node",),
                    supported_tasks=("customTask",),
                    transport="http",
                    endpoint="http://127.0.0.1:8710",
                )
            ]
        )

        self.assertEqual(controller.list_nodes()[0].node_id, "custom-node")

    def test_lists_projects_from_workspace_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            manifest = ProjectManifest(project_id="project_001", project_dir="workspaces/project_001")
            manifest.register_artifact(
                ArtifactRef(
                    artifact_id="artifact_original_audio",
                    kind="audio/wav",
                    relative_path="input/original_audio.wav",
                )
            )
            manifest.set_step_status("createProject", "succeeded", output_artifact_ids=["artifact_original_audio"])
            project_dir = workspace / "project_001"
            manifest.save(project_dir / "manifest.json")

            projects = AutoscoreController(workspace).list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].project_id, "project_001")
        self.assertEqual(projects[0].step_count, 1)
        self.assertEqual(projects[0].artifact_count, 1)

    def test_get_project_status_returns_steps_and_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            manifest = ProjectManifest(project_id="project_001", project_dir="workspaces/project_001")
            manifest.register_artifact(
                ArtifactRef(
                    artifact_id="artifact_original_audio",
                    kind="audio/wav",
                    relative_path="input/original_audio.wav",
                )
            )
            manifest.set_step_status("createProject", "succeeded", output_artifact_ids=["artifact_original_audio"])
            project_dir = workspace / "project_001"
            manifest.save(project_dir / "manifest.json")

            status = AutoscoreController(workspace).get_project_status("project_001")

        self.assertEqual(status.summary.project_id, "project_001")
        self.assertEqual(status.artifact_ids, ["artifact_original_audio"])
        self.assertEqual(status.steps[0].task_type, "createProject")
        self.assertEqual(status.steps[0].status, "succeeded")

    def test_create_project_imports_inputs_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)

            manifest = controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="hello world",
                global_tempo=120,
            )

            project_dir = workspace / "demo"
            loaded = ProjectManifest.load(project_dir / "manifest.json")
            copied_audio = (project_dir / "input" / "original_audio.wav").read_bytes()
            copied_lyrics = (project_dir / "input" / "lyrics.txt").read_text(encoding="utf-8")

        self.assertEqual(manifest.project_id, "demo")
        self.assertEqual(loaded.metadata["manual"]["globalTempo"], 120)
        self.assertIn("artifact_original_audio", loaded.artifacts)
        self.assertIn("artifact_lyrics_txt", loaded.artifacts)
        self.assertIn("artifact_manual_metadata_json", loaded.artifacts)
        self.assertEqual(loaded.steps["createProject"].status, "succeeded")
        self.assertEqual(copied_audio, b"audio")
        self.assertEqual(copied_lyrics, "hello world")

    def test_uses_configured_workspace_when_not_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "configured-workspaces"
            controller = AutoscoreController(app_config=AppConfig(workspace_root=str(workspace)))

            controller.create_project(
                project_id="demo",
                audio_path=_write_audio(Path(temp_dir) / "song.wav"),
                lyrics_text="hello",
            )

            self.assertTrue((workspace / "demo" / "manifest.json").exists())

    def test_create_project_rejects_existing_manifest_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(project_id="demo", audio_path=source_audio, lyrics_text="hello")

            with self.assertRaises(FileExistsError):
                controller.create_project(project_id="demo", audio_path=source_audio, lyrics_text="hello")

    def test_cli_create_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")

            exit_code = main(
                [
                    "--workspace",
                    str(workspace),
                    "create",
                    "--project-id",
                    "demo",
                    "--audio",
                    str(source_audio),
                    "--lyrics",
                    "hello",
                    "--tempo",
                    "120",
                ]
            )

            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")

        self.assertEqual(exit_code, 0)
        self.assertEqual(manifest.project_id, "demo")

    def test_create_projects_from_configured_import_dir(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            import_dir = root / "imports"
            import_dir.mkdir()
            (import_dir / "Song A.wav").write_bytes(b"audio-a")
            (import_dir / "Song A.txt").write_text("lyrics a", encoding="utf-8")
            (import_dir / "Song B.flac").write_bytes(b"audio-b")
            controller = AutoscoreController(
                root / "workspaces",
                app_config=AppConfig(import_dir=str(import_dir), default_tempo=120),
            )

            results = controller.create_projects_from_import_dir()
            status = controller.get_project_status("Song_A")

            self.assertEqual([result.status for result in results], ["created", "created"])
            self.assertEqual(status.summary.project_id, "Song_A")
            self.assertEqual(status.summary.artifact_count, 3)
            self.assertFalse((import_dir / "Song A.wav").exists())
            self.assertFalse((import_dir / "Song A.txt").exists())
            self.assertFalse((import_dir / "Song B.flac").exists())

    def test_create_projects_from_import_dir_rejects_already_processed_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            import_dir = root / "imports"
            import_dir.mkdir()
            audio = import_dir / "song.wav"
            audio.write_bytes(b"audio")
            controller = AutoscoreController(
                root / "workspaces",
                app_config=AppConfig(import_dir=str(import_dir)),
            )
            controller.create_projects_from_import_dir()
            audio.write_bytes(b"audio")

            with self.assertRaises(ProjectAlreadyProcessedError):
                controller.create_projects_from_import_dir()

    def test_create_projects_from_import_dir_force_overwrites_existing_project(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            import_dir = root / "imports"
            import_dir.mkdir()
            audio = import_dir / "song.wav"
            audio.write_bytes(b"audio")
            controller = AutoscoreController(
                root / "workspaces",
                app_config=AppConfig(import_dir=str(import_dir)),
            )
            controller.create_projects_from_import_dir()
            audio.write_bytes(b"new-audio")

            results = controller.create_projects_from_import_dir(overwrite=True)
            copied_audio = (root / "workspaces" / "song" / "input" / "original_audio.wav").read_bytes()

        self.assertEqual(results[0].status, "created")
        self.assertEqual(copied_audio, b"new-audio")

    def test_project_id_from_name_sanitizes_file_stem(self) -> None:
        self.assertEqual(project_id_from_name("Song A 01"), "Song_A_01")
        with self.assertRaises(ValueError):
            project_id_from_name("...")


if __name__ == "__main__":
    unittest.main()
