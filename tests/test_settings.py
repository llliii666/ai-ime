import os
import tempfile
import unittest
from pathlib import Path

from ai_ime.settings import AppSettings, load_app_settings, save_app_settings, write_provider_env


class SettingsTests(unittest.TestCase):
    def test_save_and_load_app_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = AppSettings(record_full_keylog=False, rime_schema="double_pinyin")

            save_app_settings(settings, path)
            loaded = load_app_settings(path)

            self.assertFalse(loaded.record_full_keylog)
            self.assertEqual(loaded.rime_schema, "double_pinyin")

    def test_write_provider_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            settings = AppSettings(
                provider="openai-compatible",
                openai_base_url="http://example.test/v1",
                openai_model="gpt-5.4-mini",
            )

            write_provider_env(settings, api_key="test-key", path=path)
            content = path.read_text(encoding="utf-8")

            self.assertIn("AI_IME_PROVIDER=openai-compatible", content)
            self.assertIn("AI_IME_OPENAI_MODEL=gpt-5.4-mini", content)
            self.assertIn("AI_IME_OPENAI_API_KEY=test-key", content)

    def tearDown(self) -> None:
        os.environ.pop("AI_IME_PROVIDER", None)


if __name__ == "__main__":
    unittest.main()
