from __future__ import annotations

import atexit
import ctypes
import ctypes.wintypes
import json
import os
from dataclasses import dataclass
from pathlib import Path

from ai_ime.config import default_data_dir

PID_FILE_NAME = "ai-ime.pid"
_SINGLE_INSTANCE_HANDLE: int | None = None


@dataclass(frozen=True)
class PidRecord:
    pid: int
    started_at: int | None = None


def pid_file_path() -> Path:
    return default_data_dir() / PID_FILE_NAME


def write_pid_file(path: Path | None = None) -> Path:
    resolved = path or pid_file_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    record = PidRecord(pid=os.getpid(), started_at=process_started_at(os.getpid()))
    resolved.write_text(json.dumps({"pid": record.pid, "started_at": record.started_at}), encoding="utf-8")
    atexit.register(clear_pid_file, resolved, record.pid, record.started_at)
    return resolved


def read_pid_file(path: Path | None = None) -> int | None:
    record = read_pid_record(path)
    return record.pid if record is not None else None


def read_pid_record(path: Path | None = None) -> PidRecord | None:
    resolved = path or pid_file_path()
    if not resolved.exists():
        return None
    raw = resolved.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            return PidRecord(pid=int(raw))
        except ValueError:
            return None
    if isinstance(payload, int):
        return PidRecord(pid=payload)
    if not isinstance(payload, dict):
        return None
    pid = payload.get("pid")
    started_at = payload.get("started_at")
    if not isinstance(pid, int):
        return None
    if started_at is not None and not isinstance(started_at, int):
        return None
    return PidRecord(pid=pid, started_at=started_at)


def clear_pid_file(
    path: Path | None = None,
    expected_pid: int | None = None,
    expected_started_at: int | None = None,
) -> None:
    resolved = path or pid_file_path()
    if not resolved.exists():
        return
    record = read_pid_record(resolved)
    if expected_pid is not None and (record is None or record.pid != expected_pid):
        return
    if expected_started_at is not None and record is not None and record.started_at != expected_started_at:
        return
    resolved.unlink()


def acquire_single_instance(name: str = "AI IME Tray") -> bool:
    global _SINGLE_INSTANCE_HANDLE
    if os.name != "nt":
        return True
    if _SINGLE_INSTANCE_HANDLE:
        return True

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return True
    already_exists = kernel32.GetLastError() == 183
    if already_exists:
        kernel32.CloseHandle(handle)
        return False
    _SINGLE_INSTANCE_HANDLE = handle
    atexit.register(_release_single_instance)
    return True


def _release_single_instance() -> None:
    global _SINGLE_INSTANCE_HANDLE
    if not _SINGLE_INSTANCE_HANDLE or os.name != "nt":
        return
    ctypes.windll.kernel32.CloseHandle(_SINGLE_INSTANCE_HANDLE)
    _SINGLE_INSTANCE_HANDLE = None


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


def pid_record_matches_process(record: PidRecord | None) -> bool:
    if record is None or not is_pid_running(record.pid):
        return False
    if record.started_at is None:
        return True
    return process_started_at(record.pid) == record.started_at


def process_started_at(pid: int) -> int | None:
    if pid <= 0:
        return None
    if os.name != "nt":
        return None
    process_query_limited_information = 0x1000
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        creation_time = ctypes.wintypes.FILETIME()
        exit_time = ctypes.wintypes.FILETIME()
        kernel_time = ctypes.wintypes.FILETIME()
        user_time = ctypes.wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation_time),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return None
        return (creation_time.dwHighDateTime << 32) | creation_time.dwLowDateTime
    finally:
        kernel32.CloseHandle(handle)
