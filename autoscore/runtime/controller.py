"""Controller API shared by CLI, TUI, and future WebUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from autoscore.core.projects import ProjectManifest
from autoscore.runtime.registry import NodeRegistration, default_local_nodes


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
