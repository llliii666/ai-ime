from __future__ import annotations

import inspect
import ipaddress
import json
import threading
import time
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ai_ime.config import default_data_dir, default_db_path
from ai_ime.correction.normalize import normalize_pinyin
from ai_ime.correction.rules import classify_mistake, event_supports_rule
from ai_ime.db import (
    connect,
    delete_rule,
    increment_rule_analysis_upload_counts,
    init_db,
    list_events,
    list_rules,
    upsert_rules,
)
from ai_ime.learning import _append_learning_log, _build_provider
from ai_ime.listener import KeyLogEntry, keyboard_name_to_stroke, keylog_file_lock
from ai_ime.models import CorrectionEvent, LearnedRule, ProviderAnalysis, RuleAuditFinding
from ai_ime.providers import ProviderError
from ai_ime.rime.deploy import deploy_rime_files
from ai_ime.rime.weasel import run_weasel_deployer
from ai_ime.settings import (
    AppSettings,
    normalize_analysis_count_threshold,
    normalize_analysis_schedule_mode,
    normalize_analysis_time_seconds,
    resolved_keylog_path,
)

INTERVAL_TIERS_SECONDS = (600, 1800, 3600, 7200, 18000, 28800, 43200)
DEFAULT_INTERVAL_SECONDS = 600
COUNT_MODE_POLL_INTERVAL_SECONDS = 600
MAX_KEYLOG_BATCH_ENTRIES = 5000
SCHEDULER_STATE_FILE = "analysis-scheduler.json"
MAX_RULE_ANALYSIS_UPLOAD_COUNT = 3


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
    sent_existing_rule_count: int = 0
    returned_invalid_rules: int = 0
    deleted_rules: int = 0
    invalid_rule_items: tuple[RuleAuditFinding, ...] = ()
    deployed: bool = False
    rime_redeployed: bool = False


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
            existing_rules = list_rules(conn)
            uploadable_existing_rules = list_rules(conn, max_analysis_upload_count=MAX_RULE_ANALYSIS_UPLOAD_COUNT)

        activity_count = len(keylog_entries) + len(new_events)
        next_interval = choose_next_interval_for_settings(self.settings, activity_count, state.next_interval_seconds)
        base_state = AnalysisSchedulerState(
            last_keylog_offset=next_offset,
            last_analyzed_event_id=state.last_analyzed_event_id,
            next_interval_seconds=next_interval,
            last_run_at=time.time(),
        )

        if not self.settings.auto_analyze_with_ai and not force:
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, len(keylog_entries), len(new_events), next_interval, "AI analysis disabled")

        if not new_events and not keylog_entries and (not force or (not events and not existing_rules)):
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, 0, 0, next_interval, "No new typing activity")

        if not force and should_wait_for_count_threshold(self.settings, activity_count):
            wait_state = AnalysisSchedulerState(
                last_keylog_offset=state.last_keylog_offset,
                last_analyzed_event_id=state.last_analyzed_event_id,
                next_interval_seconds=next_interval,
                last_run_at=time.time(),
            )
            save_scheduler_state(wait_state, self.state_path)
            threshold = normalize_analysis_count_threshold(self.settings.analysis_schedule_count_threshold)
            return AnalysisRunResult(
                False,
                0,
                len(keylog_entries),
                len(new_events),
                next_interval,
                f"Waiting for more typing activity ({activity_count}/{threshold})",
            )

        keylog_payload = keylog_payload_for_settings(self.settings, keylog_entries)
        events_for_provider = events_for_analysis(events, new_events, keylog_payload, force=force)
        rules_for_provider = uploadable_existing_rules if (events_for_provider or keylog_payload or force) else []
        if not events_for_provider and not keylog_payload and not rules_for_provider:
            save_scheduler_state(base_state, self.state_path)
            return AnalysisRunResult(False, 0, len(keylog_entries), 0, next_interval, "No correction events to analyze")

        try:
            provider_result = _analyze_with_provider(
                _build_provider(self.settings),
                events_for_provider,
                keylog_payload,
                rules_for_provider,
            )
        except ProviderError as exc:
            _append_learning_log(f"scheduled AI analysis failed: {exc}")
            save_scheduler_state(_failure_state(state, next_interval), self.state_path)
            return AnalysisRunResult(True, 0, len(keylog_entries), len(new_events), next_interval, str(exc))
        except Exception as exc:
            _append_learning_log(f"scheduled AI analysis failed: {exc}")
            save_scheduler_state(_failure_state(state, next_interval), self.state_path)
            return AnalysisRunResult(True, 0, len(keylog_entries), len(new_events), next_interval, str(exc))

        rules = list(provider_result.rules)
        accepted_rules, rejected_rule_items = partition_rules_by_evidence(rules, events_for_provider, keylog_payload)
        rejected = len(rejected_rule_items)
        deleted_rule_items: list[RuleAuditFinding]
        with closing(connect(self.db_path)) as conn:
            init_db(conn)
            increment_rule_analysis_upload_counts(conn, [rule.id for rule in rules_for_provider])
            upserted = upsert_rules(conn, accepted_rules)
            deleted_rule_items = delete_rules_from_audit_findings(conn, provider_result.invalid_rules, existing_rules)
            deleted_rules = len(deleted_rule_items)
        deployed = False
        rime_redeployed = False
        deploy_error = ""
        if (accepted_rules or deleted_rules) and self.settings.auto_deploy_rime and self.settings.rime_dir:
            try:
                deployed, rime_redeployed = _deploy_enabled_rules(self.settings, self.db_path)
            except Exception as exc:
                deploy_error = str(exc)
                _append_learning_log(f"scheduled AI analysis Rime deploy failed: {exc}")
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
            f"events={len(events_for_provider)}/{len(new_events)} keylogs={len(keylog_payload)}/{len(keylog_entries)} "
            f"existing_rules={len(rules_for_provider)} rules={upserted} rejected={rejected} "
            f"invalid_suggestions={len(provider_result.invalid_rules)} deleted_rules={deleted_rules} "
            f"deployed={deployed} redeployed={rime_redeployed} "
            f"deleted_keylog_bytes={deleted_keylog_bytes} next={next_interval}s"
        )
        message = "AI analysis completed"
        if rejected:
            message += f"; rejected {rejected} unsupported rule(s)"
        if deleted_rules:
            message += f"; deleted {deleted_rules} invalid rule(s)"
        if deployed:
            message += "; Rime rules deployed"
            if not rime_redeployed:
                message += "; manual Weasel redeploy may still be required"
        if deploy_error:
            message += f"; Rime deploy failed: {deploy_error}"
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
            sent_event_count=len(events_for_provider),
            deleted_keylog_bytes=deleted_keylog_bytes,
            rules=tuple(accepted_rules),
            rejected_rule_items=tuple(rejected_rule_items),
            sent_existing_rule_count=len(rules_for_provider),
            returned_invalid_rules=len(provider_result.invalid_rules),
            deleted_rules=deleted_rules,
            invalid_rule_items=tuple(deleted_rule_items),
            deployed=deployed,
            rime_redeployed=rime_redeployed,
        )

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            state = load_scheduler_state(self.state_path)
            interval = max(60, state.next_interval_seconds)
            if self._stop_event.wait(interval):
                return
            self.run_once()


