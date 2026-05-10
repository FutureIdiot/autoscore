"""Local task runner dispatch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from autoscore.core.artifacts import ArtifactRef, LocalArtifactStore
from autoscore.packages.audio.separator import run_mock_separator
from autoscore.packages.timeline.phrases import run_mock_phrase_detector
from autoscore.packages.timeline.tempo import run_mock_tempo_estimator
from autoscore.runtime.tasks import ExecutionInfo, TaskEnvelope, TaskRequirements, TaskResult

TaskRunner = Callable[[TaskEnvelope, LocalArtifactStore], TaskResult]


@dataclass(frozen=True, slots=True)
class TaskInputSpec:
    """Input artifacts grouped by hard requirements and optional context."""

    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()


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
    """Return all manifest artifact ids understood by a task."""

    spec = input_artifact_spec_for_task(task_type)
    return [*spec.required, *spec.optional]


def required_input_artifact_ids_for_task(task_type: str) -> list[str]:
    """Return artifact ids that must exist before a task can run."""

    return list(input_artifact_spec_for_task(task_type).required)


def optional_input_artifact_ids_for_task(task_type: str) -> list[str]:
    """Return artifact ids that enrich a task but should not block it."""

    return list(input_artifact_spec_for_task(task_type).optional)


def input_artifact_spec_for_task(task_type: str) -> TaskInputSpec:
    """Return the input artifact contract for a task."""

    try:
        return _INPUT_ARTIFACT_SPECS[task_type]
    except KeyError as exc:
        raise NotImplementedError(f"runner for task type {task_type!r} is not implemented") from exc


def implemented_task_types() -> list[str]:
    """Return task types implemented by the local runner dispatch."""

    return list(_LOCAL_RUNNERS)


def _requirements_for_task(task_type: str) -> TaskRequirements:
    if task_type == "separateAudio":
        return TaskRequirements(node_types=["separator-node"], required_backends=["mock"], artifact_kinds=["audio/wav"])
    if task_type == "estimateTempo":
        return TaskRequirements(
            node_types=["tempo-node"],
            required_backends=["mock"],
            artifact_kinds=["audio/wav", "application/json"],
        )
    if task_type == "detectPhrases":
        return TaskRequirements(
            node_types=["phrase-node"],
            required_backends=["mock"],
            artifact_kinds=["audio/wav", "text/plain", "application/json"],
        )
    return TaskRequirements(required_backends=["mock"])


def _node_id_for_task(task_type: str) -> str:
    if task_type == "separateAudio":
        return "audio-local"
    if task_type == "estimateTempo":
        return "timeline-local"
    if task_type == "detectPhrases":
        return "timeline-local"
    return "local"


_INPUT_ARTIFACT_SPECS = {
    "separateAudio": TaskInputSpec(required=("artifact_original_audio",)),
    "estimateTempo": TaskInputSpec(
        required=("artifact_original_audio",),
        optional=("artifact_manual_metadata_json",),
    ),
    "detectPhrases": TaskInputSpec(
        required=("artifact_vocals_wav", "artifact_tempo_timeline_json"),
        optional=("artifact_lyrics_txt", "artifact_manual_metadata_json"),
    ),
}

_LOCAL_RUNNERS: dict[str, TaskRunner] = {
    "separateAudio": run_mock_separator,
    "estimateTempo": run_mock_tempo_estimator,
    "detectPhrases": run_mock_phrase_detector,
}
