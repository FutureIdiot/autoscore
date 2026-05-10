import tempfile
import unittest
from pathlib import Path

from autoscore.cli.tui import _parse_send_command
from autoscore.runtime import AutoscoreController


class TuiCommandTests(unittest.TestCase):
    def test_parse_send_command_accepts_numbered_task_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AutoscoreController(Path(temp_dir) / "workspaces")
            controller.create_empty_project(project_id="demo")
            status = controller.get_project_status("demo")

            task_type, continue_pipeline, force = _parse_send_command("send 3&!", status=status)

        self.assertEqual(task_type, "detectPhrases")
        self.assertTrue(continue_pipeline)
        self.assertTrue(force)


if __name__ == "__main__":
    unittest.main()
