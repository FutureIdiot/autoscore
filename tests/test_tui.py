import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from autoscore.cli.tui import _input_groups_from_inbox, _parse_send_command, _send_to_nodes
from autoscore.config import AppConfig
from autoscore.runtime import AutoscoreController


class TuiCommandTests(unittest.TestCase):
    def test_parse_send_command_accepts_numbered_task_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            controller = AutoscoreController(Path(temp_dir) / "workspaces")
            controller.create_empty_project(project_id="demo")
            status = controller.get_project_status("demo")

            task_type, continue_pipeline, force, delete_sources = _parse_send_command("send 3&!", status=status)

        self.assertEqual(task_type, "detectPhrases")
        self.assertTrue(continue_pipeline)
        self.assertTrue(force)
        self.assertFalse(delete_sources)

    def test_parse_send_command_accepts_delete_source_suffix(self) -> None:
        task_type, continue_pipeline, force, delete_sources = _parse_send_command("send+D")

        self.assertIsNone(task_type)
        self.assertTrue(continue_pipeline)
        self.assertFalse(force)
        self.assertTrue(delete_sources)

    def test_input_groups_include_midi_and_text_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            inbox = Path(temp_dir) / "inbox"
            inbox.mkdir()
            (inbox / "Song.wav").write_bytes(b"audio")
            (inbox / "Song.mid").write_bytes(b"MThd")
            (inbox / "Song.txt").write_text("lyrics", encoding="utf-8")
            controller = AutoscoreController(
                Path(temp_dir) / "workspaces",
                app_config=AppConfig(import_dir=str(inbox), audio_extensions=[".wav"]),
            )

            groups = _input_groups_from_inbox(controller)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], "Song")
        self.assertEqual([path.name for path in groups[0][1]], ["Song.mid", "Song.txt", "Song.wav"])

    def test_send_delete_suffix_removes_import_sources_after_score_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            import_dir = root / "imports"
            import_dir.mkdir()
            audio = import_dir / "song.wav"
            midi = import_dir / "song.mid"
            lyrics = import_dir / "song.txt"
            audio.write_bytes(b"audio")
            midi.write_bytes(b"MThd")
            lyrics.write_text("line", encoding="utf-8")
            controller = AutoscoreController(
                root / "workspaces",
                app_config=AppConfig(import_dir=str(import_dir), default_tempo=120),
            )
            controller.create_projects_from_import_dir()

            self.assertTrue(audio.exists())
            self.assertTrue(midi.exists())
            self.assertTrue(lyrics.exists())

            with redirect_stdout(StringIO()):
                _send_to_nodes(controller, "song", "send+D", pause=False)

        self.assertFalse(audio.exists())
        self.assertFalse(midi.exists())
        self.assertFalse(lyrics.exists())


if __name__ == "__main__":
    unittest.main()
