from __future__ import annotations

import os
import re
from pathlib import Path

RIME_ICE_SCHEMA_ID = "rime_ice"


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


def detect_active_schema(rime_dir: Path) -> str | None:
    custom_path = rime_dir / "default.custom.yaml"
    default_path = rime_dir / "default.yaml"
    for path in (custom_path, default_path):
        schema = _read_first_schema(path)
        if schema:
            return schema
    return None


def detect_preferred_schema(rime_dir: Path) -> str | None:
    active = detect_active_schema(rime_dir)
    if active:
        return active
    if has_rime_ice_config(rime_dir):
        return RIME_ICE_SCHEMA_ID
    return None


def has_rime_ice_config(rime_dir: Path) -> bool:
    return has_schema(rime_dir, RIME_ICE_SCHEMA_ID) or (rime_dir / "rime_ice.dict.yaml").exists()


def has_schema(rime_dir: Path, schema_id: str) -> bool:
    return (rime_dir / f"{schema_id}.schema.yaml").exists()


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


def _read_first_schema(path: Path) -> str | None:
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8-sig")
    inline_match = re.search(r"\{\s*schema\s*:\s*([A-Za-z0-9_.-]+)\s*\}", content)
    if inline_match:
        return inline_match.group(1)
    block_match = re.search(r"^\s*-?\s*schema\s*:\s*([A-Za-z0-9_.-]+)\s*$", content, re.MULTILINE)
    if block_match:
        return block_match.group(1)
    return None
