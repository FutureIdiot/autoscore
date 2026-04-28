"""Controller API shared by CLI, TUI, and future WebUI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from autoscore.core.artifacts import LocalArtifactStore
from autoscore.core.projects import ProjectManifest
from autoscore.runtime.registry import NodeRegistration, default_local_nodes

_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


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


@dataclass(frozen=True, slots=True)
class ProjectStatus:
    """Project status snapshot for UI consumers."""

    summary: ProjectSummary
    steps: list[StepStatus] = field(default_factory=list)
    artifact_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class AutoscoreController:
    """Stable control surface for UI layers."""

    def __init__(
        self,
        workspace_root: str | Path = "workspaces",
        nodes: list[NodeRegistration] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self._nodes = nodes if nodes is not None else default_local_nodes()

    def list_projects(self) -> list[ProjectSummary]:
        manifests = sorted(self.workspace_root.glob("*/manifest.json"))
        return [self._summary_from_manifest(ProjectManifest.load(path), path) for path in manifests]

    def list_nodes(self) -> list[NodeRegistration]:
        return sorted(self._nodes, key=lambda node: node.node_id)

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
            )
            for step in sorted(manifest.steps.values(), key=lambda item: item.task_type)
        ]
        return ProjectStatus(
            summary=summary,
            steps=steps,
            artifact_ids=sorted(manifest.artifacts),
            warnings=list(manifest.warnings),
            errors=list(manifest.errors),
        )

    def run_step(self, project_id: str, task_type: str) -> None:
        """Run one project step.

        Runners are intentionally not wired yet. TUI and WebUI can call this
        method later without changing their UI-facing contract.
        """

        raise NotImplementedError(f"runner for task type {task_type!r} is not implemented")

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
