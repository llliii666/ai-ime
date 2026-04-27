from __future__ import annotations

import atexit
import ctypes
import os
from pathlib import Path

from ai_ime.config import default_data_dir

PID_FILE_NAME = "ai-ime.pid"


def pid_file_path() -> Path:
    return default_data_dir() / PID_FILE_NAME


def write_pid_file(path: Path | None = None) -> Path:
    resolved = path or pid_file_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(clear_pid_file, resolved, os.getpid())
    return resolved


def read_pid_file(path: Path | None = None) -> int | None:
    resolved = path or pid_file_path()
    if not resolved.exists():
        return None
    try:
        return int(resolved.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def clear_pid_file(path: Path | None = None, expected_pid: int | None = None) -> None:
    resolved = path or pid_file_path()
    if not resolved.exists():
        return
    if expected_pid is not None and read_pid_file(resolved) != expected_pid:
        return
    resolved.unlink()


def is_pid_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        return _is_windows_pid_running(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _is_windows_pid_running(pid: int) -> bool:
    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)
