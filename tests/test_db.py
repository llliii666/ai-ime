import sqlite3
import unittest

from ai_ime.correction.rules import aggregate_rules
from ai_ime.db import init_db, insert_event, list_events, list_rules, upsert_rules
from ai_ime.models import CorrectionEvent


class DatabaseTests(unittest.TestCase):
    def test_insert_event_and_upsert_rule(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)

        event_id = insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在"))
        self.assertEqual(event_id, 1)

        events = list_events(conn)
        rules = aggregate_rules(events)
        upserted = upsert_rules(conn, rules)
        stored_rules = list_rules(conn)

        self.assertEqual(upserted, 1)
        self.assertEqual(len(stored_rules), 1)
        self.assertEqual(stored_rules[0].wrong_pinyin, "xainzai")
        self.assertEqual(stored_rules[0].committed_text, "现在")


if __name__ == "__main__":
    unittest.main()
