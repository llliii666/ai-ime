import unittest

from ai_ime.settings_window import _settings_html_path
from ai_ime.tray import build_settings_window_command


class SettingsWindowTests(unittest.TestCase):
    def test_settings_html_resource_exists(self) -> None:
        self.assertTrue(_settings_html_path().exists())

    def test_tray_opens_settings_window_module(self) -> None:
        command = build_settings_window_command()

        self.assertIn("-m", command)
        self.assertIn("ai_ime.settings_window", command)


if __name__ == "__main__":
    unittest.main()
