from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "AIIME"
DB_FILE_NAME = "ai-ime.db"


def default_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def default_db_path() -> Path:
    return default_data_dir() / DB_FILE_NAME


def load_env_file(path: Path, override: bool = False) -> bool:
    if not path.exists():
        return False
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _unquote_env_value(value.strip())
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value
    return True


def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
