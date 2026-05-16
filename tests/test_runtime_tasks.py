import unittest

from autoscore.core.artifacts import ArtifactRef
from autoscore.core.problems import ProblemRecord
from autoscore.constants import TASK_ENVELOPE_SCHEMA_VERSION, TASK_REQUIREMENTS_SCHEMA_VERSION
from autoscore.runtime import ExecutionInfo, TaskEnvelope, TaskRequirements, TaskResult


class RuntimeTaskTests(unittest.TestCase):
    def test_task_envelope_round_trip_uses_contract_names(self) -> None:
        envelope = TaskEnvelope(
            task_id="task_001",
            project_id="project_001",
            task_type="separateAudio",
            input_artifacts=[
                ArtifactRef(
                    artifact_id="artifact_original_audio",
                    kind="audio/wav",
                    relative_path="input/original_audio.wav",
                )
            ],
            params={"backend": "mock"},
            requirements=TaskRequirements(node_types=["separator-node"], required_backends=["mock"]),
            requested_outputs=["vocals", "accompaniment"],
            execution=ExecutionInfo(mode="remote", transport="http", node_id="audio-node-01"),
        )

        data = envelope.to_dict()

        self.assertEqual(data["taskId"], "task_001")
        self.assertEqual(data["inputArtifacts"][0]["artifactId"], "artifact_original_audio")
        self.assertEqual(data["requirements"]["nodeTypes"], ["separator-node"])
        self.assertEqual(TaskEnvelope.from_dict(data), envelope)

    def test_task_contract_schema_versions_are_explicit(self) -> None:
        envelope = TaskEnvelope(task_id="task_001", project_id="project_001", task_type="separateAudio")
        requirements = TaskRequirements()

        self.assertEqual(envelope.schema_version, TASK_ENVELOPE_SCHEMA_VERSION)
        self.assertEqual(requirements.schema_version, TASK_REQUIREMENTS_SCHEMA_VERSION)

    def test_task_result_round_trip_uses_problem_records(self) -> None:
        result = TaskResult(
            task_id="task_001",
            project_id="project_001",
            task_type="estimateTempo",
            status="succeeded",
            warnings=[ProblemRecord.warning("tempo.manual_override", "manual tempo was used")],
        )

        data = result.to_dict()

        self.assertEqual(data["warnings"][0]["severity"], "warning")
        self.assertEqual(TaskResult.from_dict(data), result)

    def test_failed_task_result_requires_error_record(self) -> None:
        with self.assertRaises(ValueError):
            TaskResult(
                task_id="task_001",
                project_id="project_001",
                task_type="analyzeMidi",
                status="failed",
            )

    def test_problem_record_rejects_invalid_severity(self) -> None:
        with self.assertRaises(ValueError):
            ProblemRecord(severity="info", code="demo", message="demo")


if __name__ == "__main__":
    unittest.main()
