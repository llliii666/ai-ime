from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from ai_ime.config import default_data_dir, default_db_path
from ai_ime.correction.detector import CONFIRM_KEYS, CorrectionDetector, KeyStroke, PendingCorrection
from ai_ime.correction.rules import aggregate_rules, event_supports_rule
from ai_ime.db import connect, init_db, insert_event, list_events, list_rules, upsert_rules
from ai_ime.listener import KeyLogEntry, KeyLogWriter, keyboard_name_to_stroke
from ai_ime.logging_utils import rotate_log_file
from ai_ime.models import CorrectionEvent
from ai_ime.providers import MockProvider, OllamaProvider, OpenAICompatibleProvider, ProviderError
from ai_ime.rime.deploy import deploy_rime_files
from ai_ime.rime.weasel import run_weasel_deployer
from ai_ime.settings import AppSettings, resolved_keylog_path
from ai_ime.text_capture import FocusTextReader, extract_committed_text


@dataclass(frozen=True)
class AutoLearningResult:
    event: CorrectionEvent
    upserted_rules: int
    deployed: bool
    rime_redeployed: bool


class AutoLearningEngine:
    def __init__(
        self,
        settings: AppSettings,
        db_path: Path | None = None,
        text_reader: FocusTextReader | None = None,
        capture_delay: float = 0.35,
        async_finalize: bool = True,
        deployer: Callable[..., object] = deploy_rime_files,
        rime_redeployer: Callable[[], bool] = run_weasel_deployer,
    ) -> None:
        self.settings = settings
        self.db_path = db_path or default_db_path()
        self.text_reader = text_reader or FocusTextReader()
        self.capture_delay = capture_delay
        self.async_finalize = async_finalize
        self.deployer = deployer
        self.rime_redeployer = rime_redeployer
        self.detector = CorrectionDetector()
        self._lock = threading.Lock()
        self._candidate_commits: dict[str, str] = {}

    def handle_key_event(self, event_type: str, name: str) -> PendingCorrection | None:
        if event_type != "down" or not self.settings.auto_learn_enabled:
            return None
        stroke = keyboard_name_to_stroke(name)
        if stroke is None:
            return None
        return self.handle_stroke(stroke)

    def handle_stroke(self, stroke: KeyStroke) -> PendingCorrection | None:
        before_text = self.text_reader.read_text() if stroke.kind in CONFIRM_KEYS else None
        confirming_pinyin = self.detector.confirming_pinyin_candidate() if stroke.kind in CONFIRM_KEYS else ""
        with self._lock:
            pending = self.detector.feed_pending(stroke)
        if pending is None:
            if confirming_pinyin:
                self._schedule_commit_snapshot(confirming_pinyin, before_text, role="candidate")
            return None
        if self.async_finalize:
            timer = threading.Timer(self.capture_delay, self.finalize_pending, args=(pending, before_text))
            timer.daemon = True
            timer.start()
        else:
            self.finalize_pending(pending, before_text)
        return pending

    def _schedule_commit_snapshot(self, pinyin: str, before_text: str | None, role: str) -> None:
        if not self.settings.record_candidate_commits:
            return
        if self.async_finalize:
            timer = threading.Timer(self.capture_delay, self.finalize_commit_snapshot, args=(pinyin, before_text, role))
            timer.daemon = True
            timer.start()
        else:
            self.finalize_commit_snapshot(pinyin, before_text, role)

    def finalize_commit_snapshot(self, pinyin: str, before_text: str | None, role: str) -> str:
        if self.capture_delay > 0 and not self.async_finalize:
            time.sleep(self.capture_delay)
        committed_text = extract_committed_text(before_text, self.text_reader.read_text())
        if not committed_text:
            _append_learning_log(f"skip commit snapshot role={role} pinyin={pinyin}: committed text was not detected")
            return ""
        if role == "candidate":
            with self._lock:
                self.detector.note_wrong_committed_text(committed_text)
                self._candidate_commits[pinyin] = committed_text
        _append_semantic_keylog(
            resolved_keylog_path(self.settings),
            pinyin=pinyin,
            committed_text=committed_text,
            role=role,
        )
        return committed_text

    def finalize_pending(self, pending: PendingCorrection, before_text: str | None) -> AutoLearningResult | None:
        if self.capture_delay > 0 and not self.async_finalize:
            time.sleep(self.capture_delay)
        after_text = self.text_reader.read_text()
        committed_text = extract_committed_text(before_text, after_text)
        if not committed_text:
            _append_learning_log(
                f"skip pending={pending.wrong_pinyin}->{pending.correct_pinyin}: committed text was not detected"
            )
            return None
        event = pending.to_event(
            committed_text,
            source="auto-ui",
            wrong_committed_text=self._consume_candidate_commit(pending.wrong_pinyin)
            or pending.wrong_committed_text,
        )
        if event is None:
            return None
        if not event_supports_rule(event):
            _append_learning_log(
                f"skip pending={pending.wrong_pinyin}->{pending.correct_pinyin}: low-confidence automatic event"
            )
            return None
        if self.settings.record_candidate_commits:
            _append_semantic_keylog(
                resolved_keylog_path(self.settings),
                pinyin=pending.correct_pinyin,
                committed_text=committed_text,
                role="correction",
            )
        return self.learn_event(event)

    def learn_event(self, event: CorrectionEvent) -> AutoLearningResult:
        with closing(connect(self.db_path)) as conn:
            init_db(conn)
            insert_event(conn, event)
            events = list_events(conn)
            local_rules = aggregate_rules(events)
            upserted = upsert_rules(conn, local_rules)

        deployed = False
        rime_redeployed = False
        if self.settings.auto_deploy_rime and self.settings.rime_dir:
            with closing(connect(self.db_path)) as conn:
                init_db(conn)
                rules = list_rules(conn, enabled_only=True)
            self.deployer(
                rules,
                rime_dir=Path(self.settings.rime_dir),
                schema_id=self.settings.rime_schema,
                dictionary_id=self.settings.rime_dictionary,
                base_dictionary=self.settings.rime_base_dictionary,
                semantic_log_path=resolved_keylog_path(self.settings),
                semantic_logger_enabled=self.settings.record_candidate_commits,
            )
            deployed = True
            rime_redeployed = self.rime_redeployer()

        _append_learning_log(
            "learned "
            f"{event.wrong_pinyin}->{event.correct_pinyin}->{event.committed_text}; "
            f"rules={upserted}; deployed={deployed}; redeployed={rime_redeployed}"
        )
        return AutoLearningResult(
            event=event,
            upserted_rules=upserted,
            deployed=deployed,
            rime_redeployed=rime_redeployed,
        )

    def _consume_candidate_commit(self, pinyin: str) -> str:
        with self._lock:
            return self._candidate_commits.pop(pinyin, "")


def _build_provider(settings: AppSettings):
    if settings.provider == "mock":
        return MockProvider()
    if settings.provider == "ollama":
        return OllamaProvider(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            timeout=60.0,
        )
    if settings.provider == "openai-compatible":
        return OpenAICompatibleProvider(
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            api_key_env=settings.openai_api_key_env,
            timeout=60.0,
        )
    raise ProviderError(f"Unsupported provider: {settings.provider}")


def _append_learning_log(message: str) -> None:
    path = default_data_dir() / "learning.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_log_file(path)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _append_semantic_keylog(path: Path, pinyin: str, committed_text: str, role: str) -> None:
    KeyLogWriter(path).write(
        KeyLogEntry(
            timestamp=time.time(),
            event_type="commit",
            name=pinyin,
            pinyin=pinyin,
            committed_text=committed_text,
            role=role,
            source="auto-ui",
        )
    )
