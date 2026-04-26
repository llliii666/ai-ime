import unittest

from ai_ime.app import build_tray_command


class AppEntryTests(unittest.TestCase):
    def test_build_tray_command_runs_tray_module(self) -> None:
        command = build_tray_command()

        self.assertIn("-m", command)
        self.assertIn("ai_ime.tray", command)


if __name__ == "__main__":
    unittest.main()
