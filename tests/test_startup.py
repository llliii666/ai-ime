import unittest

from ai_ime.startup import default_startup_command


class StartupTests(unittest.TestCase):
    def test_default_startup_command_runs_tray_module(self) -> None:
        command = default_startup_command()

        self.assertIn("-m ai_ime.tray", command)


if __name__ == "__main__":
    unittest.main()
