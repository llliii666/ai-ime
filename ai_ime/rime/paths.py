from __future__ import annotations

import os
from pathlib import Path


def candidate_user_dirs() -> list[Path]:
    candidates: list[Path] = []
    app_data = os.environ.get("APPDATA")
    if app_data:
        candidates.append(Path(app_data) / "Rime")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Rime")
    candidates.append(Path.home() / "AppData" / "Roaming" / "Rime")
    return _dedupe(candidates)


def find_existing_user_dir() -> Path | None:
    for candidate in candidate_user_dirs():
        if candidate.exists():
            return candidate
    return None


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique
