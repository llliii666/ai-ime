import json
import tempfile
import unittest
from pathlib import Path

from ai_ime.correction.detector import KeyStroke
from ai_ime.listener import KeyLogEntry, KeyLogWriter, keyboard_name_to_stroke


class ListenerTests(unittest.TestCase):
    def test_keyboard_name_to_stroke(self) -> None:
        self.assertEqual(keyboard_name_to_stroke("x"), KeyStroke("char", "x"))
        self.assertEqual(keyboard_name_to_stroke("space"), KeyStroke("space"))
        self.assertEqual(keyboard_name_to_stroke("backspace"), KeyStroke("backspace"))
        self.assertIsNone(keyboard_name_to_stroke("shift"))

    def test_key_log_writer_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keylog.jsonl"
            writer = KeyLogWriter(path)
            writer.write(KeyLogEntry(timestamp=1.0, event_type="down", name="x", scan_code=45))

            line = path.read_text(encoding="utf-8").strip()
            self.assertEqual(json.loads(line)["name"], "x")


if __name__ == "__main__":
    unittest.main()
