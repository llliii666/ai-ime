from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from ai_ime.config import default_data_dir
from ai_ime.logging_utils import rotate_log_file
from ai_ime.runtime import (
    clear_pid_file,
    is_pid_running,
    pid_file_path,
    pid_record_matches_process,
    read_pid_record,
)
from ai_ime.startup import default_project_root, default_pythonw_executable


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.stop:
        return stop_background()
    if args.status:
        return print_status()
    if args.settings_window:
        from ai_ime.settings_window import main as settings_window_main

        settings_args: list[str] = []
        if args.settings_persistent:
            settings_args.append("--persistent")
        if args.settings_show_signal:
            settings_args.extend(["--show-signal", args.settings_show_signal])
        return int(settings_window_main(settings_args))
    if args.foreground:
        from ai_ime.tray import main as tray_main

        return int(tray_main([]))
    return start_background(force=args.force)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-ime-start", description="Start AI IME as a background tray app.")
    parser.add_argument("--foreground", action="store_true", help="Run the tray app in the current process.")
    parser.add_argument("--force", action="store_true", help="Start even if a previous pid file exists.")
    parser.add_argument("--status", action="store_true", help="Print background process status.")
    parser.add_argument("--stop", action="store_true", help="Stop the background tray process.")
    parser.add_argument("--settings-window", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--settings-persistent", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--settings-show-signal", default="", help=argparse.SUPPRESS)
    return parser


def start_background(force: bool = False) -> int:
    existing_record = read_pid_record()
    existing_pid = existing_record.pid if existing_record is not None else None
    if pid_record_matches_process(existing_record) and not force:
        print(f"AI IME already appears to be running with pid {existing_pid}.")
        return 0
    if existing_record is not None and not pid_record_matches_process(existing_record):
        clear_pid_file()

    log_file = default_data_dir() / "tray.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    rotate_log_file(log_file)
    with log_file.open("a", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            build_tray_command(),
            cwd=runtime_working_directory(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=_detached_creationflags(),
            close_fds=True,
        )
    runtime_pid = _wait_for_runtime_pid(process.pid)
    if not runtime_pid:
        print("AI IME did not start. Another instance may already be running, or startup failed.")
        print(f"Log file: {log_file}")
        return 1
    if runtime_pid and runtime_pid != process.pid:
        print(f"AI IME started in background with launcher pid {process.pid}; tray pid {runtime_pid}.")
    else:
        print(f"AI IME started in background with pid {process.pid}.")
    print(f"Runtime pid file: {pid_file_path()}")
    print(f"Log file: {log_file}")
    return 0


def print_status() -> int:
    record = read_pid_record()
    pid = record.pid if record is not None else None
    if pid_record_matches_process(record):
        print(f"AI IME is running with tray pid {pid}.")
        return 0
    print("AI IME is not running.")
    return 1


def stop_background() -> int:
    record = read_pid_record()
    pid = record.pid if record is not None else None
    if not pid:
        print("AI IME is not running.")
        return 0
    if not pid_record_matches_process(record):
        clear_pid_file()
        print("AI IME pid file was stale and has been cleared.")
        return 0
    _terminate_pid(pid)
    clear_pid_file()
    print(f"Stopped AI IME tray pid {pid}.")
    return 0


def build_tray_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable)), "--foreground"]
    return [_pythonw_executable(), "-m", "ai_ime.tray"]


def _pythonw_executable() -> str:
    return str(default_pythonw_executable(runtime_working_directory()))


def runtime_working_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return default_project_root().resolve()


def _detached_creationflags() -> int:
    if os.name != "nt":
        return 0
    return subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


def _wait_for_runtime_pid(launcher_pid: int, timeout: float = 5.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        runtime_record = read_pid_record()
        runtime_pid = runtime_record.pid if runtime_record is not None else None
        if pid_record_matches_process(runtime_record):
            return runtime_pid
        if not is_pid_running(launcher_pid):
            return 0
        time.sleep(0.1)
    return launcher_pid


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    os.kill(pid, signal.SIGTERM)


if __name__ == "__main__":
    raise SystemExit(main())
