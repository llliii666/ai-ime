from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Any

from ai_ime.correction.detector import DELETE_KEYS, KeyStroke


class ListenerError(RuntimeError):
    pass


@dataclass(frozen=True)
class KeyLogEntry:
    timestamp: float
    event_type: str
    name: str
    scan_code: int | None = None


class KeyLogWriter:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, entry: KeyLogEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")


def keyboard_name_to_stroke(name: str) -> KeyStroke | None:
    normalized = name.lower().strip()
    if len(normalized) == 1 and normalized.isalpha():
        return KeyStroke("char", normalized)
    if normalized in DELETE_KEYS:
        return KeyStroke(normalized)
    if normalized in {"space", "enter"}:
        return KeyStroke(normalized)
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
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        entries.append(
            KeyLogEntry(
                timestamp=float(payload.get("timestamp", 0.0)),
                event_type=str(payload.get("event_type", "")),
                name=str(payload.get("name", "")),
                scan_code=payload.get("scan_code"),
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
