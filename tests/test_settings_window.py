import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_ime.settings_window import _settings_html_path, render_settings_html
from ai_ime.tray import SettingsWindowController, build_settings_window_command
from ai_ime.ui_api import SettingsApi


class SettingsWindowTests(unittest.TestCase):
    def test_settings_html_resource_exists(self) -> None:
        self.assertTrue(_settings_html_path().exists())

    def test_tray_opens_settings_window_module(self) -> None:
        command = build_settings_window_command()

        self.assertIn("-m", command)
        self.assertIn("ai_ime.settings_window", command)

    def test_tray_can_open_persistent_settings_window(self) -> None:
        signal_path = Path("show.signal")
        command = build_settings_window_command(signal_path=signal_path, persistent=True)

        self.assertIn("--persistent", command)
        self.assertEqual(command[-2:], ["--show-signal", str(signal_path)])

    def test_settings_window_controller_reuses_running_process(self) -> None:
        class FakeProcess:
            def poll(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            signal_path = Path(tmp) / "show.signal"
            controller = SettingsWindowController(signal_path=signal_path, command=["settings"])
            controller.process = FakeProcess()  # type: ignore[assignment]

            with patch("ai_ime.tray.open_settings_window_process") as opened:
                controller.open()

            opened.assert_not_called()
            self.assertTrue(signal_path.exists())

    def test_render_settings_html_inlines_assets_and_initial_state(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        old_key = os.environ.get("AI_IME_OPENAI_API_KEY")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                os.environ["AI_IME_OPENAI_API_KEY"] = "secret-value"
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=Path(tmp) / "ai-ime.db")

                html = render_settings_html(api)

            self.assertIn("<style>", html)
            self.assertIn('id="initial-state"', html)
            self.assertIn('id="recordList"', html)
            self.assertIn('id="provider_preset"', html)
            self.assertIn('id="model_select"', html)
            self.assertIn('id="providerTestState"', html)
            self.assertIn('id="runAnalysisNow"', html)
            self.assertIn('id="analysisNowResult"', html)
            self.assertIn('id="record_candidate_commits"', html)
            self.assertIn('id="delete_sent_keylog"', html)
            self.assertIn("已保存接口", html)
            self.assertIn("renderAnalysisNowResult", html)
            self.assertIn("renderSavedModelSummary", html)
            self.assertIn('setStatus("配置已就绪", "ok")', html)
            self.assertNotIn("renderModelSummary", html)
            self.assertIn("grid-template-rows: auto minmax(0, 1fr) auto", html)
            self.assertIn("overflow-y: auto", html)
            self.assertIn("z-index: 2000", html)
            self.assertIn("transform: translate(0, 0)", html)
            self.assertIn("<script>", html)
            self.assertNotIn('href="./settings.css"', html)
            self.assertNotIn('src="./settings.js"', html)
            self.assertNotIn("secret-value", html)
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data
            if old_key is None:
                os.environ.pop("AI_IME_OPENAI_API_KEY", None)
            else:
                os.environ["AI_IME_OPENAI_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
