from __future__ import annotations

import json
import threading
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_ime.config import default_data_dir, default_db_path
from ai_ime.correction.normalize import normalize_pinyin
from ai_ime.correction.rules import event_supports_rule
from ai_ime.db import connect, init_db, list_events, upsert_rules
from ai_ime.learning import _append_learning_log, _build_provider
from ai_ime.listener import KeyLogEntry, keyboard_name_to_stroke, keylog_file_lock
from ai_ime.models import CorrectionEvent, LearnedRule
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
    returned_rules: int = 0
    rejected_rules: int = 0
    sent_keylog_count: int = 0
    sent_event_count: int = 0
    deleted_keylog_bytes: int = 0
    rules: tuple[LearnedRule, ...] = ()
    rejected_rule_items: tuple[LearnedRule, ...] = ()


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

    def run_once(self, force: bool = False) -> AnalysisRunResult:
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

        if not self.settings.auto_analyze_with_ai and not force:
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, len(keylog_entries), len(new_events), next_interval, "AI analysis disabled")

        if not new_events and not keylog_entries and (not force or not events):
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, 0, 0, next_interval, "No new typing activity")

        keylog_payload = keylog_payload_for_settings(self.settings, keylog_entries)
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

        accepted_rules, rejected_rule_items = partition_rules_by_evidence(rules, events, keylog_payload)
        rejected = len(rejected_rule_items)
        with closing(connect(self.db_path)) as conn:
            init_db(conn)
            upserted = upsert_rules(conn, accepted_rules)
        max_event_id = max((event.id or 0 for event in events), default=state.last_analyzed_event_id)
        saved_keylog_offset = next_offset
        deleted_keylog_bytes = 0
        if self.settings.delete_sent_keylog and next_offset > 0:
            deleted_keylog_bytes = delete_keylog_prefix(resolved_keylog_path(self.settings), next_offset)
            if deleted_keylog_bytes:
                saved_keylog_offset = 0
        save_scheduler_state(
            AnalysisSchedulerState(
                last_keylog_offset=saved_keylog_offset,
                last_analyzed_event_id=max_event_id,
                next_interval_seconds=next_interval,
                last_run_at=time.time(),
            ),
            self.state_path,
        )
        _append_learning_log(
            "scheduled AI analysis "
            f"events={len(new_events)} keylogs={len(keylog_payload)}/{len(keylog_entries)} "
            f"rules={upserted} rejected={rejected} deleted_keylog_bytes={deleted_keylog_bytes} next={next_interval}s"
        )
        message = "AI analysis completed"
        if rejected:
            message += f"; rejected {rejected} unsupported rule(s)"
        return AnalysisRunResult(
            True,
            upserted,
            len(keylog_entries),
            len(new_events),
            next_interval,
            message,
            returned_rules=len(rules),
            rejected_rules=rejected,
            sent_keylog_count=len(keylog_payload),
            sent_event_count=len(events),
            deleted_keylog_bytes=deleted_keylog_bytes,
            rules=tuple(accepted_rules),
            rejected_rule_items=tuple(rejected_rule_items),
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            state = load_scheduler_state(self.state_path)
            interval = max(60, state.next_interval_seconds)
            if self._stop_event.wait(interval):
                return
            self.run_once()


def should_send_keylog_entries(settings: AppSettings) -> bool:
    return settings.provider == "ollama" or settings.send_full_keylog


def keylog_payload_for_settings(settings: AppSettings, entries: list[KeyLogEntry]) -> list[KeyLogEntry]:
    if should_send_keylog_entries(settings):
        return entries
    if settings.record_candidate_commits:
        return [entry for entry in entries if entry.event_type == "commit" or _is_semantic_edit_key(entry)]
    return []


def filter_rules_by_evidence(
    rules: list[LearnedRule],
    events: list[CorrectionEvent],
    keylog_entries: list[KeyLogEntry],
) -> list[LearnedRule]:
    accepted, _ = partition_rules_by_evidence(rules, events, keylog_entries)
    return accepted


def partition_rules_by_evidence(
    rules: list[LearnedRule],
    events: list[CorrectionEvent],
    keylog_entries: list[KeyLogEntry],
) -> tuple[list[LearnedRule], list[LearnedRule]]:
    supported = _supported_event_triples(events) | _supported_keylog_triples(keylog_entries)
    accepted: list[LearnedRule] = []
    rejected: list[LearnedRule] = []
    for rule in rules:
        triple = (
            normalize_pinyin(rule.wrong_pinyin),
            normalize_pinyin(rule.correct_pinyin),
            rule.committed_text.strip(),
        )
        if triple in supported:
            accepted.append(rule)
        else:
            rejected.append(rule)
    return accepted, rejected


def _supported_event_triples(events: list[CorrectionEvent]) -> set[tuple[str, str, str]]:
    triples: set[tuple[str, str, str]] = set()
    for event in events:
        if not event_supports_rule(event):
            continue
        triples.add(
            (
                normalize_pinyin(event.wrong_pinyin),
                normalize_pinyin(event.correct_pinyin),
                event.committed_text.strip(),
            )
        )
    return triples


def _supported_keylog_triples(entries: list[KeyLogEntry]) -> set[tuple[str, str, str]]:
    triples: set[tuple[str, str, str]] = set()
    candidate: KeyLogEntry | None = None
    last_rime_commit: KeyLogEntry | None = None
    saw_delete_after_last_rime_commit = False
    for entry in entries:
        if _is_semantic_edit_key(entry):
            saw_delete_after_last_rime_commit = last_rime_commit is not None
            continue
        if entry.event_type != "commit":
            continue
        if entry.role == "candidate":
            candidate = entry
            continue
        if entry.role == "correction" and candidate is not None:
            _add_supported_keylog_triple(triples, candidate, entry)
            candidate = None
            continue
        if _is_rime_commit(entry):
            if last_rime_commit is not None and saw_delete_after_last_rime_commit:
                _add_supported_keylog_triple(triples, last_rime_commit, entry)
            last_rime_commit = entry
            saw_delete_after_last_rime_commit = False
            continue
        candidate = None
    return triples


def _add_supported_keylog_triple(
    triples: set[tuple[str, str, str]],
    wrong_entry: KeyLogEntry,
    correct_entry: KeyLogEntry,
) -> None:
    wrong = normalize_pinyin(wrong_entry.pinyin or wrong_entry.name)
    correct = normalize_pinyin(correct_entry.pinyin or correct_entry.name)
    text = (correct_entry.committed_text or correct_entry.candidate_text or "").strip()
    if wrong and correct and text and wrong != correct:
        triples.add((wrong, correct, text))


def _is_rime_commit(entry: KeyLogEntry) -> bool:
    return entry.event_type == "commit" and (entry.role == "rime_commit" or entry.source == "rime-lua")


def _is_semantic_edit_key(entry: KeyLogEntry) -> bool:
    if entry.event_type != "down":
        return False
    stroke = keyboard_name_to_stroke(entry.name)
    return stroke is not None and stroke.kind in {"backspace", "delete"}


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
    entries: list[KeyLogEntry] = []
    with keylog_file_lock(path):
        size = path.stat().st_size
        if offset < 0 or offset > size:
            offset = 0
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


def delete_keylog_prefix(path: Path, offset: int) -> int:
    if offset <= 0 or not path.exists():
        return 0
    with keylog_file_lock(path):
        size = path.stat().st_size
        if offset >= size:
            path.write_text("", encoding="utf-8", newline="\n")
            return size
        with path.open("rb+") as handle:
            handle.seek(offset)
            remaining = handle.read()
            handle.seek(0)
            handle.write(remaining)
            handle.truncate()
        return offset


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
        source=_optional_str(payload.get("source")),
        candidate_text=_optional_str(payload.get("candidate_text")),
        candidate_comment=_optional_str(payload.get("candidate_comment")),
        selection_index=_optional_int(payload.get("selection_index")),
        commit_key=_optional_str(payload.get("commit_key")),
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
