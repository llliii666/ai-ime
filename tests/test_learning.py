import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ai_ime.correction.detector import parse_sequence
from ai_ime.db import connect, init_db, list_events, list_rules
from ai_ime.learning import AutoLearningEngine
from ai_ime.listener import read_keylog
from ai_ime.settings import AppSettings


class FakeTextReader:
    def __init__(self, values: list[str | None]) -> None:
        self.values = values

    def read_text(self) -> str | None:
        if not self.values:
            return None
        return self.values.pop(0)


class LearningTests(unittest.TestCase):
    def test_engine_learns_detected_correction_from_focused_text_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            settings = AppSettings(auto_deploy_rime=False, auto_analyze_with_ai=False)
            engine = AutoLearningEngine(
                settings,
                db_path=db_path,
                text_reader=FakeTextReader(["我", "我现在"]),
                capture_delay=0,
                async_finalize=False,
            )

            with patch("ai_ime.learning._append_learning_log"):
                for stroke in parse_sequence("xainzai{backspace*7}xianzai{space}"):
                    engine.handle_stroke(stroke)

            with closing(connect(db_path)) as conn:
                init_db(conn)
                events = list_events(conn)
                rules = list_rules(conn)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].committed_text, "现在")
            self.assertEqual(events[0].source, "auto-ui")
            self.assertEqual(len(rules), 1)
            self.assertEqual(rules[0].wrong_pinyin, "xainzai")

    def test_engine_learns_when_candidate_number_confirms_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            settings = AppSettings(auto_deploy_rime=False, auto_analyze_with_ai=False)
            engine = AutoLearningEngine(
                settings,
                db_path=db_path,
                text_reader=FakeTextReader(["我", "我现在"]),
                capture_delay=0,
                async_finalize=False,
            )

            with patch("ai_ime.learning._append_learning_log"):
                for stroke in parse_sequence("xainzai{backspace*7}xianzai{1}"):
                    engine.handle_stroke(stroke)

            with closing(connect(db_path)) as conn:
                init_db(conn)
                events = list_events(conn)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].committed_text, "现在")
            self.assertEqual(events[0].commit_key, "1")

    def test_engine_records_wrong_and_correct_candidate_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            keylog_path = Path(tmp) / "keylog.jsonl"
            settings = AppSettings(
                auto_deploy_rime=False,
                auto_analyze_with_ai=False,
                record_full_keylog=True,
                keylog_file=str(keylog_path),
            )
            engine = AutoLearningEngine(
                settings,
                db_path=db_path,
                text_reader=FakeTextReader(["我", "我喜爱能在", "我", "我现在"]),
                capture_delay=0,
                async_finalize=False,
            )

            with patch("ai_ime.learning._append_learning_log"):
                for stroke in parse_sequence("xainzai{1}{backspace*4}xianzai{space}"):
                    engine.handle_stroke(stroke)

            with closing(connect(db_path)) as conn:
                init_db(conn)
                events = list_events(conn)

            keylog_entries = read_keylog(keylog_path)
            semantic_entries = [entry for entry in keylog_entries if entry.event_type == "commit"]
            self.assertEqual(events[0].wrong_committed_text, "喜爱能在")
            self.assertEqual(events[0].committed_text, "现在")
            self.assertEqual([(entry.role, entry.pinyin, entry.committed_text) for entry in semantic_entries], [
                ("candidate", "xainzai", "喜爱能在"),
                ("correction", "xianzai", "现在"),
            ])

    def test_engine_skips_low_confidence_auto_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            settings = AppSettings(auto_deploy_rime=False, auto_analyze_with_ai=False)
            engine = AutoLearningEngine(
                settings,
                db_path=db_path,
                text_reader=FakeTextReader(["我", "我很"]),
                capture_delay=0,
                async_finalize=False,
            )

            with patch("ai_ime.learning._append_learning_log"):
                for stroke in parse_sequence("hen{backspace*3}n{space}"):
                    engine.handle_stroke(stroke)

            with closing(connect(db_path)) as conn:
                init_db(conn)
                self.assertEqual(list_events(conn), [])
                self.assertEqual(list_rules(conn), [])

    def test_engine_skips_when_committed_text_is_not_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "ai-ime.db"
            settings = AppSettings(auto_deploy_rime=False, auto_analyze_with_ai=False)
            engine = AutoLearningEngine(
                settings,
                db_path=db_path,
                text_reader=FakeTextReader(["我", "我"]),
                capture_delay=0,
                async_finalize=False,
            )

            with patch("ai_ime.learning._append_learning_log"):
                for stroke in parse_sequence("xainzai{backspace*7}xianzai{space}"):
                    engine.handle_stroke(stroke)

            with closing(connect(db_path)) as conn:
                init_db(conn)
                self.assertEqual(list_events(conn), [])


if __name__ == "__main__":
    unittest.main()
