"""Controller API shared by CLI, TUI, and future WebUI."""

from __future__ import annotations

import json
import re
import shutil
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
    node_id_for_task,
    optional_input_artifact_ids_for_task,
    output_artifact_ids_for_task,
    required_input_artifact_ids_for_task,
)
from autoscore.runtime.tasks import TaskResult

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_PIPELINE_TASK_ORDER = (
    "createProject",
    "separateAudio",
    "estimateTempo",
    "detectPhrases",
    "analyzeMidi",
    "analyzeLyrics",
    "alignPhrase",
    "stitchPhrases",
    "buildScoreJson",
)
_PENDING_INPUTS_METADATA_KEY = "pendingInputs"
_MIDI_INPUT_EXTENSIONS = {".mid", ".midi"}


@dataclass(frozen=True, slots=True)
class InputArtifactSpec:
    """How one pending input role is registered into the project artifact set."""

    artifact_id: str
    kind: str
    relative_path: str


_INPUT_ARTIFACT_SPECS = {
    "originalAudio": InputArtifactSpec(
        artifact_id="artifact_original_audio",
        kind="audio/wav",
        relative_path="input/original_audio.wav",
    ),
    "vocals": InputArtifactSpec(
        artifact_id="artifact_vocals_wav",
        kind="audio/wav",
        relative_path="audio/vocals.wav",
    ),
    "accompaniment": InputArtifactSpec(
        artifact_id="artifact_accompaniment_wav",
        kind="audio/wav",
        relative_path="audio/accompaniment.wav",
    ),
    "lyrics": InputArtifactSpec(
        artifact_id="artifact_lyrics_txt",
        kind="text/plain",
        relative_path="input/lyrics.txt",
    ),
    "melodyMidi": InputArtifactSpec(
        artifact_id="artifact_melody_midi",
        kind="audio/midi",
        relative_path="input/melody.mid",
    ),
}


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
        if manifest_path.exists() and overwrite:
            shutil.rmtree(project_dir)

        project_dir.mkdir(parents=True, exist_ok=True)
        manifest = ProjectManifest(project_id=project_id, project_dir=str(project_dir))
        manifest.set_step_status("createProject", "succeeded", output_artifact_ids=[])
        manifest.save(manifest_path)
        return manifest

    def create_project_from_pending_inputs(
        self,
        *,
        project_id: str,
        input_paths: list[str | Path],
        overwrite: bool = False,
    ) -> ProjectManifest:
        """Create a project and copy discovered files as unbound pending inputs."""

        manifest = self.create_empty_project(project_id=project_id, overwrite=overwrite)
        return self.add_pending_inputs(project_id, input_paths=input_paths)

    def add_pending_inputs(
        self,
        project_id: str,
        *,
        input_paths: list[str | Path],
    ) -> ProjectManifest:
        """Copy files into the project inbox without assigning artifact roles yet."""

        manifest_path = self._manifest_path(project_id)
        manifest = ProjectManifest.load(manifest_path)
        pending_inputs = _pending_inputs(manifest)
        project_dir = Path(manifest.project_dir)
        store = LocalArtifactStore(project_dir)
        for input_path in input_paths:
            source = Path(input_path)
            if not source.is_file():
                raise FileNotFoundError(source)
            relative_path = _unique_project_inbox_path(store, source.name)
            target = store.resolve_relative_path(relative_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            pending_inputs.append(
                {
                    "relativePath": relative_path,
                    "sourcePath": str(source),
                    "kind": _kind_for_input_path(source),
                    "status": "pending",
                }
            )
        manifest.metadata[_PENDING_INPUTS_METADATA_KEY] = pending_inputs
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
        """Create a project workspace with user inputs left pending."""

        self._validate_project_id(project_id)
        if lyrics_text is None and lyrics_path is None:
            raise ValueError("lyrics_text or lyrics_path is required")

        pending_paths = [Path(audio_path)]
        if lyrics_path is not None:
            pending_paths.append(Path(lyrics_path))
        manifest = self.create_project_from_pending_inputs(
            project_id=project_id,
            input_paths=pending_paths,
            overwrite=overwrite,
        )
        if lyrics_text is not None:
            project_dir = Path(manifest.project_dir)
            store = LocalArtifactStore(project_dir)
            text_path = store.resolve_relative_path("inbox/lyrics.txt")
            text_path.parent.mkdir(parents=True, exist_ok=True)
            text_path.write_text(lyrics_text, encoding="utf-8", newline="\n")
            manifest = ProjectManifest.load(project_dir / "manifest.json")
            pending_inputs = _pending_inputs(manifest)
            pending_inputs.append(
                {
                    "relativePath": "inbox/lyrics.txt",
                    "sourcePath": "",
                    "kind": "text/plain",
                    "status": "pending",
                }
            )
            manifest.metadata[_PENDING_INPUTS_METADATA_KEY] = pending_inputs
        manifest.metadata["manual"] = {
            "globalTempo": global_tempo,
            "meter": meter or {},
            "key": key or {},
        }
        manifest.save(self._manifest_path(project_id))
        return manifest

    def create_projects_from_import_dir(
        self,
        *,
        import_dir: str | Path | None = None,
        default_tempo: float | None = None,
        meter: dict[str, object] | None = None,
        overwrite: bool = False,
        fail_on_processed: bool = False,
    ) -> list[ProjectCreateResult]:
        """Create projects from grouped files in the configured import directory."""

        selected_import_dir = Path(import_dir or self.app_config.import_dir or "")
        if not str(selected_import_dir):
            raise ValueError("import directory is not configured")
        if not selected_import_dir.is_dir():
            raise FileNotFoundError(selected_import_dir)

        tempo = default_tempo if default_tempo is not None else self.app_config.default_tempo
        input_groups = _group_initial_input_files(
            selected_import_dir,
            audio_extensions=self.app_config.audio_extensions,
        )
        results: list[ProjectCreateResult] = []
        for project_name, input_files in input_groups:
            project_id = project_id_from_name(project_name)
            manifest_path = self._manifest_path(project_id)
            if manifest_path.exists() and not overwrite:
                message = "project already exists"
                if fail_on_processed:
                    raise ProjectAlreadyProcessedError(f"{message}: {manifest_path}")
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=", ".join(str(path) for path in input_files),
                        status="skipped",
                        message=message,
                    )
                )
                continue
            try:
                manifest = self.create_project_from_pending_inputs(
                    project_id=project_id,
                    input_paths=input_files,
                    overwrite=overwrite,
                )
                manifest.metadata["manual"] = {
                    "globalTempo": tempo,
                    "meter": meter or {},
                    "key": {},
                }
                manifest.save(self._manifest_path(project_id))
            except FileExistsError:
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=", ".join(str(path) for path in input_files),
                        status="skipped",
                        message="project already exists",
                    )
                )
            except Exception as exc:
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=", ".join(str(path) for path in input_files),
                        status="failed",
                        message=str(exc),
                    )
                )
            else:
                for input_file in input_files:
                    input_file.unlink()
                results.append(
                    ProjectCreateResult(
                        project_id=project_id,
                        audio_path=", ".join(str(path) for path in input_files),
                        status="created",
                    )
                )
        return results

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

    def update_manual_project_info(
        self,
        project_id: str,
        *,
        global_tempo: float | None,
        meter: dict[str, object] | None,
        key: dict[str, object] | None = None,
    ) -> ProjectManifest:
        """Update project-level manual parameters and their manifest artifacts."""

        manifest_path = self._manifest_path(project_id)
        manifest = ProjectManifest.load(manifest_path)
        store = LocalArtifactStore(manifest.project_dir)
        current_manual = dict(manifest.metadata.get("manual", {}))
        resolved_key = key if key is not None else dict(current_manual.get("key", {}))
        manifest.metadata["manual"] = {
            "globalTempo": global_tempo,
            "meter": meter or {},
            "key": resolved_key or {},
        }
        metadata_ref = self._write_manual_metadata_artifact(
            store,
            global_tempo=global_tempo,
            meter=meter,
            key=resolved_key,
        )
        manifest.register_artifact(metadata_ref)
        if global_tempo is not None:
            tempo_ref = self._write_provided_tempo_artifact(store, global_tempo=global_tempo)
            manifest.register_artifact(tempo_ref)
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
            self._register_pending_inputs_as_artifacts(manifest, LocalArtifactStore(manifest.project_dir))
            manifest.save(self._manifest_path(project_id))
            ready_tasks = [
                task
                for task in self._task_readiness(manifest)
                if task.ready and _should_run_task(manifest, task.task_type, force=False)
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
            manifest = ProjectManifest.load(self._manifest_path(project_id))
            store = LocalArtifactStore(manifest.project_dir)
            self._register_pending_inputs_as_artifacts(manifest, store)
            manifest.save(self._manifest_path(project_id))
            if not force and _task_outputs_exist(manifest, task_type):
                return []
            return [self.run_step(project_id, task_type)]
        return self._run_ready_chain(project_id, start_task_type=task_type, force=force)

    def run_step(self, project_id: str, task_type: str) -> TaskResult:
        """Run one project step and persist manifest changes."""

        manifest_path = self._manifest_path(project_id)
        manifest = ProjectManifest.load(manifest_path)
        store = LocalArtifactStore(manifest.project_dir)
        required_input_artifact_ids = required_input_artifact_ids_for_task(task_type)
        optional_input_artifact_ids = optional_input_artifact_ids_for_task(task_type)
        self._register_pending_inputs_as_artifacts(manifest, store)
        manifest.save(manifest_path)
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

    def _register_pending_inputs_as_artifacts(
        self,
        manifest: ProjectManifest,
        store: LocalArtifactStore,
    ) -> None:
        self._register_manual_artifacts(manifest, store)
        pending_inputs = _available_pending_inputs(
            manifest,
            self.app_config.audio_extensions,
            import_dir=self._global_input_dir(),
        )
        if not pending_inputs:
            return
        changed = False
        bound_inputs: list[tuple[dict[str, object], str]] = []
        for pending_input in pending_inputs:
            role = _input_role_for_pending_input(pending_input)
            spec = _INPUT_ARTIFACT_SPECS[role]
            if spec.artifact_id in manifest.artifacts:
                pending_input["status"] = "skipped"
                pending_input["artifactId"] = spec.artifact_id
                pending_input["skippedReason"] = "artifact already registered"
                bound_inputs.append((pending_input, spec.artifact_id))
                changed = True
                continue
            source_path = _pending_input_source_path(store, pending_input)
            artifact = store.import_file(
                source_path,
                kind=spec.kind,
                relative_path=spec.relative_path,
                artifact_id=spec.artifact_id,
                metadata={
                    "provided": True,
                    "providedAs": role,
                    "boundFromPendingInput": _pending_input_display_path(pending_input),
                    "sourcePath": str(pending_input.get("sourcePath", "")),
                    **_auto_bind_metadata(pending_input),
                },
            )
            manifest.register_artifact(artifact)
            _append_auto_bind_warning(manifest, pending_input, spec.artifact_id)
            pending_input["status"] = "bound"
            pending_input["artifactId"] = spec.artifact_id
            bound_inputs.append((pending_input, spec.artifact_id))
            changed = True
        if changed:
            manifest.metadata[_PENDING_INPUTS_METADATA_KEY] = _mark_pending_inputs_bound(manifest, bound_inputs)

    def _register_manual_artifacts(self, manifest: ProjectManifest, store: LocalArtifactStore) -> None:
        manual = manifest.metadata.get("manual")
        if not isinstance(manual, dict):
            return
        if "artifact_manual_metadata_json" not in manifest.artifacts:
            metadata_ref = self._write_manual_metadata_artifact(
                store,
                global_tempo=manual.get("globalTempo") if isinstance(manual.get("globalTempo"), int | float) else None,
                meter=manual.get("meter") if isinstance(manual.get("meter"), dict) else None,
                key=manual.get("key") if isinstance(manual.get("key"), dict) else None,
            )
            manifest.register_artifact(metadata_ref)
        if manual.get("globalTempo") is not None and "artifact_tempo_timeline_json" not in manifest.artifacts:
            tempo_ref = self._write_provided_tempo_artifact(
                store,
                global_tempo=float(manual["globalTempo"]) if isinstance(manual["globalTempo"], int | float) else None,
            )
            manifest.register_artifact(tempo_ref)

    def _manifest_path(self, project_id: str) -> Path:
        if not project_id:
            raise ValueError("project_id is required")
        return self.workspace_root / project_id / "manifest.json"

    def _global_input_dir(self) -> str | None:
        if self.app_config.import_dir:
            return self.app_config.import_dir
        try:
            if self.workspace_root.resolve() == Path("workspaces").resolve():
                return "inbox"
        except FileNotFoundError:
            return None
        return None

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
            self._register_pending_inputs_as_artifacts(manifest, LocalArtifactStore(manifest.project_dir))
            manifest.save(self._manifest_path(project_id))
            ready_tasks = [
                task
                for task in self._task_readiness(manifest)
                if task.ready
                and _task_type_sort_key(task.task_type)[0] >= start_index
                and task.task_type not in ran_task_types
                and _should_run_task(manifest, task.task_type, force=force)
            ]
            if not ready_tasks:
                return results
            if not results and start_task_type is not None:
                selected = next((task for task in ready_tasks if task.task_type == start_task_type), None)
            else:
                selected = ready_tasks[0]
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


def input_group_name_from_path(path: str | Path) -> str:
    """Return the workspace grouping name for an initial inbox file."""

    stem = Path(path).stem
    normalized = stem.lower()
    for suffix in (
        "_vox",
        "_vocal",
        "_vocals",
        "_instrument",
        "_instruments",
        "_accompaniment",
    ):
        if normalized.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


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
    try:
        return node_id_for_task(task_type)
    except NotImplementedError:
        pass
    return "local"


def _should_run_task(manifest: ProjectManifest, task_type: str, *, force: bool) -> bool:
    if force:
        return True
    if _task_outputs_exist(manifest, task_type):
        return False
    step = manifest.steps.get(task_type)
    return step is None or step.status not in {"running", "succeeded"}


def _task_outputs_exist(manifest: ProjectManifest, task_type: str) -> bool:
    output_artifact_ids = output_artifact_ids_for_task(task_type)
    return bool(output_artifact_ids) and all(artifact_id in manifest.artifacts for artifact_id in output_artifact_ids)


def _pending_inputs(manifest: ProjectManifest) -> list[dict[str, object]]:
    pending = manifest.metadata.get(_PENDING_INPUTS_METADATA_KEY, [])
    if not isinstance(pending, list):
        return []
    return [dict(item) for item in pending if isinstance(item, dict)]


def _available_pending_inputs(
    manifest: ProjectManifest,
    audio_extensions: list[str],
    *,
    import_dir: str | None,
) -> list[dict[str, object]]:
    project_dir = Path(manifest.project_dir)
    artifact_relative_paths = {
        artifact.relative_path
        for artifact in manifest.artifacts.values()
        if artifact.relative_path
    }
    audio_suffixes = {extension.lower() for extension in audio_extensions}
    input_suffixes = {*audio_suffixes, *_MIDI_INPUT_EXTENSIONS, ".txt"}
    pending_inputs = [
        item
        for item in _pending_inputs(manifest)
        if item.get("status", "pending") == "pending"
        and isinstance(item.get("relativePath"), str)
        and item.get("relativePath") not in artifact_relative_paths
    ]
    seen = {str(item["relativePath"]) for item in pending_inputs}
    inbox_dir = project_dir / "inbox"
    if inbox_dir.is_dir():
        for path in sorted(inbox_dir.iterdir()):
            relative_path = f"inbox/{path.name}"
            if (
                path.is_file()
                and path.suffix.lower() in input_suffixes
                and relative_path not in artifact_relative_paths
                and relative_path not in seen
            ):
                pending_inputs.append(
                    {
                        "relativePath": relative_path,
                        "sourcePath": str(path),
                        "kind": _kind_for_input_path(path),
                        "status": "pending",
                    }
                )
    global_inbox_inputs = _global_inbox_inputs(
        manifest,
        input_suffixes=input_suffixes,
        import_dir=import_dir,
        seen_source_paths={
            str(item.get("sourcePath"))
            for item in pending_inputs
            if item.get("sourcePath")
        },
    )
    pending_inputs.extend(global_inbox_inputs)
    return pending_inputs


def _global_inbox_inputs(
    manifest: ProjectManifest,
    *,
    input_suffixes: set[str],
    import_dir: str | None,
    seen_source_paths: set[str],
) -> list[dict[str, object]]:
    if import_dir is None:
        return []
    inbox_dir = Path(import_dir)
    if not inbox_dir.is_dir():
        return []
    candidates = [
        path
        for path in sorted(inbox_dir.iterdir())
        if path.is_file()
        and path.suffix.lower() in input_suffixes
        and str(path) not in seen_source_paths
    ]
    if not candidates:
        return []
    matching_project = [
        path
        for path in candidates
        if project_id_from_name(input_group_name_from_path(path)).lower() == manifest.project_id.lower()
    ]
    if matching_project:
        selected = matching_project
        auto_bind_reason = ""
    elif len(candidates) == 1:
        selected = candidates
        auto_bind_reason = "single global inbox candidate"
    else:
        selected = []
        auto_bind_reason = ""
    inputs = []
    for path in selected:
        item = {
            "relativePath": "",
            "sourcePath": str(path),
            "kind": _kind_for_input_path(path),
            "status": "pending",
        }
        if auto_bind_reason:
            item["autoBindReason"] = auto_bind_reason
        inputs.append(item)
    return inputs


def _mark_pending_inputs_bound(
    manifest: ProjectManifest,
    bound_inputs: list[tuple[dict[str, object], str]],
) -> list[dict[str, object]]:
    pending_inputs = _pending_inputs(manifest)
    by_pending_key = {
        _pending_input_key(item): item
        for item in pending_inputs
    }
    for bound_input, artifact_id in bound_inputs:
        key = _pending_input_key(bound_input)
        target = by_pending_key.get(key)
        if target is None:
            target = {
                "relativePath": str(bound_input.get("relativePath", "")),
                "sourcePath": str(bound_input.get("sourcePath", "")),
                "kind": str(bound_input.get("kind") or "audio/wav"),
            }
            pending_inputs.append(target)
            by_pending_key[key] = target
        target["status"] = "bound"
        target["artifactId"] = artifact_id
        if bound_input.get("autoBindReason"):
            target["autoBindReason"] = str(bound_input["autoBindReason"])
    return pending_inputs


def _auto_bind_metadata(pending_input: dict[str, object]) -> dict[str, object]:
    reason = pending_input.get("autoBindReason")
    if not reason:
        return {}
    return {"autoBound": True, "autoBindReason": str(reason)}


def _append_auto_bind_warning(
    manifest: ProjectManifest,
    pending_input: dict[str, object],
    artifact_id: str,
) -> None:
    reason = pending_input.get("autoBindReason")
    if not reason:
        return
    message = (
        f"auto-bound {pending_input.get('sourcePath')} to {artifact_id} "
        f"for project {manifest.project_id}: {reason}"
    )
    if message not in manifest.warnings:
        manifest.warnings.append(message)


def _pending_input_key(pending_input: dict[str, object]) -> str:
    relative_path = str(pending_input.get("relativePath", ""))
    if relative_path:
        return f"relative:{relative_path}"
    return f"source:{pending_input.get('sourcePath', '')}"


def _pending_input_display_path(pending_input: dict[str, object]) -> str:
    return str(pending_input.get("relativePath") or pending_input.get("sourcePath") or "")


def _pending_input_source_path(store: LocalArtifactStore, pending_input: dict[str, object]) -> Path:
    relative_path = str(pending_input.get("relativePath", ""))
    if relative_path:
        return store.resolve_relative_path(relative_path)
    source_path = str(pending_input.get("sourcePath", ""))
    if not source_path:
        raise FileNotFoundError("pending input has no relativePath or sourcePath")
    return Path(source_path)


def _unique_project_inbox_path(store: LocalArtifactStore, filename: str) -> str:
    stem = Path(filename).stem or "input"
    suffix = Path(filename).suffix
    candidate = f"inbox/{filename}"
    index = 2
    while store.resolve_relative_path(candidate).exists():
        candidate = f"inbox/{stem}-{index}{suffix}"
        index += 1
    return candidate


def _group_initial_input_files(
    input_dir: Path,
    *,
    audio_extensions: list[str],
) -> list[tuple[str, list[Path]]]:
    input_suffixes = {extension.lower() for extension in audio_extensions}
    input_suffixes.update(_MIDI_INPUT_EXTENSIONS)
    input_suffixes.add(".txt")
    grouped: dict[str, list[Path]] = {}
    for path in sorted(input_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in input_suffixes:
            continue
        group_name = input_group_name_from_path(path)
        grouped.setdefault(group_name, []).append(path)
    return sorted(grouped.items(), key=lambda item: project_id_from_name(item[0]).lower())


def _input_role_for_pending_input(pending_input: dict[str, object]) -> str:
    display_path = _pending_input_display_path(pending_input).lower()
    suffix = Path(display_path).suffix.lower()
    if suffix in _MIDI_INPUT_EXTENSIONS or str(pending_input.get("kind")) == "audio/midi":
        return "melodyMidi"
    if suffix == ".txt" or str(pending_input.get("kind")) == "text/plain":
        return "lyrics"
    name = Path(display_path).stem.lower()
    if "vox" in name or "vocal" in name:
        return "vocals"
    if "instrument" in name or "accompaniment" in name:
        return "accompaniment"
    return "originalAudio"


def _kind_for_input_path(path: Path) -> str:
    if path.suffix.lower() in _MIDI_INPUT_EXTENSIONS:
        return "audio/midi"
    if path.suffix.lower() == ".txt":
        return "text/plain"
    return _kind_for_audio_path(path)


def _kind_for_audio_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".flac":
        return "audio/flac"
    return "audio/wav"
