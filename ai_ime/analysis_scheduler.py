from __future__ import annotations

import json
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_ime.config import default_data_dir, default_db_path
from ai_ime.db import connect, init_db, list_events, upsert_rules
from ai_ime.learning import _append_learning_log, _build_provider
from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent
from ai_ime.providers import ProviderError
from ai_ime.settings import AppSettings, resolved_keylog_path


INTERVAL_TIERS_SECONDS = (600, 1800, 3600, 7200, 18000, 28800, 43200)
DEFAULT_INTERVAL_SECONDS = 1800
MAX_KEYLOG_BATCH_ENTRIES = 5000
SCHEDULER_STATE_FILE = "analysis-scheduler.json"


@dataclass(frozen=True)
class AnalysisSchedulerState:
    last_keylog_offset: int = 0
    last_analyzed_event_id: int = 0
    next_interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    last_run_at: float = 0.0


@dataclass(frozen=True)
class AnalysisRunResult:
    attempted: bool
    upserted_rules: int
    keylog_count: int
    new_event_count: int
    next_interval_seconds: int
    message: str


class AdaptiveAnalysisScheduler:
    def __init__(
        self,
        settings: AppSettings,
        db_path: Path | None = None,
        state_path: Path | None = None,
    ) -> None:
        self.settings = settings
        self.db_path = db_path or default_db_path()
        self.state_path = state_path or default_data_dir() / SCHEDULER_STATE_FILE
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="AIIMEAnalysisScheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def run_once(self) -> AnalysisRunResult:
        state = load_scheduler_state(self.state_path)
        keylog_entries, next_offset = read_keylog_entries_since(resolved_keylog_path(self.settings), state.last_keylog_offset)
        with closing(connect(self.db_path)) as conn:
            init_db(conn)
            events = list_events(conn)
            new_events = [event for event in events if (event.id or 0) > state.last_analyzed_event_id]

        activity_count = len(keylog_entries) + len(new_events)
        next_interval = choose_next_interval(activity_count, state.next_interval_seconds)
        base_state = AnalysisSchedulerState(
            last_keylog_offset=next_offset,
            last_analyzed_event_id=state.last_analyzed_event_id,
            next_interval_seconds=next_interval,
            last_run_at=time.time(),
        )

        if not self.settings.auto_analyze_with_ai:
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, len(keylog_entries), len(new_events), next_interval, "AI analysis disabled")

        if not new_events and not keylog_entries:
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, 0, 0, next_interval, "No new typing activity")

        keylog_payload = keylog_entries if should_send_keylog_entries(self.settings) else []
        if not events and not keylog_payload:
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, len(keylog_entries), 0, next_interval, "No correction events to analyze")

        try:
            rules = _build_provider(self.settings).analyze_events(events, keylog_entries=keylog_payload)
        except ProviderError as exc:
            _append_learning_log(f"scheduled AI analysis failed: {exc}")
            save_scheduler_state(_failure_state(state, next_interval), self.state_path)
            return AnalysisRunResult(True, 0, len(keylog_entries), len(new_events), next_interval, str(exc))
        except Exception as exc:
            _append_learning_log(f"scheduled AI analysis failed: {exc}")
            save_scheduler_state(_failure_state(state, next_interval), self.state_path)
            return AnalysisRunResult(True, 0, len(keylog_entries), len(new_events), next_interval, str(exc))

        with closing(connect(self.db_path)) as conn:
            init_db(conn)
            upserted = upsert_rules(conn, rules)
        max_event_id = max((event.id or 0 for event in events), default=state.last_analyzed_event_id)
        save_scheduler_state(
            AnalysisSchedulerState(
                last_keylog_offset=next_offset,
                last_analyzed_event_id=max_event_id,
                next_interval_seconds=next_interval,
                last_run_at=time.time(),
            ),
            self.state_path,
        )
        _append_learning_log(
            "scheduled AI analysis "
            f"events={len(new_events)} keylogs={len(keylog_payload)}/{len(keylog_entries)} "
            f"rules={upserted} next={next_interval}s"
        )
        return AnalysisRunResult(True, upserted, len(keylog_entries), len(new_events), next_interval, "AI analysis completed")

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            state = load_scheduler_state(self.state_path)
            interval = max(60, state.next_interval_seconds)
            if self._stop_event.wait(interval):
                return
            self.run_once()


def should_send_keylog_entries(settings: AppSettings) -> bool:
    return settings.provider == "ollama" or settings.send_full_keylog


def _failure_state(previous: AnalysisSchedulerState, next_interval: int) -> AnalysisSchedulerState:
    return AnalysisSchedulerState(
        last_keylog_offset=previous.last_keylog_offset,
        last_analyzed_event_id=previous.last_analyzed_event_id,
        next_interval_seconds=next_interval,
        last_run_at=time.time(),
    )


def choose_next_interval(activity_count: int, current_interval: int = DEFAULT_INTERVAL_SECONDS) -> int:
    if activity_count <= 0:
        return _next_idle_interval(current_interval)
    if activity_count >= 1000:
        return 600
    if activity_count >= 100:
        return 1800
    if activity_count >= 20:
        return 3600
    return 7200


def read_keylog_entries_since(path: Path, offset: int, limit: int = MAX_KEYLOG_BATCH_ENTRIES) -> tuple[list[KeyLogEntry], int]:
    if not path.exists():
        return [], 0
    size = path.stat().st_size
    if offset < 0 or offset > size:
        offset = 0
    entries: list[KeyLogEntry] = []
    with path.open("rb") as handle:
        handle.seek(offset)
        for raw_line in handle:
            if len(entries) >= limit:
                break
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            entries.append(_keylog_entry_from_payload(payload))
        next_offset = handle.tell()
    return entries, next_offset


def load_scheduler_state(path: Path | None = None) -> AnalysisSchedulerState:
    state_path = path or default_data_dir() / SCHEDULER_STATE_FILE
    if not state_path.exists():
        return AnalysisSchedulerState()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return AnalysisSchedulerState()
    if not isinstance(payload, dict):
        return AnalysisSchedulerState()
    return AnalysisSchedulerState(
        last_keylog_offset=_as_int(payload.get("last_keylog_offset"), 0),
        last_analyzed_event_id=_as_int(payload.get("last_analyzed_event_id"), 0),
        next_interval_seconds=_normalize_interval(_as_int(payload.get("next_interval_seconds"), DEFAULT_INTERVAL_SECONDS)),
        last_run_at=float(payload.get("last_run_at") or 0.0),
    )


def save_scheduler_state(state: AnalysisSchedulerState, path: Path | None = None) -> Path:
    state_path = path or default_data_dir() / SCHEDULER_STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state.__dict__, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return state_path


def _keylog_entry_from_payload(payload: dict[str, Any]) -> KeyLogEntry:
    return KeyLogEntry(
        timestamp=float(payload.get("timestamp", 0.0)),
        event_type=str(payload.get("event_type", "")),
        name=str(payload.get("name", "")),
        scan_code=payload.get("scan_code"),
        pinyin=_optional_str(payload.get("pinyin")),
        committed_text=_optional_str(payload.get("committed_text")),
        role=_optional_str(payload.get("role")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _next_idle_interval(current_interval: int) -> int:
    current = _normalize_interval(current_interval)
    for tier in INTERVAL_TIERS_SECONDS:
        if tier > current:
            return tier
    return INTERVAL_TIERS_SECONDS[-1]


def _normalize_interval(value: int) -> int:
    for tier in INTERVAL_TIERS_SECONDS:
        if value <= tier:
            return tier
    return INTERVAL_TIERS_SECONDS[-1]


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default
