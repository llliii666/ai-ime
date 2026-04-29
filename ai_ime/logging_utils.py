from __future__ import annotations

from pathlib import Path

DEFAULT_MAX_LOG_BYTES = 512 * 1024
DEFAULT_LOG_BACKUPS = 2


def rotate_log_file(
    path: Path,
    max_bytes: int = DEFAULT_MAX_LOG_BYTES,
    backups: int = DEFAULT_LOG_BACKUPS,
) -> bool:
    if max_bytes <= 0 or backups <= 0:
        return False
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        oldest = _backup_path(path, backups)
        if oldest.exists():
            oldest.unlink()
        for index in range(backups - 1, 0, -1):
            source = _backup_path(path, index)
            if source.exists():
                source.replace(_backup_path(path, index + 1))
        path.replace(_backup_path(path, 1))
        return True
    except OSError:
        return False


def _backup_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.{index}")
