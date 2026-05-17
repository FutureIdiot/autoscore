"""Core task result contracts shared by packages and runtime orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from autoscore.core.artifacts import ArtifactRef
from autoscore.core.problems import ProblemRecord


TASK_RESULT_STATES = {
    "pending",
    "ready",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
}

TaskResultStatus = Literal[
    "pending",
    "ready",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "skipped",
]


@dataclass(slots=True)
class ExecutionInfo:
    """Where and how a task is executed."""

    mode: str = "local"
    transport: str = "in_process"
    node_id: str = "local"
    started_at: str | None = None
    finished_at: str | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"local", "remote"}:
            raise ValueError(f"invalid execution mode: {self.mode}")
        if not self.transport:
            raise ValueError("transport is required")
        if not self.node_id:
            raise ValueError("node_id is required")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionInfo":
        return cls(
            mode=data.get("mode", "local"),
            transport=data.get("transport", "in_process"),
            node_id=data.get("nodeId", "local"),
            started_at=data.get("startedAt"),
            finished_at=data.get("finishedAt"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "transport": self.transport,
            "nodeId": self.node_id,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
        }


@dataclass(slots=True)
class TaskResult:
    """Common task result shape returned by local and remote runners."""

    task_id: str
    project_id: str
    task_type: str
    status: TaskResultStatus
    output_artifacts: list[ArtifactRef] = field(default_factory=list)
    warnings: list[ProblemRecord] = field(default_factory=list)
    errors: list[ProblemRecord] = field(default_factory=list)
    execution: ExecutionInfo = field(default_factory=ExecutionInfo)

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.project_id:
            raise ValueError("project_id is required")
        if not self.task_type:
            raise ValueError("task_type is required")
        if self.status not in TASK_RESULT_STATES:
            raise ValueError(f"invalid task status: {self.status}")
        if self.status == "failed" and not self.errors:
            raise ValueError("failed task results must include at least one error")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskResult":
        return cls(
            task_id=data["taskId"],
            project_id=data["projectId"],
            task_type=data["taskType"],
            status=data["status"],
            output_artifacts=[ArtifactRef.from_dict(item) for item in data.get("outputArtifacts") or []],
            warnings=[ProblemRecord.from_dict(item) for item in data.get("warnings") or []],
            errors=[ProblemRecord.from_dict(item) for item in data.get("errors") or []],
            execution=ExecutionInfo.from_dict(data.get("execution", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskId": self.task_id,
            "projectId": self.project_id,
            "taskType": self.task_type,
            "status": self.status,
            "outputArtifacts": [artifact.to_dict() for artifact in self.output_artifacts],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "errors": [error.to_dict() for error in self.errors],
            "execution": self.execution.to_dict(),
        }
