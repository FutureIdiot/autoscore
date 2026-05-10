import json
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
            manifest.set_step_status(
                "estimateTempo",
                "succeeded",
                execution={"mode": "local", "transport": "in_process", "nodeId": "timeline-local"},
            )
            manifest.set_step_status(
                "separateAudio",
                "succeeded",
                execution={"mode": "local", "transport": "in_process", "nodeId": "audio-local"},
            )
            project_dir = workspace / "project_001"
            manifest.save(project_dir / "manifest.json")

            status = AutoscoreController(workspace).get_project_status("project_001")

        self.assertEqual(status.summary.project_id, "project_001")
        self.assertEqual(status.artifact_ids, ["artifact_original_audio"])
        self.assertEqual([step.task_type for step in status.steps], ["createProject", "separateAudio", "estimateTempo"])
        self.assertEqual(status.steps[0].status, "succeeded")
        self.assertEqual(status.steps[1].execution_node_id, "audio-local")
        self.assertEqual(status.steps[2].execution_node_id, "timeline-local")

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
                meter={"numerator": 3, "denominator": 4},
            )

            project_dir = workspace / "demo"
            loaded = ProjectManifest.load(project_dir / "manifest.json")
            copied_audio = (project_dir / "input" / "original_audio.wav").read_bytes()
            copied_lyrics = (project_dir / "input" / "lyrics.txt").read_text(encoding="utf-8")

        self.assertEqual(manifest.project_id, "demo")
        self.assertEqual(loaded.metadata["manual"]["globalTempo"], 120)
        self.assertEqual(loaded.metadata["manual"]["meter"], {"numerator": 3, "denominator": 4})
        self.assertIn("artifact_original_audio", loaded.artifacts)
        self.assertIn("artifact_lyrics_txt", loaded.artifacts)
        self.assertIn("artifact_manual_metadata_json", loaded.artifacts)
        self.assertEqual(loaded.steps["createProject"].status, "succeeded")
        self.assertEqual(copied_audio, b"audio")
        self.assertEqual(copied_lyrics, "hello world")

    def test_create_empty_project_writes_manifest_without_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            controller = AutoscoreController(workspace)

            manifest = controller.create_empty_project(project_id="empty")
            loaded = ProjectManifest.load(workspace / "empty" / "manifest.json")

        self.assertEqual(manifest.project_id, "empty")
        self.assertEqual(loaded.artifacts, {})
        self.assertEqual(loaded.steps["createProject"].status, "succeeded")
        self.assertEqual(loaded.steps["createProject"].output_artifact_ids, [])

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

    def test_run_step_separate_audio_creates_mock_stems(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(project_id="demo", audio_path=source_audio, lyrics_text="hello")

            result = controller.run_step("demo", "separateAudio")
            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")

            self.assertEqual(result.status, "succeeded")
            self.assertEqual(manifest.steps["separateAudio"].status, "succeeded")
            self.assertEqual(
                manifest.steps["separateAudio"].output_artifact_ids,
                ["artifact_vocals_wav", "artifact_accompaniment_wav"],
            )
            self.assertEqual((workspace / "demo" / "audio" / "vocals.wav").read_bytes(), b"audio")
            self.assertEqual((workspace / "demo" / "audio" / "accompaniment.wav").read_bytes(), b"audio")

    def test_run_step_rejects_unknown_task_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(project_id="demo", audio_path=source_audio, lyrics_text="hello")

            with self.assertRaises(NotImplementedError):
                controller.run_step("demo", "missingTask")

    def test_run_step_estimate_tempo_writes_manual_tempo_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(project_id="demo", audio_path=source_audio, lyrics_text="hello", global_tempo=132)

            result = controller.run_step("demo", "estimateTempo")
            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")
            tempo_data = json.loads((workspace / "demo" / "timeline" / "tempo.json").read_text(encoding="utf-8"))

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(manifest.steps["estimateTempo"].status, "succeeded")
        self.assertEqual(manifest.steps["estimateTempo"].output_artifact_ids, ["artifact_tempo_timeline_json"])
        self.assertIn("artifact_tempo_timeline_json", manifest.artifacts)
        self.assertEqual(tempo_data["globalTempo"], 132)
        self.assertEqual(tempo_data["source"], "manual")

    def test_run_step_estimate_tempo_defaults_when_manual_tempo_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(project_id="demo", audio_path=source_audio, lyrics_text="hello")

            controller.run_step("demo", "estimateTempo")
            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")
            tempo_data = json.loads((workspace / "demo" / "timeline" / "tempo.json").read_text(encoding="utf-8"))

        self.assertEqual(tempo_data["globalTempo"], 120)
        self.assertEqual(tempo_data["source"], "mock-default")
        self.assertTrue(any("mock tempo defaulted" in warning for warning in manifest.steps["estimateTempo"].warnings))

    def test_run_step_detect_phrases_writes_mock_phrase_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="first line\nsecond line\n",
                global_tempo=120,
                meter={"numerator": 4, "denominator": 4},
            )
            controller.run_step("demo", "separateAudio")
            controller.run_step("demo", "estimateTempo")

            result = controller.run_step("demo", "detectPhrases")
            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")
            phrase_data = json.loads((workspace / "demo" / "timeline" / "phrases.json").read_text(encoding="utf-8"))
            copied_phrase_audio = (workspace / "demo" / "phrases" / "phrase_001" / "vocals.wav").read_bytes()

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(manifest.steps["detectPhrases"].status, "succeeded")
        self.assertEqual(
            manifest.steps["detectPhrases"].output_artifact_ids,
            [
                "artifact_phrase_timeline_json",
                "artifact_phrase_001_vocals_wav",
                "artifact_phrase_002_vocals_wav",
            ],
        )
        self.assertEqual(phrase_data["source"], "mock-bar-window")
        self.assertEqual(phrase_data["meter"], {"numerator": 4, "denominator": 4})
        self.assertEqual(len(phrase_data["phrases"]), 2)
        self.assertEqual(phrase_data["phrases"][0]["phraseStartMs"], 0)
        self.assertEqual(phrase_data["phrases"][0]["phraseEndMs"], 16000)
        self.assertEqual(phrase_data["phrases"][0]["audioArtifact"]["artifactId"], "artifact_phrase_001_vocals_wav")
        self.assertEqual(copied_phrase_audio, b"audio")

    def test_project_status_reports_ready_tasks_by_available_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="line",
                global_tempo=120,
            )

            status = controller.get_project_status("demo")
            readiness = {task.task_type: task for task in status.task_readiness}

        self.assertTrue(readiness["separateAudio"].ready)
        self.assertTrue(readiness["estimateTempo"].ready)
        self.assertFalse(readiness["detectPhrases"].ready)
        self.assertEqual(readiness["detectPhrases"].missing_input_artifact_ids, ["artifact_vocals_wav"])
        self.assertEqual(readiness["detectPhrases"].missing_optional_artifact_ids, ["artifact_tempo_timeline_json"])
        self.assertEqual(readiness["detectPhrases"].node_id, "timeline-local")

    def test_estimate_tempo_runs_without_manual_metadata_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            manifest = controller.create_empty_project(project_id="demo")
            controller.attach_artifact(
                manifest.project_id,
                source_path=source_audio,
                artifact_id="artifact_original_audio",
                kind="audio/wav",
                relative_path="input/original_audio.wav",
            )

            result = controller.run_step("demo", "estimateTempo")
            loaded = ProjectManifest.load(workspace / "demo" / "manifest.json")

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(any(warning.code == "tempo.missing_metadata" for warning in result.warnings))
        self.assertTrue(any("tempo.missing_metadata" in warning for warning in loaded.steps["estimateTempo"].warnings))

    def test_detect_phrases_runs_without_optional_lyrics_or_metadata_with_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            vocals = Path(temp_dir) / "vocals.wav"
            vocals.write_bytes(b"vocals")
            controller = AutoscoreController(workspace)
            manifest = controller.create_empty_project(project_id="demo")
            controller.attach_artifact(
                manifest.project_id,
                source_path=vocals,
                artifact_id="artifact_vocals_wav",
                kind="audio/wav",
                relative_path="audio/vocals.wav",
            )
            controller.provide_tempo_timeline("demo", global_tempo=120)

            status = controller.get_project_status("demo")
            readiness = {task.task_type: task for task in status.task_readiness}
            result = controller.run_step("demo", "detectPhrases")
            loaded = ProjectManifest.load(workspace / "demo" / "manifest.json")

        self.assertTrue(readiness["detectPhrases"].ready)
        self.assertEqual(
            readiness["detectPhrases"].missing_optional_artifact_ids,
            ["artifact_lyrics_txt", "artifact_manual_metadata_json"],
        )
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(any(warning.code == "phrases.missing_lyrics" for warning in result.warnings))
        self.assertTrue(any(warning.code == "phrases.missing_metadata" for warning in result.warnings))
        self.assertTrue(any("phrases.missing_lyrics" in warning for warning in loaded.steps["detectPhrases"].warnings))

    def test_detect_phrases_runs_without_tempo_with_default_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            vocals = Path(temp_dir) / "vocals.wav"
            vocals.write_bytes(b"vocals")
            controller = AutoscoreController(workspace)
            manifest = controller.create_empty_project(project_id="demo")
            controller.attach_artifact(
                manifest.project_id,
                source_path=vocals,
                artifact_id="artifact_vocals_wav",
                kind="audio/wav",
                relative_path="audio/vocals.wav",
            )

            result = controller.run_step("demo", "detectPhrases")

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(any(warning.code == "phrases.missing_tempo" for warning in result.warnings))

    def test_detect_phrases_fails_when_required_vocals_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            controller = AutoscoreController(workspace)
            controller.create_empty_project(project_id="demo")

            with self.assertRaisesRegex(KeyError, "artifact_vocals_wav"):
                controller.run_step("demo", "detectPhrases")

    def test_activate_ready_tasks_runs_pipeline_until_no_ready_unfinished_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="line",
                global_tempo=120,
            )

            results = controller.activate_ready_tasks("demo")
            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")

        self.assertEqual([result.task_type for result in results], ["separateAudio", "estimateTempo", "detectPhrases"])
        self.assertEqual(manifest.steps["detectPhrases"].status, "succeeded")
        self.assertIn("artifact_phrase_timeline_json", manifest.artifacts)

    def test_send_to_task_without_task_runs_ready_pipeline_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="line",
                global_tempo=120,
            )

            results = controller.send_to_task("demo")

        self.assertEqual([result.task_type for result in results], ["separateAudio", "estimateTempo", "detectPhrases"])

    def test_send_to_task_runs_only_requested_task_without_continue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="line",
                global_tempo=120,
            )
            controller.run_step("demo", "separateAudio")

            results = controller.send_to_task("demo", task_type="estimateTempo")
            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")

        self.assertEqual([result.task_type for result in results], ["estimateTempo"])
        self.assertNotIn("detectPhrases", manifest.steps)

    def test_send_to_task_can_force_rerun_from_requested_task_and_continue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="line",
                global_tempo=120,
            )
            controller.activate_ready_tasks("demo")

            results = controller.send_to_task(
                "demo",
                task_type="detectPhrases",
                continue_pipeline=True,
                force=True,
            )

        self.assertEqual([result.task_type for result in results], ["detectPhrases"])

    def test_create_project_from_provided_vocals_can_run_detect_phrases_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            vocals = Path(temp_dir) / "vocals.wav"
            vocals.write_bytes(b"vocals")
            controller = AutoscoreController(workspace)

            controller.create_project_from_provided_vocals(
                project_id="direct",
                vocals_path=vocals,
                global_tempo=120,
                meter={"numerator": 4, "denominator": 4},
            )
            result = controller.run_step("direct", "detectPhrases")
            manifest = ProjectManifest.load(workspace / "direct" / "manifest.json")
            phrase_data = json.loads((workspace / "direct" / "timeline" / "phrases.json").read_text(encoding="utf-8"))

        self.assertEqual(result.status, "succeeded")
        self.assertIn("artifact_vocals_wav", manifest.artifacts)
        self.assertIn("artifact_tempo_timeline_json", manifest.artifacts)
        self.assertEqual(manifest.artifacts["artifact_vocals_wav"].metadata["providedAs"], "vocals")
        self.assertEqual(phrase_data["phrases"][0]["audioArtifact"]["artifactId"], "artifact_phrase_001_vocals_wav")

    def test_attach_artifact_allows_downstream_steps_to_use_provided_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            provided_vocals = Path(temp_dir) / "provided-vocals.wav"
            provided_vocals.write_bytes(b"provided")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="line",
                global_tempo=120,
            )
            controller.run_step("demo", "estimateTempo")

            controller.attach_artifact(
                "demo",
                source_path=provided_vocals,
                artifact_id="artifact_vocals_wav",
                kind="audio/wav",
                relative_path="audio/vocals.wav",
                metadata={"providedAs": "vocals"},
            )
            result = controller.run_step("demo", "detectPhrases")
            copied_vocals = (workspace / "demo" / "audio" / "vocals.wav").read_bytes()

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(copied_vocals, b"provided")

    def test_provide_tempo_timeline_allows_detect_phrases_with_vocals_and_manual_tempo(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspaces"
            source_audio = Path(temp_dir) / "song.wav"
            source_audio.write_bytes(b"audio")
            provided_vocals = Path(temp_dir) / "provided-vocals.wav"
            provided_vocals.write_bytes(b"provided")
            controller = AutoscoreController(workspace)
            controller.create_project(
                project_id="demo",
                audio_path=source_audio,
                lyrics_text="line",
                global_tempo=132,
            )
            controller.attach_artifact(
                "demo",
                source_path=provided_vocals,
                artifact_id="artifact_vocals_wav",
                kind="audio/wav",
                relative_path="audio/vocals.wav",
                metadata={"providedAs": "vocals"},
            )
            controller.provide_tempo_timeline("demo", global_tempo=132)

            result = controller.send_to_task("demo", task_type="detectPhrases")
            phrase_data = json.loads((workspace / "demo" / "timeline" / "phrases.json").read_text(encoding="utf-8"))

        self.assertEqual([item.task_type for item in result], ["detectPhrases"])
        self.assertEqual(phrase_data["barDurationMs"], 1818.1818181818182)

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
                    "--meter",
                    "6/8",
                ]
            )

            manifest = ProjectManifest.load(workspace / "demo" / "manifest.json")

        self.assertEqual(exit_code, 0)
        self.assertEqual(manifest.project_id, "demo")
        self.assertEqual(manifest.metadata["manual"]["meter"], {"numerator": 6, "denominator": 8})

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

    def test_create_projects_from_import_dir_accepts_manual_tempo_and_meter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            import_dir = root / "imports"
            import_dir.mkdir()
            (import_dir / "song.wav").write_bytes(b"audio")
            controller = AutoscoreController(
                root / "workspaces",
                app_config=AppConfig(import_dir=str(import_dir), default_tempo=120),
            )

            controller.create_projects_from_import_dir(
                default_tempo=132,
                meter={"numerator": 3, "denominator": 4},
            )
            manifest = ProjectManifest.load(root / "workspaces" / "song" / "manifest.json")

        self.assertEqual(manifest.metadata["manual"]["globalTempo"], 132)
        self.assertEqual(manifest.metadata["manual"]["meter"], {"numerator": 3, "denominator": 4})

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
