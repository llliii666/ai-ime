from __future__ import annotations

import os
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_RUN_NAME = "AI IME"
LEGACY_APP_RUN_NAMES = ("AIIME",)


def default_startup_command(project_root: Path | None = None, python_executable: Path | None = None) -> str:
    if getattr(sys, "frozen", False):
        return f"{_quote_cmd_arg(Path(sys.executable))} --foreground"

    root = (project_root or default_project_root()).resolve()
    executable = (python_executable or default_pythonw_executable(root)).resolve()
    source_launcher = root / "run.py"
    if source_launcher.is_file():
        return f"{_quote_cmd_arg(executable)} {_quote_cmd_arg(source_launcher)}"
    return f"{_quote_cmd_arg(executable)} -m ai_ime.app"


def default_project_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "run.py").is_file() and (cwd / "ai_ime").is_dir():
        return cwd
    return Path(__file__).resolve().parent.parent


def default_pythonw_executable(project_root: Path | None = None) -> Path:
    root = (project_root or default_project_root()).resolve()
    venv_scripts = root / ".venv" / "Scripts"
    for candidate in (venv_scripts / "pythonw.exe", venv_scripts / "python.exe"):
        if candidate.exists():
            return candidate

    executable = Path(sys.executable)
    if os.name == "nt":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
    return executable


def set_start_on_login(enabled: bool, command: str | None = None) -> None:
    if os.name != "nt":
        return
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_RUN_NAME, 0, winreg.REG_SZ, command or default_startup_command())
            for legacy_name in LEGACY_APP_RUN_NAMES:
                try:
                    winreg.DeleteValue(key, legacy_name)
                except FileNotFoundError:
                    pass
        else:
            for name in (APP_RUN_NAME, *LEGACY_APP_RUN_NAMES):
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
        winreg.FlushKey(key)


def is_start_on_login_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            for name in (APP_RUN_NAME, *LEGACY_APP_RUN_NAMES):
                try:
                    winreg.QueryValueEx(key, name)
                    return True
                except FileNotFoundError:
                    continue
            return False
    except FileNotFoundError:
        return False


def startup_command_value() -> str:
    if os.name != "nt":
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            for name in (APP_RUN_NAME, *LEGACY_APP_RUN_NAMES):
                try:
                    value, _value_type = winreg.QueryValueEx(key, name)
                    return str(value or "")
                except FileNotFoundError:
                    continue
    except FileNotFoundError:
        return ""
    return ""


def sync_start_on_login(enabled: bool) -> bool:
    if os.name != "nt":
        return False
    if enabled:
        expected = default_startup_command()
        if startup_command_value() != expected:
            set_start_on_login(True, command=expected)
        return startup_command_value() == expected
    set_start_on_login(False)
    return False


def _quote_cmd_arg(value: Path | str) -> str:
    text = str(value)
    return '"' + text.replace('"', r'\"') + '"'
