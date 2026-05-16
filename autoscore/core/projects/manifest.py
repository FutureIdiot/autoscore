"""Project manifest model and JSON persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from autoscore.constants import PROJECT_MANIFEST_SCHEMA_VERSION
from autoscore.core.artifacts import ArtifactRef
from autoscore.core.projects.migrate import migrate_manifest_dict

TASK_STATES = {
    "pending",
    "ready",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
}

TaskStatus = Literal[
    "pending",
    "ready",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class ManifestStep:
    """Status record for one pipeline step or task type."""

    task_type: str
    status: TaskStatus = "pending"
    input_artifact_ids: list[str] = field(default_factory=list)
    output_artifact_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    execution: dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now_iso)

    def __post_init__(self) -> None:
        if not self.task_type:
            raise ValueError("task_type is required")
        if self.status not in TASK_STATES:
            raise ValueError(f"invalid task status: {self.status}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ManifestStep":
        return cls(
            task_type=data["taskType"],
            status=data.get("status", "pending"),
            input_artifact_ids=list(data.get("inputArtifactIds", [])),
            output_artifact_ids=list(data.get("outputArtifactIds", [])),
            warnings=list(data.get("warnings", [])),
            errors=list(data.get("errors", [])),
            execution=dict(data.get("execution", {})),
            updated_at=data.get("updatedAt", utc_now_iso()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskType": self.task_type,
            "status": self.status,
            "inputArtifactIds": self.input_artifact_ids,
            "outputArtifactIds": self.output_artifact_ids,
            "warnings": self.warnings,
            "errors": self.errors,
            "execution": self.execution,
            "updatedAt": self.updated_at,
        }


@dataclass(slots=True)
class ProjectManifest:
    """Durable project-level state owned by the orchestrator."""

    project_id: str
    project_dir: str
    schema_version: int = PROJECT_MANIFEST_SCHEMA_VERSION
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    steps: dict[str, ManifestStep] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.project_dir:
            raise ValueError("project_dir is required")
        if self.schema_version != PROJECT_MANIFEST_SCHEMA_VERSION:
            warning = (
                f"manifest schemaVersion {self.schema_version} differs from current "
                f"{PROJECT_MANIFEST_SCHEMA_VERSION}; migration should be handled before persistence"
            )
            if warning not in self.warnings:
                self.warnings.append(warning)

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def register_artifact(self, artifact: ArtifactRef) -> None:
        self.artifacts[artifact.artifact_id] = artifact
        self.touch()

    def get_artifact(self, artifact_id: str) -> ArtifactRef:
        try:
            return self.artifacts[artifact_id]
        except KeyError as exc:
            raise KeyError(f"unknown artifact: {artifact_id}") from exc

    def set_step(self, step: ManifestStep) -> None:
        self.steps[step.task_type] = step
        self.touch()

    def set_step_status(
        self,
        task_type: str,
        status: TaskStatus,
        *,
        input_artifact_ids: list[str] | None = None,
        output_artifact_ids: list[str] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
        execution: dict[str, Any] | None = None,
    ) -> ManifestStep:
        if status not in TASK_STATES:
            raise ValueError(f"invalid task status: {status}")
        step = self.steps.get(task_type, ManifestStep(task_type=task_type))
        step.status = status
        if input_artifact_ids is not None:
            step.input_artifact_ids = input_artifact_ids
        if output_artifact_ids is not None:
            step.output_artifact_ids = output_artifact_ids
        if warnings is not None:
            step.warnings = warnings
        if errors is not None:
            step.errors = errors
        if execution is not None:
            step.execution = execution
        step.updated_at = utc_now_iso()
        self.steps[task_type] = step
        self.touch()
        return step

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, project_dir: str | Path | None = None) -> "ProjectManifest":
        migrated_data, _migration_warnings = migrate_manifest_dict(data)
        artifacts = {
            artifact_id: ArtifactRef.from_dict(artifact_data)
            for artifact_id, artifact_data in migrated_data.get("artifacts", {}).items()
        }
        steps = {
            task_type: ManifestStep.from_dict(step_data)
            for task_type, step_data in migrated_data.get("steps", {}).items()
        }
        resolved_project_dir = str(project_dir) if project_dir is not None else migrated_data["projectDir"]
        return cls(
            project_id=migrated_data["projectId"],
            project_dir=resolved_project_dir,
            schema_version=migrated_data.get("schemaVersion", PROJECT_MANIFEST_SCHEMA_VERSION),
            created_at=migrated_data.get("createdAt", utc_now_iso()),
            updated_at=migrated_data.get("updatedAt", utc_now_iso()),
            artifacts=artifacts,
            steps=steps,
            metadata=dict(migrated_data.get("metadata", {})),
            warnings=list(migrated_data.get("warnings", [])),
            errors=list(migrated_data.get("errors", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "projectId": self.project_id,
            "projectDir": self.project_dir,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "metadata": self.metadata,
            "artifacts": {
                artifact_id: artifact.to_dict()
                for artifact_id, artifact in sorted(self.artifacts.items())
            },
            "steps": {
                task_type: step.to_dict()
                for task_type, step in sorted(self.steps.items())
            },
            "warnings": self.warnings,
            "errors": self.errors,
        }

    @classmethod
    def load(cls, path: str | Path) -> "ProjectManifest":
        manifest_path = Path(path)
        with manifest_path.open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle), project_dir=manifest_path.parent)

    def save(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
