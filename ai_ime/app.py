from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from ai_ime.config import default_data_dir
from ai_ime.runtime import is_pid_running, pid_file_path, read_pid_file


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.foreground:
        from ai_ime.tray import main as tray_main

        return int(tray_main([]))
    return start_background(force=args.force)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-ime-start", description="Start AI IME as a background tray app.")
    parser.add_argument("--foreground", action="store_true", help="Run the tray app in the current process.")
    parser.add_argument("--force", action="store_true", help="Start even if a previous pid file exists.")
    return parser


def start_background(force: bool = False) -> int:
    existing_pid = read_pid_file()
    if existing_pid and is_pid_running(existing_pid) and not force:
        print(f"AI IME already appears to be running with pid {existing_pid}.")
        return 0

    log_file = default_data_dir() / "tray.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            build_tray_command(),
            cwd=Path.cwd(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=_detached_creationflags(),
            close_fds=True,
        )
    print(f"AI IME started in background with pid {process.pid}.")
    print(f"Runtime pid file: {pid_file_path()}")
    print(f"Log file: {log_file}")
    return 0


def build_tray_command() -> list[str]:
    return [_pythonw_executable(), "-m", "ai_ime.tray"]


def _pythonw_executable() -> str:
    executable = Path(sys.executable)
    if os.name == "nt":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(executable)


def _detached_creationflags() -> int:
    if os.name != "nt":
        return 0
    return subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP


if __name__ == "__main__":
    raise SystemExit(main())
