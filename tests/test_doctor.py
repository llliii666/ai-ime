import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_ime.doctor import CheckResult, format_checks, has_error, run_checks


class DoctorTests(unittest.TestCase):
    def test_format_checks(self) -> None:
        output = format_checks([CheckResult("env", "OK", "provider mock")])

        self.assertEqual(output, "[OK] env: provider mock")

    def test_has_error(self) -> None:
        self.assertTrue(has_error([CheckResult("keyboard", "ERROR", "missing")]))
        self.assertFalse(has_error([CheckResult("env", "WARN", "missing key")]))

    def test_placeholder_openai_key_is_warning(self) -> None:
        env = {
            "AI_IME_PROVIDER": "openai-compatible",
            "AI_IME_OPENAI_BASE_URL": "https://api.openai.com/v1",
            "AI_IME_OPENAI_API_KEY": "replace-with-your-key",
        }

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", env, clear=True):
                with patch("ai_ime.doctor.find_existing_user_dir", return_value=None):
                    checks = run_checks(db_path=Path(tmp) / "ai-ime.db")

        env_check = next(check for check in checks if check.name == "env")
        self.assertEqual(env_check.status, "WARN")


if __name__ == "__main__":
    unittest.main()
