"""Local task runner dispatch."""

from __future__ import annotations

from collections.abc import Callable

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.packages.audio.separator import run_mock_separator
from autoscore.packages.timeline.tempo import run_mock_tempo_estimator
from autoscore.runtime.tasks import ExecutionInfo, TaskEnvelope, TaskRequirements, TaskResult

TaskRunner = Callable[[TaskEnvelope, LocalArtifactStore], TaskResult]


def build_task_envelope(
    *,
    project_id: str,
    task_type: str,
    input_artifacts: list[ArtifactRef],
) -> TaskEnvelope:
    """Create the standard local envelope for a project task."""

    return TaskEnvelope(
        task_id=f"{project_id}:{task_type}",
        project_id=project_id,
        task_type=task_type,
        input_artifacts=input_artifacts,
        params={"backend": "mock"},
        requirements=_requirements_for_task(task_type),
        execution=ExecutionInfo(mode="local", transport="in_process", node_id=_node_id_for_task(task_type)),
    )


def get_local_runner(task_type: str) -> TaskRunner:
    """Return the local runner for a task type."""

    try:
        return _LOCAL_RUNNERS[task_type]
    except KeyError as exc:
        raise NotImplementedError(f"runner for task type {task_type!r} is not implemented") from exc


def input_artifact_ids_for_task(task_type: str) -> list[str]:
    """Return manifest artifact ids needed by a task."""

    try:
        return list(_INPUT_ARTIFACT_IDS[task_type])
    except KeyError as exc:
        raise NotImplementedError(f"runner for task type {task_type!r} is not implemented") from exc


def _requirements_for_task(task_type: str) -> TaskRequirements:
    if task_type == "separateAudio":
        return TaskRequirements(node_types=["separator-node"], required_backends=["mock"], artifact_kinds=["audio/wav"])
    if task_type == "estimateTempo":
        return TaskRequirements(
            node_types=["tempo-node"],
            required_backends=["mock"],
            artifact_kinds=["audio/wav", "application/json"],
        )
    return TaskRequirements(required_backends=["mock"])


def _node_id_for_task(task_type: str) -> str:
    if task_type == "separateAudio":
        return "audio-local"
    if task_type == "estimateTempo":
        return "timeline-local"
    return "local"


_INPUT_ARTIFACT_IDS = {
    "separateAudio": ("artifact_original_audio",),
    "estimateTempo": ("artifact_original_audio", "artifact_manual_metadata_json"),
}

_LOCAL_RUNNERS: dict[str, TaskRunner] = {
    "separateAudio": run_mock_separator,
    "estimateTempo": run_mock_tempo_estimator,
}
