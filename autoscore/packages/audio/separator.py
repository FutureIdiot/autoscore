"""separator-node local implementations."""

from __future__ import annotations

import shutil

from autoscore.core.artifacts import LocalArtifactStore
from autoscore.runtime.tasks import ExecutionInfo, TaskEnvelope, TaskResult


def run_mock_separator(envelope: TaskEnvelope, store: LocalArtifactStore) -> TaskResult:
    """Create deterministic mock stem artifacts from the original audio input."""

    original = _find_input_artifact(envelope, "artifact_original_audio")
    source = store.materialize(original)
    output_specs = [
        ("artifact_vocals_wav", "audio/vocals.wav"),
        ("artifact_accompaniment_wav", "audio/accompaniment.wav"),
    ]
    output_artifacts = []
    for artifact_id, relative_path in output_specs:
        target = store.resolve_relative_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        output_artifacts.append(
            store.create_ref(
                artifact_id=artifact_id,
                kind="audio/wav",
                relative_path=relative_path,
                metadata={"mockSourceArtifactId": original.artifact_id},
            )
        )

    return TaskResult(
        task_id=envelope.task_id,
        project_id=envelope.project_id,
        task_type=envelope.task_type,
        status="succeeded",
        output_artifacts=output_artifacts,
        execution=ExecutionInfo(mode="local", transport="in_process", node_id="audio-local"),
    )


def _find_input_artifact(envelope: TaskEnvelope, artifact_id: str):
    artifact = envelope.input_artifact_index.get(artifact_id)
    if artifact is not None:
        return artifact
    raise KeyError(f"missing required input artifact: {artifact_id}")
