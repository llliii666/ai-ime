import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_ime.setup_wizard import format_setup_result, run_initial_setup


class SetupWizardTests(unittest.TestCase):
    def test_dry_run_does_not_create_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_initial_setup(
                db_path=root / "ai-ime.db",
                env_path=root / ".env",
                settings_path=root / "settings.json",
                dry_run=True,
            )

            self.assertFalse((root / ".env").exists())
            self.assertFalse((root / "settings.json").exists())
            self.assertTrue(any(step.status == "DRY-RUN" for step in result.steps))

    def test_setup_creates_env_database_and_settings(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        old_provider = os.environ.get("AI_IME_PROVIDER")
        old_key = os.environ.get("AI_IME_OPENAI_API_KEY")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                os.environ["LOCALAPPDATA"] = str(root / "LocalAppData")
                os.environ.pop("AI_IME_PROVIDER", None)
                os.environ.pop("AI_IME_OPENAI_API_KEY", None)

                with patch("ai_ime.setup_wizard.find_existing_user_dir", return_value=None):
                    result = run_initial_setup(
                        db_path=root / "ai-ime.db",
                        env_path=root / ".env",
                        settings_path=root / "settings.json",
                        provider="mock",
                    )

                self.assertFalse(result.has_error)
                self.assertTrue((root / ".env").exists())
                self.assertTrue((root / "ai-ime.db").exists())
                self.assertTrue((root / "settings.json").exists())
                self.assertIn("Next: run", format_setup_result(result))
        finally:
            _restore_env("LOCALAPPDATA", old_local_app_data)
            _restore_env("AI_IME_PROVIDER", old_provider)
            _restore_env("AI_IME_OPENAI_API_KEY", old_key)


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


if __name__ == "__main__":
    unittest.main()