def should_send_keylog_entries(settings: AppSettings) -> bool:
    if settings.send_full_keylog:
        return True
    if settings.provider != "ollama":
        return False
    return _is_loopback_base_url(settings.ollama_base_url)


def _is_loopback_base_url(base_url: str) -> bool:
    parsed = urlparse(base_url.strip())
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        return False
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _deploy_enabled_rules(settings: AppSettings, db_path: Path) -> tuple[bool, bool]:
    with closing(connect(db_path)) as conn:
        init_db(conn)
        rules = list_rules(conn, enabled_only=True)
    deploy_rime_files(
        rules,
        rime_dir=Path(settings.rime_dir),
        schema_id=settings.rime_schema,
        dictionary_id=settings.rime_dictionary,
        base_dictionary=settings.rime_base_dictionary,
        semantic_log_path=resolved_keylog_path(settings),
        semantic_logger_enabled=settings.record_candidate_commits,
    )
    return True, run_weasel_deployer()


def _analyze_with_provider(
    provider: object,
    events: list[CorrectionEvent],
    keylog_entries: list[KeyLogEntry],
    existing_rules: list[LearnedRule],
) -> ProviderAnalysis:
    analyze_events = provider.analyze_events
    kwargs: dict[str, object] = {"keylog_entries": keylog_entries}
    try:
        signature = inspect.signature(analyze_events)
    except (TypeError, ValueError):
        signature = None
    if signature is None or _accepts_keyword(signature, "existing_rules"):
        kwargs["existing_rules"] = existing_rules
    result = analyze_events(events, **kwargs)
    if isinstance(result, ProviderAnalysis):
        return result
    return ProviderAnalysis(rules=list(result), invalid_rules=())


