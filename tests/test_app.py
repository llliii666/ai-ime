import unittest

from ai_ime.app import build_parser, build_tray_command


class AppEntryTests(unittest.TestCase):
    def test_build_tray_command_runs_tray_module(self) -> None:
        command = build_tray_command()

        self.assertIn("-m", command)
        self.assertIn("ai_ime.tray", command)

    def test_parser_supports_status_and_stop(self) -> None:
        parser = build_parser()

        self.assertTrue(parser.parse_args(["--status"]).status)
        self.assertTrue(parser.parse_args(["--stop"]).stop)


if __name__ == "__main__":
    unittest.main()
