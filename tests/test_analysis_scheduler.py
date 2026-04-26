import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ai_ime.analysis_scheduler import (
    AdaptiveAnalysisScheduler,
    AnalysisSchedulerState,
    choose_next_interval,
    load_scheduler_state,
    read_keylog_entries_since,
    should_send_keylog_entries,
)
from ai_ime.db import connect, init_db, insert_event
from ai_ime.listener import KeyLogEntry, KeyLogWriter
from ai_ime.models import CorrectionEvent, LearnedRule
from ai_ime.settings import AppSettings


class FakeProvider:
    def __init__(self) -> None:
        self.keylog_count = 0

    def analyze_events(self, events, keylog_entries=None):
        self.keylog_count = len(keylog_entries or [])
        return [
            LearnedRule(
                wrong_pinyin="xainzai",
                correct_pinyin="xianzai",
                committed_text="现在",
                confidence=0.8,
                weight=141000,
                count=1,
                mistake_type="adjacent_transposition",
                provider="fake",
            )
        ]


class AnalysisSchedulerTests(unittest.TestCase):
    def test_choose_next_interval_by_activity(self) -> None:
        self.assertEqual(choose_next_interval(1200, 1800), 600)
        self.assertEqual(choose_next_interval(120, 1800), 1800)
        self.assertEqual(choose_next_interval(30, 1800), 3600)
        self.assertEqual(choose_next_interval(1, 1800), 7200)
        self.assertEqual(choose_next_interval(0, 1800), 3600)
        self.assertEqual(choose_next_interval(0, 43200), 43200)

    def test_should_send_keylogs_for_local_or_user_opt_in(self) -> None:
        self.assertTrue(should_send_keylog_entries(AppSettings(provider="ollama", send_full_keylog=False)))
        self.assertTrue(should_send_keylog_entries(AppSettings(provider="openai-compatible", send_full_keylog=True)))
        self.assertFalse(should_send_keylog_entries(AppSettings(provider="openai-compatible", send_full_keylog=False)))

    def test_read_keylog_entries_since_offset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keylog.jsonl"
            writer = KeyLogWriter(path)
            writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name="x"))
            offset = path.stat().st_size
            writer.write(KeyLogEntry(timestamp=2.0, event_type="down", name="y"))

            entries, next_offset = read_keylog_entries_since(path, offset)

            self.assertEqual([entry.name for entry in entries], ["y"])
            self.assertEqual(next_offset, path.stat().st_size)

    def test_run_once_batches_events_and_allowed_keylogs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            keylog_path = Path(tmp) / "keylog.jsonl"
            state_path = Path(tmp) / "analysis.json"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在", source="test"))
            KeyLogWriter(keylog_path).write(KeyLogEntry(timestamp=1.0, event_type="down", name="x"))
            provider = FakeProvider()
            settings = AppSettings(
                auto_analyze_with_ai=True,
                provider="openai-compatible",
                send_full_keylog=True,
                keylog_file=str(keylog_path),
            )
            scheduler = AdaptiveAnalysisScheduler(settings, db_path=db_path, state_path=state_path)

            with patch("ai_ime.analysis_scheduler._build_provider", return_value=provider), patch(
                "ai_ime.analysis_scheduler._append_learning_log"
            ):
                result = scheduler.run_once()

            state = load_scheduler_state(state_path)
            self.assertTrue(result.attempted)
            self.assertEqual(provider.keylog_count, 1)
            self.assertEqual(result.upserted_rules, 1)
            self.assertEqual(state.last_analyzed_event_id, 1)
            self.assertGreater(state.last_keylog_offset, 0)


if __name__ == "__main__":
    unittest.main()
