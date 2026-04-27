from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SHORTCUT_NAME = "AI IME"


@dataclass(frozen=True)
class ShortcutSpec:
    path: Path
    target: Path
    arguments: str
    working_directory: Path
    description: str
    icon_location: str


def create_desktop_shortcut(name: str = DEFAULT_SHORTCUT_NAME, shortcut_path: Path | None = None) -> ShortcutSpec:
    if os.name != "nt":
        raise RuntimeError("Desktop shortcuts are currently supported only on Windows.")
    spec = build_shortcut_spec(name=name, shortcut_path=shortcut_path)
    _create_windows_shortcut(spec)
    return spec


def build_shortcut_spec(
    name: str = DEFAULT_SHORTCUT_NAME,
    shortcut_path: Path | None = None,
    project_root: Path | None = None,
    desktop_dir: Path | None = None,
    python_executable: Path | None = None,
) -> ShortcutSpec:
    project_root = (project_root or default_project_root()).resolve()
    target = (python_executable or default_pythonw_executable(project_root)).resolve()
    path = shortcut_path or (desktop_dir or default_desktop_dir()) / f"{_shortcut_stem(name)}.lnk"
    return ShortcutSpec(
        path=path.resolve(),
        target=target,
        arguments="-m ai_ime.app",
        working_directory=project_root,
        description="启动 AI IME 托盘程序",
        icon_location=f"{target},0",
    )


def default_project_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "run.py").is_file() and (cwd / "ai_ime").is_dir():
        return cwd
    return Path(__file__).resolve().parent.parent


def default_pythonw_executable(project_root: Path) -> Path:
    venv_scripts = project_root / ".venv" / "Scripts"
    for candidate in (venv_scripts / "pythonw.exe", venv_scripts / "python.exe"):
        if candidate.exists():
            return candidate

    executable = Path(sys.executable)
    if os.name == "nt":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
    return executable


def default_desktop_dir() -> Path:
    if os.name == "nt":
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
            check=True,
            capture_output=True,
            text=True,
        )
        desktop = completed.stdout.strip()
        if desktop:
            return Path(desktop)
    return Path.home() / "Desktop"


def _create_windows_shortcut(spec: ShortcutSpec) -> None:
    script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            f"$ShortcutPath = {_ps_literal(str(spec.path))}",
            f"$TargetPath = {_ps_literal(str(spec.target))}",
            f"$Arguments = {_ps_literal(spec.arguments)}",
            f"$WorkingDirectory = {_ps_literal(str(spec.working_directory))}",
            f"$Description = {_ps_literal(spec.description)}",
            f"$IconLocation = {_ps_literal(spec.icon_location)}",
            "$Parent = Split-Path -Parent $ShortcutPath",
            "New-Item -ItemType Directory -Path $Parent -Force | Out-Null",
            "$Shell = New-Object -ComObject WScript.Shell",
            "$Shortcut = $Shell.CreateShortcut($ShortcutPath)",
            "$Shortcut.TargetPath = $TargetPath",
            "$Shortcut.Arguments = $Arguments",
            "$Shortcut.WorkingDirectory = $WorkingDirectory",
            "$Shortcut.Description = $Description",
            "$Shortcut.IconLocation = $IconLocation",
            "$Shortcut.Save()",
        ]
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )


def _shortcut_stem(name: str) -> str:
    stem = name.strip() or DEFAULT_SHORTCUT_NAME
    if stem.lower().endswith(".lnk"):
        stem = stem[:-4]
    return stem


def _ps_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
