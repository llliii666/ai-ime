import unittest
from unittest.mock import patch

from ai_ime.app import build_parser, build_tray_command


class AppEntryTests(unittest.TestCase):
    def test_build_tray_command_runs_tray_module(self) -> None:
        command = build_tray_command()

        self.assertIn("-m", command)
        self.assertIn("ai_ime.tray", command)

    def test_build_tray_command_runs_foreground_for_frozen_exe(self) -> None:
        with patch("ai_ime.app.sys.frozen", True, create=True), patch("ai_ime.app.sys.executable", "AI IME.exe"):
            command = build_tray_command()

        self.assertEqual(command, ["AI IME.exe", "--foreground"])

    def test_parser_supports_status_and_stop(self) -> None:
        parser = build_parser()

        self.assertTrue(parser.parse_args(["--status"]).status)
        self.assertTrue(parser.parse_args(["--stop"]).stop)
        self.assertTrue(parser.parse_args(["--settings-window"]).settings_window)


if __name__ == "__main__":
    unittest.main()
