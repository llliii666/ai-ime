import os
import tempfile
import unittest
from pathlib import Path

from ai_ime.config import env_value, load_env_file


class ConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("AI_IME_TEST_VALUE", None)
        os.environ.pop("AI_IME_TEST_OTHER", None)

    def test_load_env_file_sets_values_without_overriding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "AI_IME_TEST_VALUE='from-file'\nAI_IME_TEST_OTHER=plain\n",
                encoding="utf-8",
            )
            os.environ["AI_IME_TEST_VALUE"] = "existing"

            self.assertTrue(load_env_file(path))

            self.assertEqual(os.environ["AI_IME_TEST_VALUE"], "existing")
            self.assertEqual(os.environ["AI_IME_TEST_OTHER"], "plain")
            self.assertEqual(env_value("AI_IME_TEST_MISSING", "AI_IME_TEST_OTHER"), "plain")


if __name__ == "__main__":
    unittest.main()
