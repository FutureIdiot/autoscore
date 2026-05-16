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


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Static local dispatch contract for one task type."""

    runner: TaskRunner
    input_artifacts: TaskInputSpec
    output_artifacts: tuple[str, ...]
    requirements: TaskRequirements
    node_id: str


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
        requirements=requirements_for_task(task_type),
        execution=ExecutionInfo(mode="local", transport="in_process", node_id=node_id_for_task(task_type)),
    )


def get_local_runner(task_type: str) -> TaskRunner:
    """Return the local runner for a task type."""

    return task_spec_for_task(task_type).runner


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


def output_artifact_ids_for_task(task_type: str) -> list[str]:
    """Return artifact ids a task is expected to produce."""

    return list(task_spec_for_task(task_type).output_artifacts)


def input_artifact_spec_for_task(task_type: str) -> TaskInputSpec:
    """Return the input artifact contract for a task."""

    return task_spec_for_task(task_type).input_artifacts


def requirements_for_task(task_type: str) -> TaskRequirements:
    """Return a fresh scheduling requirements object for a task."""

    return TaskRequirements.from_dict(task_spec_for_task(task_type).requirements.to_dict())


def node_id_for_task(task_type: str) -> str:
    """Return the default local node id for a task."""

    return task_spec_for_task(task_type).node_id


def task_spec_for_task(task_type: str) -> TaskSpec:
    """Return the local dispatch spec for a task."""

    try:
        return _TASK_SPECS[task_type]
    except KeyError as exc:
        raise NotImplementedError(f"task spec for task type {task_type!r} is not implemented") from exc


def implemented_task_types() -> list[str]:
    """Return task types implemented by the local runner dispatch."""

    return list(_TASK_SPECS)


_TASK_SPECS = {
    "separateAudio": TaskSpec(
        runner=run_mock_separator,
        input_artifacts=TaskInputSpec(required=("artifact_original_audio",)),
        output_artifacts=("artifact_vocals_wav", "artifact_accompaniment_wav"),
        requirements=TaskRequirements(
            node_types=["separator-node"],
            required_backends=["mock"],
            artifact_kinds=["audio/wav"],
        ),
        node_id="audio-local",
    ),
    "estimateTempo": TaskSpec(
        runner=run_mock_tempo_estimator,
        input_artifacts=TaskInputSpec(
            required=("artifact_original_audio",),
            optional=("artifact_manual_metadata_json",),
        ),
        output_artifacts=("artifact_tempo_timeline_json",),
        requirements=TaskRequirements(
            node_types=["tempo-node"],
            required_backends=["mock"],
            artifact_kinds=["audio/wav", "application/json"],
        ),
        node_id="timeline-local",
    ),
    "detectPhrases": TaskSpec(
        runner=run_mock_phrase_detector,
        input_artifacts=TaskInputSpec(
            required=("artifact_vocals_wav",),
            optional=("artifact_tempo_timeline_json", "artifact_lyrics_txt", "artifact_manual_metadata_json"),
        ),
        output_artifacts=("artifact_phrase_timeline_json",),
        requirements=TaskRequirements(
            node_types=["phrase-node"],
            required_backends=["mock"],
            artifact_kinds=["audio/wav", "text/plain", "application/json"],
        ),
        node_id="timeline-local",
    ),
}
