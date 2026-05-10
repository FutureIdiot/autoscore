import json
import tempfile
import unittest
from pathlib import Path

from autoscore.config import AppConfig, PackageConfig, load_app_config, load_package_config


class PackageConfigTests(unittest.TestCase):
    def test_loads_default_app_config_when_file_missing(self) -> None:
        config = load_app_config("missing-autoscore-local.json")

        self.assertIsInstance(config, AppConfig)
        self.assertEqual(config.workspace_root, "workspaces")
        self.assertIsNone(config.import_dir)

    def test_loads_json_app_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "autoscore.local.json"
            path.write_text(
                json.dumps(
                    {
                        "importDir": "D:/autoscore-imports",
                        "workspaceRoot": "D:/autoscore-workspaces",
                        "defaultTempo": 120,
                        "audioExtensions": [".wav"],
                    }
                ),
                encoding="utf-8",
            )

            config = load_app_config(path)

        self.assertEqual(config.workspace_root, "D:/autoscore-workspaces")
        self.assertEqual(config.import_dir, "D:/autoscore-imports")
        self.assertEqual(config.default_tempo, 120)
        self.assertEqual(config.audio_extensions, [".wav"])

    def test_package_config_round_trip_uses_contract_names(self) -> None:
        config = PackageConfig(
            package_id="timeline-package",
            package_version="0.1.0",
            node_id="timeline-local",
            node_types=["tempo-node", "phrase-node"],
            supported_tasks=["estimateTempo", "detectPhrases"],
            artifact_kinds=["audio/wav"],
            local_artifact_cache_dir="D:/autoscore-worker/artifacts",
            runtime={"python": "3.12"},
        )

        data = config.to_dict()

        self.assertEqual(data["packageId"], "timeline-package")
        self.assertEqual(data["nodeTypes"], ["tempo-node", "phrase-node"])
        self.assertEqual(PackageConfig.from_dict(data), config)

    def test_loads_json_package_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "timeline.json"
            path.write_text(
                json.dumps(
                    {
                        "packageId": "timeline-package",
                        "packageVersion": "0.1.0",
                        "nodeId": "timeline-local",
                        "nodeTypes": ["tempo-node"],
                        "supportedTasks": ["estimateTempo"],
                    }
                ),
                encoding="utf-8",
            )

            config = load_package_config(path)

        self.assertEqual(config.package_id, "timeline-package")
        self.assertEqual(config.schema_versions, [1])

    def test_loads_toml_package_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "timeline.toml"
            path.write_text(
                """
packageId = "timeline-package"
packageVersion = "0.1.0"
nodeId = "timeline-local"
nodeTypes = ["tempo-node"]
supportedTasks = ["estimateTempo"]
schemaVersions = [1]

[runtime]
python = "3.12"
""".strip(),
                encoding="utf-8",
            )

            config = load_package_config(path)

        self.assertEqual(config.runtime["python"], "3.12")


if __name__ == "__main__":
    unittest.main()
