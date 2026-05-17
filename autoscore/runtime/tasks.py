"""Task envelope and result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from autoscore.constants import TASK_ENVELOPE_SCHEMA_VERSION, TASK_REQUIREMENTS_SCHEMA_VERSION
from autoscore.core.artifacts import ArtifactRef
from autoscore.core.tasks import ExecutionInfo, TaskResult, TaskResultStatus


@dataclass(slots=True)
class TaskRequirements:
    """Scheduling requirements used to match a task to a node."""

    node_types: list[str] = field(default_factory=list)
    gpu_vendor: str | None = None
    min_vram_gb: int | None = None
    required_backends: list[str] = field(default_factory=list)
    required_models: list[str] = field(default_factory=list)
    schema_version: int = TASK_REQUIREMENTS_SCHEMA_VERSION
    artifact_kinds: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.min_vram_gb is not None and self.min_vram_gb < 0:
            raise ValueError("min_vram_gb must be non-negative")
        if self.schema_version != TASK_REQUIREMENTS_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRequirements":
        return cls(
            node_types=list(data.get("nodeTypes", [])),
            gpu_vendor=data.get("gpuVendor"),
            min_vram_gb=data.get("minVramGb"),
            required_backends=list(data.get("requiredBackends", [])),
            required_models=list(data.get("requiredModels", [])),
            schema_version=int(data.get("schemaVersion", TASK_REQUIREMENTS_SCHEMA_VERSION)),
            artifact_kinds=list(data.get("artifactKinds", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodeTypes": self.node_types,
            "gpuVendor": self.gpu_vendor,
            "minVramGb": self.min_vram_gb,
            "requiredBackends": self.required_backends,
            "requiredModels": self.required_models,
            "schemaVersion": self.schema_version,
            "artifactKinds": self.artifact_kinds,
        }


@dataclass(slots=True)
class TaskEnvelope:
    """Common task input envelope used by local and remote runners."""

    task_id: str
    project_id: str
    task_type: str
    schema_version: int = TASK_ENVELOPE_SCHEMA_VERSION
    input_artifacts: list[ArtifactRef] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    requirements: TaskRequirements = field(default_factory=TaskRequirements)
    requested_outputs: list[str] = field(default_factory=list)
    execution: ExecutionInfo = field(default_factory=ExecutionInfo)
    _input_artifact_index: dict[str, ArtifactRef] | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _input_artifact_index_size: int = field(default=-1, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.task_type:
            raise ValueError("task_type is required")
        if self.schema_version != TASK_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")

    @property
    def input_artifact_index(self) -> dict[str, ArtifactRef]:
        """Return input artifacts keyed by artifact id for repeated lookups."""

        if self._input_artifact_index is None or self._input_artifact_index_size != len(self.input_artifacts):
            artifact_index: dict[str, ArtifactRef] = {}
            for artifact in self.input_artifacts:
                artifact_index.setdefault(artifact.artifact_id, artifact)
            self._input_artifact_index = artifact_index
            self._input_artifact_index_size = len(self.input_artifacts)
        return self._input_artifact_index

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskEnvelope":
        return cls(
            task_id=data["taskId"],
            project_id=data["projectId"],
            task_type=data["taskType"],
            schema_version=int(data.get("schemaVersion", TASK_ENVELOPE_SCHEMA_VERSION)),
            input_artifacts=[ArtifactRef.from_dict(item) for item in data.get("inputArtifacts", [])],
            params=dict(data.get("params", {})),
            requirements=TaskRequirements.from_dict(data.get("requirements", {})),
            requested_outputs=list(data.get("requestedOutputs", [])),
            execution=ExecutionInfo.from_dict(data.get("execution", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "projectId": self.project_id,
            "taskType": self.task_type,
            "schemaVersion": self.schema_version,
            "inputArtifacts": [artifact.to_dict() for artifact in self.input_artifacts],
            "params": self.params,
            "requirements": self.requirements.to_dict(),
            "requestedOutputs": self.requested_outputs,
            "execution": self.execution.to_dict(),
        }
