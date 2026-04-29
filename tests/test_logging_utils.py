import tempfile
import unittest
from pathlib import Path

from ai_ime.logging_utils import rotate_log_file


class LoggingUtilsTests(unittest.TestCase):
    def test_rotate_log_file_shifts_existing_backups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text("current", encoding="utf-8")
            path.with_name("app.log.1").write_text("previous", encoding="utf-8")

            rotated = rotate_log_file(path, max_bytes=1, backups=2)

            self.assertTrue(rotated)
            self.assertFalse(path.exists())
            self.assertEqual(path.with_name("app.log.1").read_text(encoding="utf-8"), "current")
            self.assertEqual(path.with_name("app.log.2").read_text(encoding="utf-8"), "previous")

    def test_rotate_log_file_keeps_small_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text("small", encoding="utf-8")

            rotated = rotate_log_file(path, max_bytes=1024, backups=2)

            self.assertFalse(rotated)
            self.assertEqual(path.read_text(encoding="utf-8"), "small")


if __name__ == "__main__":
    unittest.main()
