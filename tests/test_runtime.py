import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_ime.runtime import acquire_single_instance, clear_pid_file, is_pid_running, read_pid_file, write_pid_file


class FakeKernel32:
    def __init__(self, last_error: int = 0) -> None:
        self.last_error = last_error
        self.closed: list[int] = []

    def CreateMutexW(self, security_attributes: object, initial_owner: bool, name: str) -> int:
        return 42

    def GetLastError(self) -> int:
        return self.last_error

    def CloseHandle(self, handle: int) -> None:
        self.closed.append(handle)


class FakeWindll:
    def __init__(self, kernel32: FakeKernel32) -> None:
        self.kernel32 = kernel32


class RuntimeTests(unittest.TestCase):
    def test_pid_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai-ime.pid"

            write_pid_file(path)
            self.assertEqual(read_pid_file(path), os.getpid())
            self.assertTrue(is_pid_running(os.getpid()))
            clear_pid_file(path, expected_pid=os.getpid())
            self.assertIsNone(read_pid_file(path))

    def test_windows_single_instance_mutex_rejects_existing_instance(self) -> None:
        kernel32 = FakeKernel32(last_error=183)
        with (
            patch("ai_ime.runtime.os.name", "nt"),
            patch("ai_ime.runtime.ctypes.windll", FakeWindll(kernel32), create=True),
            patch("ai_ime.runtime._SINGLE_INSTANCE_HANDLE", None),
        ):
            acquired = acquire_single_instance()

        self.assertFalse(acquired)
        self.assertEqual(kernel32.closed, [42])


if __name__ == "__main__":
    unittest.main()