def _accepts_keyword(signature: inspect.Signature, name: str) -> bool:
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            return True
        if parameter.name == name and parameter.kind in {
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        }:
            return True
    return False


def delete_rules_from_audit_findings(
    conn: Any,
    findings: Sequence[RuleAuditFinding],
    existing_rules: Sequence[LearnedRule],
) -> list[RuleAuditFinding]:
    rules_by_id = {rule.id: rule for rule in existing_rules if rule.id is not None}
    deleted: list[RuleAuditFinding] = []
    for finding in findings:
        if finding.action != "delete" or finding.rule_id is None:
            continue
        rule = rules_by_id.get(finding.rule_id)
        if rule is None or rule.id is None:
            continue
        if not _audit_finding_matches_rule(finding, rule):
            continue
        if delete_rule(conn, rule.id):
            deleted.append(finding)
    return deleted


def _audit_finding_matches_rule(finding: RuleAuditFinding, rule: LearnedRule) -> bool:
    return (
        normalize_pinyin(rule.wrong_pinyin) == normalize_pinyin(finding.wrong_pinyin)
        and normalize_pinyin(rule.correct_pinyin) == normalize_pinyin(finding.correct_pinyin)
        and rule.committed_text.strip() == finding.committed_text.strip()
    )


def keylog_payload_for_settings(settings: AppSettings, entries: list[KeyLogEntry]) -> list[KeyLogEntry]:
    if should_send_keylog_entries(settings):
        return entries
    if settings.record_candidate_commits:
        return [entry for entry in entries if entry.event_type == "commit" or _is_semantic_edit_key(entry)]
    return []


def events_for_analysis(
    all_events: list[CorrectionEvent],
    new_events: list[CorrectionEvent],
    keylog_payload: list[KeyLogEntry],
    force: bool = False,
) -> list[CorrectionEvent]:
    if new_events:
        return new_events
    if keylog_payload:
        return []
    if force:
        return all_events
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
    mistake_type = classify_mistake(wrong, correct)
    if wrong and correct and text and wrong != correct and mistake_type != "unknown" and min(len(wrong), len(correct)) >= 3:
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


def choose_next_interval_for_settings(
    settings: AppSettings,
    activity_count: int,
    current_interval: int = DEFAULT_INTERVAL_SECONDS,
) -> int:
    mode = normalize_analysis_schedule_mode(settings.analysis_schedule_mode)
    if mode == "count":
        return COUNT_MODE_POLL_INTERVAL_SECONDS
    fixed_seconds = normalize_analysis_time_seconds(settings.analysis_schedule_time_seconds)
    if fixed_seconds > 0:
        return fixed_seconds
    return choose_next_interval(activity_count, current_interval)


def should_wait_for_count_threshold(settings: AppSettings, activity_count: int) -> bool:
    if normalize_analysis_schedule_mode(settings.analysis_schedule_mode) != "count":
        return False
    return activity_count < normalize_analysis_count_threshold(settings.analysis_schedule_count_threshold)


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
