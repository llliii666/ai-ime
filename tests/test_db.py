import sqlite3
import unittest

from ai_ime.correction.rules import aggregate_rules
from ai_ime.db import (
    clear_events,
    delete_rule,
    init_db,
    insert_event,
    list_events,
    list_rules,
    set_rule_enabled,
    upsert_rules,
)
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

    def test_rule_management_and_event_cleanup(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        init_db(conn)

        insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在"))
        rules = aggregate_rules(list_events(conn))
        upsert_rules(conn, rules)
        rule_id = list_rules(conn)[0].id
        self.assertIsNotNone(rule_id)

        self.assertTrue(set_rule_enabled(conn, rule_id, enabled=False))
        self.assertFalse(list_rules(conn)[0].enabled)
        self.assertTrue(set_rule_enabled(conn, rule_id, enabled=True))
        self.assertTrue(list_rules(conn)[0].enabled)

        self.assertEqual(len(list_events(conn, limit=1)), 1)
        self.assertEqual(clear_events(conn), 1)
        self.assertEqual(list_events(conn), [])
        self.assertTrue(delete_rule(conn, rule_id))
        self.assertEqual(list_rules(conn), [])


if __name__ == "__main__":
    unittest.main()
