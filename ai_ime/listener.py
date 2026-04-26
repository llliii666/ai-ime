from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Any

from ai_ime.correction.detector import CANDIDATE_SELECTION_KEYS, DELETE_KEYS, KeyStroke


class ListenerError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyLogEntry:
    timestamp: float
    event_type: str
    name: str
    scan_code: int | None = None
    pinyin: str | None = None
    committed_text: str | None = None
    role: str | None = None
    source: str | None = None
    candidate_text: str | None = None
    candidate_comment: str | None = None
    selection_index: int | None = None
    commit_key: str | None = None


class KeyLogWriter:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, entry: KeyLogEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with keylog_file_lock(self.path):
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                payload = {
                    key: value
                    for key, value in asdict(entry).items()
                    if value is not None and (not isinstance(value, str) or value or key in {"event_type", "name"})
                }
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


@contextmanager
def keylog_file_lock(path: Path, timeout: float = 3.0, stale_after: float = 30.0) -> Iterator[None]:
    lock_path = _keylog_lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    handle: int | None = None
    while handle is None:
        try:
            handle = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if _is_stale_lock(lock_path, stale_after):
                try:
                    lock_path.unlink()
                    continue
                except FileNotFoundError:
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for keylog lock: {lock_path}") from None
            time.sleep(0.025)
    try:
        os.write(handle, str(os.getpid()).encode("ascii", errors="ignore"))
        yield
    finally:
        os.close(handle)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _keylog_lock_path(path: Path) -> Path:
    suffix = f"{path.suffix}.lock" if path.suffix else ".lock"
    return path.with_suffix(suffix)


def _is_stale_lock(path: Path, stale_after: float) -> bool:
    try:
        age = time.time() - path.stat().st_mtime
    except FileNotFoundError:
        return False
    return age > stale_after


def keyboard_name_to_stroke(name: str) -> KeyStroke | None:
    normalized = name.lower().strip()
    candidate_key = _candidate_selection_key(normalized)
    if candidate_key is not None:
        return KeyStroke(candidate_key)
    if len(normalized) == 1 and normalized.isalpha():
        return KeyStroke("char", normalized)
    if normalized in DELETE_KEYS:
        return KeyStroke(normalized)
    if normalized in {"space", "enter"}:
        return KeyStroke(normalized)
    return None


def _candidate_selection_key(normalized_name: str) -> str | None:
    if normalized_name in CANDIDATE_SELECTION_KEYS:
        return normalized_name
    for prefix in ("num ", "numpad ", "number "):
        if normalized_name.startswith(prefix):
            suffix = normalized_name[len(prefix) :].strip()
            if suffix in CANDIDATE_SELECTION_KEYS:
                return suffix
    return None


def keylog_to_sequence(path: Path) -> str:
    parts: list[str] = []
    for entry in read_keylog(path):
        if entry.event_type != "down":
            continue
        stroke = keyboard_name_to_stroke(entry.name)
        if stroke is None:
            continue
        parts.append(_stroke_to_sequence_part(stroke))
    return "".join(parts)


def read_keylog(path: Path) -> list[KeyLogEntry]:
    entries: list[KeyLogEntry] = []
    if not path.exists():
        return entries
    with keylog_file_lock(path):
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    for line in lines:
        if not line.strip():
            continue
        payload = json.loads(line)
        entries.append(
            KeyLogEntry(
                timestamp=float(payload.get("timestamp", 0.0)),
                event_type=str(payload.get("event_type", "")),
                name=str(payload.get("name", "")),
                scan_code=payload.get("scan_code"),
                pinyin=payload.get("pinyin"),
                committed_text=payload.get("committed_text"),
                role=payload.get("role"),
                source=payload.get("source"),
                candidate_text=payload.get("candidate_text"),
                candidate_comment=payload.get("candidate_comment"),
                selection_index=_optional_int(payload.get("selection_index")),
                commit_key=payload.get("commit_key"),
            )
        )
    return entries


def run_keyboard_listener(
    log_file: Path,
    duration: float,
    stop_hotkey: str = "ctrl+alt+shift+p",
    echo: bool = False,
) -> int:
    try:
        import keyboard  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ListenerError("keyboard package is not installed. Run `uv add keyboard`.") from exc

    writer = KeyLogWriter(log_file)
    stop_event = Event()
    captured = 0

    def on_event(event: Any) -> None:
        nonlocal captured
        entry = KeyLogEntry(
            timestamp=time.time(),
            event_type=str(getattr(event, "event_type", "")),
            name=str(getattr(event, "name", "")),
            scan_code=getattr(event, "scan_code", None),
        )
        writer.write(entry)
        captured += 1
        if echo:
            print(f"{entry.event_type}: {entry.name}")

    hook = keyboard.hook(on_event)
    keyboard.add_hotkey(stop_hotkey, stop_event.set)
    started = time.monotonic()
    try:
        while not stop_event.is_set():
            if duration > 0 and time.monotonic() - started >= duration:
                break
            time.sleep(0.05)
    finally:
        keyboard.unhook(hook)
        keyboard.remove_hotkey(stop_hotkey)
    return captured


def _stroke_to_sequence_part(stroke: KeyStroke) -> str:
    if stroke.kind == "char":
        return stroke.value
    return f"{{{stroke.kind}}}"


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
