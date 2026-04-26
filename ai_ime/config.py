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
