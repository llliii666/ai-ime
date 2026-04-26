import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ai_ime.analysis_scheduler import (
    AdaptiveAnalysisScheduler,
    choose_next_interval,
    delete_keylog_prefix,
    events_for_analysis,
    filter_rules_by_evidence,
    keylog_payload_for_settings,
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
        self.event_count = 0

    def analyze_events(self, events, keylog_entries=None):
        self.event_count = len(events or [])
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

    def test_keylog_payload_can_send_semantic_commits_without_raw_keys(self) -> None:
        entries = [
            KeyLogEntry(timestamp=1.0, event_type="down", name="x"),
            KeyLogEntry(
                timestamp=2.0,
                event_type="commit",
                name="xianzai",
                pinyin="xianzai",
                committed_text="现在",
                role="correction",
            ),
        ]

        payload = keylog_payload_for_settings(
            AppSettings(provider="openai-compatible", send_full_keylog=False, record_candidate_commits=True),
            entries,
        )

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0].event_type, "commit")

    def test_keylog_payload_keeps_rime_delete_between_semantic_commits(self) -> None:
        entries = [
            KeyLogEntry(
                timestamp=1.0,
                event_type="commit",
                name="xainzai",
                pinyin="xainzai",
                committed_text="喜爱能在",
                role="rime_commit",
                source="rime-lua",
            ),
            KeyLogEntry(timestamp=2.0, event_type="down", name="backspace", role="rime_edit", source="rime-lua"),
            KeyLogEntry(
                timestamp=3.0,
                event_type="commit",
                name="xianzai",
                pinyin="xianzai",
                committed_text="现在",
                role="rime_commit",
                source="rime-lua",
            ),
        ]

        payload = keylog_payload_for_settings(
            AppSettings(provider="openai-compatible", send_full_keylog=False, record_candidate_commits=True),
            entries,
        )

        self.assertEqual([entry.name for entry in payload], ["xainzai", "backspace", "xianzai"])

    def test_events_for_analysis_does_not_mix_old_events_into_keylog_batch(self) -> None:
        old_event = CorrectionEvent("xainzai", "xianzai", "现在", id=1)
        keylog = [KeyLogEntry(timestamp=1.0, event_type="commit", name="keneneg", committed_text="可讷讷给")]

        self.assertEqual(events_for_analysis([old_event], [], keylog, force=True), [])
        self.assertEqual(events_for_analysis([old_event], [], [], force=True), [old_event])
        self.assertEqual(events_for_analysis([old_event], [old_event], keylog, force=False), [old_event])

    def test_rime_commit_delete_commit_sequence_supports_ai_rule(self) -> None:
        entries = [
            KeyLogEntry(
                timestamp=1.0,
                event_type="commit",
                name="xainzai",
                pinyin="xainzai",
                committed_text="喜爱能在",
                role="rime_commit",
                source="rime-lua",
            ),
            KeyLogEntry(timestamp=2.0, event_type="down", name="delete", role="rime_edit", source="rime-lua"),
            KeyLogEntry(
                timestamp=3.0,
                event_type="commit",
                name="xianzai",
                pinyin="xianzai",
                committed_text="现在",
                role="rime_commit",
                source="rime-lua",
            ),
        ]
        rules = [
            LearnedRule(
                wrong_pinyin="xainzai",
                correct_pinyin="xianzai",
                committed_text="现在",
                confidence=0.85,
                weight=145000,
                count=1,
                mistake_type="semantic_correction",
                provider="fake",
            )
        ]

        accepted = filter_rules_by_evidence(rules, events=[], keylog_entries=entries)

        self.assertEqual(accepted, rules)

    def test_distant_rime_commit_sequence_does_not_support_ai_rule(self) -> None:
        entries = [
            KeyLogEntry(
                timestamp=1.0,
                event_type="commit",
                name="gongneng",
                pinyin="gongneng",
                committed_text="功能",
                role="rime_commit",
                source="rime-lua",
            ),
            KeyLogEntry(timestamp=2.0, event_type="down", name="delete", role="rime_edit", source="rime-lua"),
            KeyLogEntry(
                timestamp=3.0,
                event_type="commit",
                name="haishi",
                pinyin="haishi",
                committed_text="还是",
                role="rime_commit",
                source="rime-lua",
            ),
        ]
        rules = [
            LearnedRule(
                wrong_pinyin="gongneng",
                correct_pinyin="haishi",
                committed_text="还是",
                confidence=0.85,
                weight=145000,
                count=1,
                mistake_type="semantic_correction",
                provider="fake",
            )
        ]

        accepted = filter_rules_by_evidence(rules, events=[], keylog_entries=entries)

        self.assertEqual(accepted, [])

    def test_read_keylog_entries_since_offset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keylog.jsonl"
            writer = KeyLogWriter(path)
            writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name="x"))
            offset = path.stat().st_size
            writer.write(
                KeyLogEntry(
                    timestamp=2.0,
                    event_type="commit",
                    name="xianzai",
                    pinyin="xianzai",
                    committed_text="现在",
                    role="correction",
                )
            )

            entries, next_offset = read_keylog_entries_since(path, offset)

            self.assertEqual([entry.name for entry in entries], ["xianzai"])
            self.assertEqual(entries[0].committed_text, "现在")
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
            self.assertEqual(provider.event_count, 1)
            self.assertEqual(provider.keylog_count, 1)
            self.assertEqual(result.upserted_rules, 1)
            self.assertEqual(result.returned_rules, 1)
            self.assertEqual(result.rejected_rules, 0)
            self.assertEqual(result.sent_event_count, 1)
            self.assertEqual(result.sent_keylog_count, 1)
            self.assertEqual(state.last_analyzed_event_id, 1)
            self.assertEqual(state.last_keylog_offset, 0)
            self.assertEqual(keylog_path.read_text(encoding="utf-8"), "")

    def test_run_once_with_keylog_does_not_resend_old_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            keylog_path = Path(tmp) / "keylog.jsonl"
            state_path = Path(tmp) / "analysis.json"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                event_id = insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在", source="manual-ui"))
            state_path.write_text(
                f'{{"last_keylog_offset":0,"last_analyzed_event_id":{event_id},"next_interval_seconds":1800,"last_run_at":0}}',
                encoding="utf-8",
            )
            KeyLogWriter(keylog_path).write(
                KeyLogEntry(
                    timestamp=1.0,
                    event_type="commit",
                    name="keneneg",
                    pinyin="keneneg",
                    committed_text="可讷讷给",
                    role="rime_commit",
                    source="rime-lua",
                )
            )
            provider = FakeProvider()
            settings = AppSettings(
                auto_analyze_with_ai=True,
                provider="openai-compatible",
                send_full_keylog=True,
                delete_sent_keylog=False,
                keylog_file=str(keylog_path),
            )
            scheduler = AdaptiveAnalysisScheduler(settings, db_path=db_path, state_path=state_path)

            with patch("ai_ime.analysis_scheduler._build_provider", return_value=provider), patch(
                "ai_ime.analysis_scheduler._append_learning_log"
            ):
                result = scheduler.run_once(force=True)

            self.assertTrue(result.attempted)
            self.assertEqual(provider.event_count, 0)
            self.assertEqual(provider.keylog_count, 1)
            self.assertEqual(result.sent_event_count, 0)

    def test_delete_keylog_prefix_preserves_unsent_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keylog.jsonl"
            writer = KeyLogWriter(path)
            writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name="x"))
            offset = path.stat().st_size
            writer.write(KeyLogEntry(timestamp=2.0, event_type="down", name="y"))

            deleted = delete_keylog_prefix(path, offset)
            entries = read_keylog_entries_since(path, 0)[0]

            self.assertEqual(deleted, offset)
            self.assertEqual([entry.name for entry in entries], ["y"])

    def test_run_once_rejects_provider_rules_without_supported_evidence(self) -> None:
        class MixedProvider:
            def analyze_events(self, events, keylog_entries=None):
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
                    ),
                    LearnedRule(
                        wrong_pinyin="hen",
                        correct_pinyin="n",
                        committed_text="很",
                        confidence=0.9,
                        weight=150000,
                        count=1,
                        mistake_type="unknown",
                        provider="fake",
                    ),
                ]

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            keylog_path = Path(tmp) / "keylog.jsonl"
            state_path = Path(tmp) / "analysis.json"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在", source="auto-ui"))
                insert_event(conn, CorrectionEvent("hen", "n", "很", source="auto-ui"))
            settings = AppSettings(
                auto_analyze_with_ai=True,
                provider="openai-compatible",
                keylog_file=str(keylog_path),
            )
            scheduler = AdaptiveAnalysisScheduler(settings, db_path=db_path, state_path=state_path)

            with patch("ai_ime.analysis_scheduler._build_provider", return_value=MixedProvider()), patch(
                "ai_ime.analysis_scheduler._append_learning_log"
            ):
                result = scheduler.run_once()

            self.assertTrue(result.attempted)
            self.assertEqual(result.returned_rules, 2)
            self.assertEqual(result.upserted_rules, 1)
            self.assertEqual(result.rejected_rules, 1)
            self.assertEqual(result.rules[0].wrong_pinyin, "xainzai")
            self.assertEqual(result.rejected_rule_items[0].wrong_pinyin, "hen")

    def test_run_once_keeps_keylog_offset_when_provider_fails(self) -> None:
        class FailingProvider:
            def analyze_events(self, events, keylog_entries=None):
                raise RuntimeError("provider down")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            keylog_path = Path(tmp) / "keylog.jsonl"
            state_path = Path(tmp) / "analysis.json"
            with closing(connect(db_path)) as conn:
                init_db(conn)
                insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在", source="test"))
            KeyLogWriter(keylog_path).write(KeyLogEntry(timestamp=1.0, event_type="down", name="x"))
            settings = AppSettings(
                auto_analyze_with_ai=True,
                provider="openai-compatible",
                send_full_keylog=True,
                keylog_file=str(keylog_path),
            )
            scheduler = AdaptiveAnalysisScheduler(settings, db_path=db_path, state_path=state_path)

            with patch("ai_ime.analysis_scheduler._build_provider", return_value=FailingProvider()), patch(
                "ai_ime.analysis_scheduler._append_learning_log"
            ):
                result = scheduler.run_once()

            state = load_scheduler_state(state_path)
            self.assertTrue(result.attempted)
            self.assertEqual(state.last_keylog_offset, 0)
            self.assertEqual(state.last_analyzed_event_id, 0)


if __name__ == "__main__":
    unittest.main()
