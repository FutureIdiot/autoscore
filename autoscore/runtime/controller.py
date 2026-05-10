"""Controller API shared by CLI, TUI, and future WebUI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from autoscore.config import AppConfig, load_app_config
from autoscore.core.artifacts import LocalArtifactStore
from autoscore.core.projects import ProjectManifest
from autoscore.runtime.registry import NodeRegistration, default_local_nodes
from autoscore.runtime.runners import (
    build_task_envelope,
    get_local_runner,
    implemented_task_types,
    optional_input_artifact_ids_for_task,
    required_input_artifact_ids_for_task,
)
from autoscore.runtime.tasks import TaskResult

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_PIPELINE_TASK_ORDER = (
    "createProject",
    "separateAudio",
    "estimateTempo",
    "detectPhrases",
    "runGame",
    "runLyricFA",
    "alignPhrase",
    "stitchPhrases",
    "buildScoreJson",
)


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """Small project listing item."""

    project_id: str
    project_dir: str
    manifest_path: str
    step_count: int
    artifact_count: int
    warning_count: int
    error_count: int


@dataclass(frozen=True, slots=True)
class StepStatus:
    """Display-friendly manifest step status."""

    task_type: str
    status: str
    input_artifact_count: int = 0
    output_artifact_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    updated_at: str = ""
    execution_node_id: str = ""
    execution_transport: str = ""


@dataclass(frozen=True, slots=True)
class ProjectStatus:
    """Project status snapshot for UI consumers."""

    summary: ProjectSummary
    steps: list[StepStatus] = field(default_factory=list)
    task_readiness: list["TaskReadiness"] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectCreateResult:
    """Result for one batch project creation candidate."""

    project_id: str
    audio_path: str
    status: str
    message: str = ""


@dataclass(frozen=True, slots=True)
class TaskReadiness:
    """Whether one task can be activated from current project artifacts."""

    task_type: str
    node_id: str
    ready: bool
    status: str = "pending"
    input_artifact_ids: list[str] = field(default_factory=list)
    missing_input_artifact_ids: list[str] = field(default_factory=list)
    optional_input_artifact_ids: list[str] = field(default_factory=list)
    missing_optional_artifact_ids: list[str] = field(default_factory=list)


class ProjectAlreadyProcessedError(FileExistsError):
    """Raised when an import candidate maps to an existing project manifest."""


class AutoscoreController:
    """Stable control surface for UI layers."""

    def __init__(
        self,
        workspace_root: str | Path | None = None,
        nodes: list[NodeRegistration] | None = None,
        app_config: AppConfig | None = None,
    ) -> None:
        self._nodes = nodes if nodes is not None else default_local_nodes()
        self.app_config = app_config if app_config is not None else load_app_config()
        self.workspace_root = Path(workspace_root if workspace_root is not None else self.app_config.workspace_root)

    def list_projects(self) -> list[ProjectSummary]:
        manifests = sorted(self.workspace_root.glob("*/manifest.json"))
        return [self._summary_from_manifest(ProjectManifest.load(path), path) for path in manifests]

    def list_nodes(self) -> list[NodeRegistration]:
        return sorted(self._nodes, key=lambda node: node.node_id)

    def create_empty_project(
        self,
        *,
        project_id: str,
        overwrite: bool = False,
    ) -> ProjectManifest:
        """Create a project workspace without input artifacts yet."""

        self._validate_project_id(project_id)
        project_dir = self.workspace_root / project_id
        manifest_path = project_dir / "manifest.json"
        if manifest_path.exists() and not overwrite:
            raise FileExistsError(manifest_path)

        project_dir.mkdir(parents=True, exist_ok=True)
        manifest = ProjectManifest(project_id=project_id, project_dir=str(project_dir))
        manifest.set_step_status("createProject", "succeeded", output_artifact_ids=[])
        manifest.save(manifest_path)
        return manifest

    def create_project(
        self,
        *,
        project_id: str,
        audio_path: str | Path,
        lyrics_text: str | None = None,
        lyrics_path: str | Path | None = None,
        global_tempo: float | None = None,
        meter: dict[str, object] | None = None,
        key: dict[str, object] | None = None,
        overwrite: bool = False,
    ) -> ProjectManifest:
        """Create a project workspace and manifest from user inputs."""

        self._validate_project_id(project_id)
        if lyrics_text is None and lyrics_path is None:
            raise ValueError("lyrics_text or lyrics_path is required")

        project_dir = self.workspace_root / project_id
        manifest_path = project_dir / "manifest.json"
        if manifest_path.exists() and not overwrite:
            raise FileExistsError(manifest_path)

        project_dir.mkdir(parents=True, exist_ok=True)
        store = LocalArtifactStore(project_dir)
        manifest = ProjectManifest(project_id=project_id, project_dir=str(project_dir))

        audio_ref = store.import_file(
            audio_path,
            kind="audio/wav",
            relative_path="input/original_audio.wav",
            artifact_id="artifact_original_audio",
        )
        manifest.register_artifact(audio_ref)

        lyrics_ref = self._write_lyrics_artifact(store, lyrics_text=lyrics_text, lyrics_path=lyrics_path)
        manifest.register_artifact(lyrics_ref)

        metadata_ref = self._write_manual_metadata_artifact(
            store,
            global_tempo=global_tempo,
            meter=meter,
            key=key,
        )
        manifest.register_artifact(metadata_ref)
        manifest.metadata["manual"] = {
            "globalTempo": global_tempo,
            "meter": meter or {},
            "key": key or {},
        }
        manifest.set_step_status(
            "createProject",
            "succeeded",
            output_artifact_ids=[
                audio_ref.artifact_id,
                lyrics_ref.artifact_id,
                metadata_ref.artifact_id,
            ],
        )
        manifest.save(manifest_path)
        return manifest

    def create_projects_from_import_dir(
        self,
        *,
        import_dir: str | Path | None = None,
        default_tempo: float | None = None,
        meter: dict[str, object] | None = None,
        overwrite: bool = False,
        fail_on_processed: bool = True,
    ) -> list[ProjectCreateResult]:
        """Create projects for audio files in the configured import directory."""

        selected_import_dir = Path(import_dir or self.app_config.import_dir or "")
        if not str(selected_import_dir):
            raise ValueError("import directory is not configured")
        if not selected_import_dir.is_dir():
            raise FileNotFoundError(selected_import_dir)

        tempo = default_tempo if default_tempo is not None else self.app_config.default_tempo
        audio_extensions = {extension.lower() for extension in self.app_config.audio_extensions}
        audio_files = sorted(
            path for path in selected_import_dir.iterdir() if path.is_file() and path.suffix.lower() in audio_extensions
        )
        results: list[ProjectCreateResult] = []
        for audio_file in audio_files:
            project_id = project_id_from_name(audio_file.stem)
            lyrics_path = audio_file.with_suffix(".txt")
            manifest_path = self._manifest_path(project_id)
            if manifest_path.exists() and not overwrite:
                message = f"project {project_id!r} has already been processed: {manifest_path}"
                if fail_on_processed:
                    raise ProjectAlreadyProcessedError(message)
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=str(audio_file),
                        status="failed",
                        message=message,
                    )
                )
                continue
            try:
                self.create_project(
                    project_id=project_id,
                    audio_path=audio_file,
                    lyrics_path=lyrics_path if lyrics_path.exists() else None,
                    lyrics_text="" if not lyrics_path.exists() else None,
                    global_tempo=tempo,
                    meter=meter,
                    overwrite=overwrite,
                )
            except FileExistsError:
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=str(audio_file),
                        status="skipped",
                        message="project already exists",
                    )
                )
            except Exception as exc:
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=str(audio_file),
                        status="failed",
                        message=str(exc),
                    )
                )
            else:
                audio_file.unlink()
                if lyrics_path.exists():
                    lyrics_path.unlink()
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=str(audio_file),
                        status="created",
                    )
                )
        return results

    def create_project_from_provided_vocals(
        self,
        *,
        project_id: str,
        vocals_path: str | Path,
        lyrics_text: str = "",
        global_tempo: float | None = None,
        meter: dict[str, object] | None = None,
        overwrite: bool = False,
    ) -> ProjectManifest:
        """Create a project that starts from a user-provided vocals artifact."""

        self._validate_project_id(project_id)
        project_dir = self.workspace_root / project_id
        manifest_path = project_dir / "manifest.json"
        if manifest_path.exists() and not overwrite:
            raise FileExistsError(manifest_path)

        project_dir.mkdir(parents=True, exist_ok=True)
        store = LocalArtifactStore(project_dir)
        manifest = ProjectManifest(project_id=project_id, project_dir=str(project_dir))

        vocals_ref = store.import_file(
            vocals_path,
            kind="audio/wav",
            relative_path="audio/vocals.wav",
            artifact_id="artifact_vocals_wav",
            metadata={"provided": True, "providedAs": "vocals"},
        )
        manifest.register_artifact(vocals_ref)

        lyrics_ref = self._write_lyrics_artifact(store, lyrics_text=lyrics_text, lyrics_path=None)
        manifest.register_artifact(lyrics_ref)

        metadata_ref = self._write_manual_metadata_artifact(
            store,
            global_tempo=global_tempo,
            meter=meter,
            key=None,
        )
        manifest.register_artifact(metadata_ref)

        tempo_ref = self._write_provided_tempo_artifact(
            store,
            global_tempo=global_tempo,
        )
        manifest.register_artifact(tempo_ref)
        manifest.metadata["manual"] = {
            "globalTempo": global_tempo,
            "meter": meter or {},
            "key": {},
        }
        manifest.set_step_status(
            "createProject",
            "succeeded",
            output_artifact_ids=[
                vocals_ref.artifact_id,
                lyrics_ref.artifact_id,
                metadata_ref.artifact_id,
                tempo_ref.artifact_id,
            ],
        )
        manifest.save(manifest_path)
        return manifest

    def attach_artifact(
        self,
        project_id: str,
        *,
        source_path: str | Path,
        artifact_id: str,
        kind: str,
        relative_path: str,
        metadata: dict[str, object] | None = None,
    ) -> ProjectManifest:
        """Attach a user-provided artifact so a downstream task can run directly."""

        manifest_path = self._manifest_path(project_id)
        manifest = ProjectManifest.load(manifest_path)
        store = LocalArtifactStore(manifest.project_dir)
        artifact = store.import_file(
            source_path,
            kind=kind,
            relative_path=relative_path,
            artifact_id=artifact_id,
            metadata={"provided": True, **dict(metadata or {})},
        )
        manifest.register_artifact(artifact)
        manifest.save(manifest_path)
        return manifest

    def provide_tempo_timeline(
        self,
        project_id: str,
        *,
        global_tempo: float | None = None,
    ) -> ProjectManifest:
        """Provide a tempo timeline artifact without running tempo estimation."""

        manifest_path = self._manifest_path(project_id)
        manifest = ProjectManifest.load(manifest_path)
        store = LocalArtifactStore(manifest.project_dir)
        artifact = self._write_provided_tempo_artifact(store, global_tempo=global_tempo)
        manifest.register_artifact(artifact)
        manifest.save(manifest_path)
        return manifest

    def load_manifest(self, project_id: str) -> ProjectManifest:
        return ProjectManifest.load(self._manifest_path(project_id))

    def get_project_status(self, project_id: str) -> ProjectStatus:
        manifest_path = self._manifest_path(project_id)
        manifest = ProjectManifest.load(manifest_path)
        summary = self._summary_from_manifest(manifest, manifest_path)
        steps = [
            StepStatus(
                task_type=step.task_type,
                status=step.status,
                input_artifact_count=len(step.input_artifact_ids),
                output_artifact_count=len(step.output_artifact_ids),
                warning_count=len(step.warnings),
                error_count=len(step.errors),
                updated_at=step.updated_at,
                execution_node_id=str(step.execution.get("nodeId", "")),
                execution_transport=str(step.execution.get("transport", "")),
            )
            for step in sorted(manifest.steps.values(), key=_pipeline_step_sort_key)
        ]
        return ProjectStatus(
            summary=summary,
            steps=steps,
            task_readiness=self._task_readiness(manifest),
            artifact_ids=sorted(manifest.artifacts),
            warnings=list(manifest.warnings),
            errors=list(manifest.errors),
        )

    def list_ready_tasks(self, project_id: str) -> list[TaskReadiness]:
        """Return runnable tasks whose required input artifacts exist."""

        manifest = ProjectManifest.load(self._manifest_path(project_id))
        return [task for task in self._task_readiness(manifest) if task.ready]

    def activate_ready_tasks(self, project_id: str) -> list[TaskResult]:
        """Run every currently ready, unfinished task until no new task is ready."""

        results: list[TaskResult] = []
        while True:
            manifest = ProjectManifest.load(self._manifest_path(project_id))
            ready_tasks = [
                task
                for task in self._task_readiness(manifest)
                if task.ready and task.status not in {"running", "succeeded"}
            ]
            if not ready_tasks:
                return results
            result = self.run_step(project_id, ready_tasks[0].task_type)
            results.append(result)

    def send_to_task(
        self,
        project_id: str,
        *,
        task_type: str | None = None,
        continue_pipeline: bool = False,
        force: bool = False,
    ) -> list[TaskResult]:
        """Send current project artifacts to one task or a downstream task chain."""

        if task_type is None:
            return self._run_ready_chain(project_id, start_task_type=None, force=force)
        if not continue_pipeline:
            return [self.run_step(project_id, task_type)]
        return self._run_ready_chain(project_id, start_task_type=task_type, force=force)

    def run_step(self, project_id: str, task_type: str) -> TaskResult:
        """Run one project step and persist manifest changes."""

        manifest_path = self._manifest_path(project_id)
        manifest = ProjectManifest.load(manifest_path)
        store = LocalArtifactStore(manifest.project_dir)
        required_input_artifact_ids = required_input_artifact_ids_for_task(task_type)
        optional_input_artifact_ids = optional_input_artifact_ids_for_task(task_type)
        missing_required_artifact_ids = [
            artifact_id for artifact_id in required_input_artifact_ids if artifact_id not in manifest.artifacts
        ]
        if missing_required_artifact_ids:
            missing = ", ".join(missing_required_artifact_ids)
            raise KeyError(f"missing required input artifact(s) for {task_type}: {missing}")
        input_artifact_ids = [
            artifact_id
            for artifact_id in [*required_input_artifact_ids, *optional_input_artifact_ids]
            if artifact_id in manifest.artifacts
        ]
        input_artifacts = [manifest.get_artifact(artifact_id) for artifact_id in input_artifact_ids]
        runner = get_local_runner(task_type)
        envelope = build_task_envelope(
            project_id=manifest.project_id,
            task_type=task_type,
            input_artifacts=input_artifacts,
        )

        manifest.set_step_status(
            task_type,
            "running",
            input_artifact_ids=input_artifact_ids,
            output_artifact_ids=[],
            warnings=[],
            errors=[],
            execution=envelope.execution.to_dict(),
        )
        manifest.save(manifest_path)

        result = runner(envelope, store)
        for artifact in result.output_artifacts:
            manifest.register_artifact(artifact)
        manifest.set_step_status(
            task_type,
            result.status,
            input_artifact_ids=input_artifact_ids,
            output_artifact_ids=[artifact.artifact_id for artifact in result.output_artifacts],
            warnings=[_problem_to_message(warning) for warning in result.warnings],
            errors=[_problem_to_message(error) for error in result.errors],
            execution=result.execution.to_dict(),
        )
        manifest.save(manifest_path)
        return result

    def _manifest_path(self, project_id: str) -> Path:
        if not project_id:
            raise ValueError("project_id is required")
        return self.workspace_root / project_id / "manifest.json"

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not project_id:
            raise ValueError("project_id is required")
        if not _PROJECT_ID_PATTERN.fullmatch(project_id):
            raise ValueError("project_id may only contain letters, numbers, underscore, dash, and dot")

    @staticmethod
    def _write_lyrics_artifact(
        store: LocalArtifactStore,
        *,
        lyrics_text: str | None,
        lyrics_path: str | Path | None,
    ):
        target = store.resolve_relative_path("input/lyrics.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        if lyrics_path is not None:
            target.write_text(Path(lyrics_path).read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        else:
            target.write_text(lyrics_text or "", encoding="utf-8", newline="\n")
        return store.create_ref(
            artifact_id="artifact_lyrics_txt",
            kind="text/plain",
            relative_path="input/lyrics.txt",
        )

    @staticmethod
    def _write_manual_metadata_artifact(
        store: LocalArtifactStore,
        *,
        global_tempo: float | None,
        meter: dict[str, object] | None,
        key: dict[str, object] | None,
    ):
        target = store.resolve_relative_path("input/manual_metadata.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "globalTempo": global_tempo,
            "meter": meter or {},
            "key": key or {},
        }
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return store.create_ref(
            artifact_id="artifact_manual_metadata_json",
            kind="application/json",
            relative_path="input/manual_metadata.json",
        )

    @staticmethod
    def _write_provided_tempo_artifact(
        store: LocalArtifactStore,
        *,
        global_tempo: float | None,
    ):
        target = store.resolve_relative_path("timeline/tempo.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        tempo = {
            "globalTempo": float(global_tempo if global_tempo is not None else 120),
            "source": "manual" if global_tempo is not None else "mock-default",
            "gridOffsetMs": 0,
            "timebase": 480,
            "candidates": [
                {
                    "bpm": float(global_tempo if global_tempo is not None else 120),
                    "source": "manual" if global_tempo is not None else "mock-default",
                    "confidence": 1.0 if global_tempo is not None else 0.25,
                    "warning": None,
                }
            ],
            "warnings": [] if global_tempo is not None else ["manual tempo was not provided; mock tempo defaulted to 120 BPM"],
        }
        target.write_text(json.dumps(tempo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return store.create_ref(
            artifact_id="artifact_tempo_timeline_json",
            kind="application/json",
            relative_path="timeline/tempo.json",
            metadata={"provided": True, "source": tempo["source"]},
        )

    @staticmethod
    def _summary_from_manifest(manifest: ProjectManifest, manifest_path: Path) -> ProjectSummary:
        return ProjectSummary(
            project_id=manifest.project_id,
            project_dir=manifest.project_dir,
            manifest_path=str(manifest_path),
            step_count=len(manifest.steps),
            artifact_count=len(manifest.artifacts),
            warning_count=len(manifest.warnings),
            error_count=len(manifest.errors),
        )

    @staticmethod
    def _task_readiness(manifest: ProjectManifest) -> list[TaskReadiness]:
        readiness = []
        for task_type in sorted(implemented_task_types(), key=_task_type_sort_key):
            input_artifact_ids = required_input_artifact_ids_for_task(task_type)
            optional_input_artifact_ids = optional_input_artifact_ids_for_task(task_type)
            missing_input_artifact_ids = [
                artifact_id for artifact_id in input_artifact_ids if artifact_id not in manifest.artifacts
            ]
            missing_optional_artifact_ids = [
                artifact_id for artifact_id in optional_input_artifact_ids if artifact_id not in manifest.artifacts
            ]
            step = manifest.steps.get(task_type)
            readiness.append(
                TaskReadiness(
                    task_type=task_type,
                    node_id=_node_id_from_execution_or_task(step.execution if step else {}, task_type),
                    ready=not missing_input_artifact_ids,
                    status=step.status if step else "pending",
                    input_artifact_ids=input_artifact_ids,
                    missing_input_artifact_ids=missing_input_artifact_ids,
                    optional_input_artifact_ids=optional_input_artifact_ids,
                    missing_optional_artifact_ids=missing_optional_artifact_ids,
                )
            )
        return readiness

    def _run_ready_chain(
        self,
        project_id: str,
        *,
        start_task_type: str | None,
        force: bool,
    ) -> list[TaskResult]:
        results: list[TaskResult] = []
        ran_task_types: set[str] = set()
        start_index = 0 if start_task_type is None else _task_type_sort_key(start_task_type)[0]
        while True:
            manifest = ProjectManifest.load(self._manifest_path(project_id))
            ready_tasks = [
                task
                for task in self._task_readiness(manifest)
                if task.ready
                and _task_type_sort_key(task.task_type)[0] >= start_index
                and task.task_type not in ran_task_types
                and (force or task.status not in {"running", "succeeded"})
            ]
            if not ready_tasks:
                return results
            selected = None
            for task in ready_tasks:
                if start_task_type is not None and not results and task.task_type == start_task_type:
                    selected = task
                    break
                if start_task_type is None or results:
                    selected = task
                    break
            if selected is None:
                return results
            result = self.run_step(project_id, selected.task_type)
            ran_task_types.add(selected.task_type)
            results.append(result)


def project_id_from_name(name: str) -> str:
    project_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._-")
    if not project_id:
        raise ValueError("name does not contain a usable project id")
    return project_id


def _problem_to_message(problem: object) -> str:
    code = getattr(problem, "code", "")
    message = getattr(problem, "message", str(problem))
    return f"{code}: {message}" if code else message


def _pipeline_step_sort_key(step: object) -> tuple[int, str]:
    task_type = getattr(step, "task_type", "")
    return _task_type_sort_key(task_type)


def _task_type_sort_key(task_type: str) -> tuple[int, str]:
    try:
        return (_PIPELINE_TASK_ORDER.index(task_type), task_type)
    except ValueError:
        return (len(_PIPELINE_TASK_ORDER), task_type)


def _node_id_from_execution_or_task(execution: dict[str, object], task_type: str) -> str:
    node_id = execution.get("nodeId")
    if node_id:
        return str(node_id)
    if task_type == "separateAudio":
        return "audio-local"
    if task_type in {"estimateTempo", "detectPhrases", "alignPhrase", "stitchPhrases"}:
        return "timeline-local"
    if task_type == "runGame":
        return "midi-local"
    if task_type == "runLyricFA":
        return "lyric-local"
    if task_type == "buildScoreJson":
        return "score-export-local"
    return "local"
