from __future__ import annotations

import time
from pathlib import Path

from ai_ime.config import default_data_dir

SETTINGS_SHOW_SIGNAL_FILE = "settings-window-show.signal"
SETTINGS_UPDATED_SIGNAL_FILE = "settings-updated.signal"


def default_settings_show_signal_path() -> Path:
    return default_data_dir() / SETTINGS_SHOW_SIGNAL_FILE


def default_settings_updated_signal_path() -> Path:
    return default_data_dir() / SETTINGS_UPDATED_SIGNAL_FILE


def touch_signal(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(time.time()), encoding="ascii", newline="\n")
    return path
