import json
import tempfile
import unittest
from pathlib import Path

from ai_ime.correction.detector import KeyStroke
from ai_ime.listener import KeyLogEntry, KeyLogWriter, keylog_to_sequence, keyboard_name_to_stroke, read_keylog


class ListenerTests(unittest.TestCase):
    def test_keyboard_name_to_stroke(self) -> None:
        self.assertEqual(keyboard_name_to_stroke("x"), KeyStroke("char", "x"))
        self.assertEqual(keyboard_name_to_stroke("space"), KeyStroke("space"))
        self.assertEqual(keyboard_name_to_stroke("1"), KeyStroke("1"))
        self.assertEqual(keyboard_name_to_stroke("num 1"), KeyStroke("1"))
        self.assertEqual(keyboard_name_to_stroke("numpad 2"), KeyStroke("2"))
        self.assertEqual(keyboard_name_to_stroke("backspace"), KeyStroke("backspace"))
        self.assertIsNone(keyboard_name_to_stroke("shift"))

    def test_key_log_writer_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keylog.jsonl"
            writer = KeyLogWriter(path)
            writer.write(
                KeyLogEntry(
                    timestamp=1.0,
                    event_type="commit",
                    name="xianzai",
                    scan_code=45,
                    pinyin="xianzai",
                    committed_text="现在",
                    role="correction",
                )
            )

            line = path.read_text(encoding="utf-8").strip()
            payload = json.loads(line)
            self.assertEqual(payload["name"], "xianzai")
            self.assertEqual(payload["committed_text"], "现在")
            self.assertEqual(read_keylog(path)[0].role, "correction")

    def test_keylog_to_sequence_uses_down_events_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keylog.jsonl"
            writer = KeyLogWriter(path)
            for name in ["x", "a", "i", "n", "z", "a", "i"]:
                writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name=name))
            writer.write(KeyLogEntry(timestamp=1.0, event_type="up", name="i"))
            writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name="backspace"))
            writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name="x"))
            writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name="1"))

            self.assertEqual(keylog_to_sequence(path), "xainzai{backspace}x{1}")


if __name__ == "__main__":
    unittest.main()
