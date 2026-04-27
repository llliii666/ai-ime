from __future__ import annotations

from importlib import resources
from pathlib import Path


def app_icon_path() -> Path:
    return Path(str(resources.files("ai_ime") / "assets" / "app.ico")).resolve()


def app_icon_svg() -> str:
    path = Path(str(resources.files("ai_ime") / "assets" / "app-icon.svg"))
    return path.read_text(encoding="utf-8")
