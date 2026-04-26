import os
import tempfile
import unittest
from pathlib import Path

from ai_ime.runtime import clear_pid_file, is_pid_running, read_pid_file, write_pid_file


class RuntimeTests(unittest.TestCase):
    def test_pid_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai-ime.pid"

            write_pid_file(path)
            self.assertEqual(read_pid_file(path), os.getpid())
            self.assertTrue(is_pid_running(os.getpid()))
            clear_pid_file(path, expected_pid=os.getpid())
            self.assertIsNone(read_pid_file(path))


if __name__ == "__main__":
    unittest.main()
