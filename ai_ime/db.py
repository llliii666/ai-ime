from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .models import CorrectionEvent, LearnedRule

SCHEMA_VERSION = 2


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS correction_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wrong_pinyin TEXT NOT NULL,
            correct_pinyin TEXT NOT NULL,
            committed_text TEXT NOT NULL,
            commit_key TEXT NOT NULL DEFAULT 'unknown',
            app_id_hash TEXT,
            wrong_committed_text TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS learned_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wrong_pinyin TEXT NOT NULL,
            correct_pinyin TEXT NOT NULL,
            committed_text TEXT NOT NULL,
            confidence REAL NOT NULL,
            weight INTEGER NOT NULL,
            count INTEGER NOT NULL,
            mistake_type TEXT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'rule',
            explanation TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (wrong_pinyin, correct_pinyin, committed_text, provider)
        );
        """
    )
    _migrate_schema(conn)
    conn.execute(
        """
        INSERT INTO schema_meta (key, value)
        VALUES ('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(correction_events)").fetchall()}
    if "wrong_committed_text" not in event_columns:
        conn.execute("ALTER TABLE correction_events ADD COLUMN wrong_committed_text TEXT")


def insert_event(conn: sqlite3.Connection, event: CorrectionEvent) -> int:
    cursor = conn.execute(
        """
        INSERT INTO correction_events (
            wrong_pinyin,
            correct_pinyin,
            committed_text,
            commit_key,
            app_id_hash,
            wrong_committed_text,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.wrong_pinyin,
            event.correct_pinyin,
            event.committed_text,
            event.commit_key,
            event.app_id_hash,
            event.wrong_committed_text,
            event.source,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def list_events(conn: sqlite3.Connection, limit: int | None = None) -> list[CorrectionEvent]:
    limit_clause = ""
    params: tuple[int, ...] = ()
    if limit is not None:
        limit_clause = "LIMIT ?"
        params = (limit,)
    rows = conn.execute(
        f"""
        SELECT
            id,
            wrong_pinyin,
            correct_pinyin,
            committed_text,
            commit_key,
            source,
            app_id_hash,
            wrong_committed_text,
            created_at
        FROM correction_events
        ORDER BY id
        {limit_clause}
        """,
        params,
    ).fetchall()
    return [
        CorrectionEvent(
            id=row["id"],
            wrong_pinyin=row["wrong_pinyin"],
            correct_pinyin=row["correct_pinyin"],
            committed_text=row["committed_text"],
            commit_key=row["commit_key"],
            source=row["source"],
            app_id_hash=row["app_id_hash"],
            wrong_committed_text=row["wrong_committed_text"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def update_event(conn: sqlite3.Connection, event_id: int, event: CorrectionEvent) -> bool:
    cursor = conn.execute(
        """
        UPDATE correction_events
        SET wrong_pinyin = ?,
            correct_pinyin = ?,
            committed_text = ?,
            wrong_committed_text = ?
        WHERE id = ?
        """,
        (
            event.wrong_pinyin,
            event.correct_pinyin,
            event.committed_text,
            event.wrong_committed_text,
            event_id,
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_event(conn: sqlite3.Connection, event_id: int) -> bool:
    cursor = conn.execute("DELETE FROM correction_events WHERE id = ?", (event_id,))
    conn.commit()
    return cursor.rowcount > 0


def upsert_rules(conn: sqlite3.Connection, rules: Iterable[LearnedRule]) -> int:
    count = 0
    for rule in rules:
        conn.execute(
            """
            INSERT INTO learned_rules (
                wrong_pinyin,
                correct_pinyin,
                committed_text,
                confidence,
                weight,
                count,
                mistake_type,
                provider,
                explanation,
                enabled,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(wrong_pinyin, correct_pinyin, committed_text, provider)
            DO UPDATE SET
                confidence = excluded.confidence,
                weight = excluded.weight,
                count = excluded.count,
                mistake_type = excluded.mistake_type,
                explanation = excluded.explanation,
                enabled = excluded.enabled,
                last_seen_at = excluded.last_seen_at
            """,
            (
                rule.wrong_pinyin,
                rule.correct_pinyin,
                rule.committed_text,
                rule.confidence,
                rule.weight,
                rule.count,
                rule.mistake_type,
                rule.provider,
                rule.explanation,
                1 if rule.enabled else 0,
            ),
        )
        count += 1
    conn.commit()
    return count


def list_rules(conn: sqlite3.Connection, enabled_only: bool = False) -> list[LearnedRule]:
    where = "WHERE enabled = 1" if enabled_only else ""
    rows = conn.execute(
        f"""
        SELECT
            id,
            wrong_pinyin,
            correct_pinyin,
            committed_text,
            confidence,
            weight,
            count,
            mistake_type,
            provider,
            explanation,
            enabled,
            last_seen_at
        FROM learned_rules
        {where}
        ORDER BY enabled DESC, confidence DESC, count DESC, id ASC
        """
    ).fetchall()
    return [
        LearnedRule(
            id=row["id"],
            wrong_pinyin=row["wrong_pinyin"],
            correct_pinyin=row["correct_pinyin"],
            committed_text=row["committed_text"],
            confidence=float(row["confidence"]),
            weight=int(row["weight"]),
            count=int(row["count"]),
            mistake_type=row["mistake_type"],
            provider=row["provider"],
            explanation=row["explanation"],
            enabled=bool(row["enabled"]),
            last_seen_at=row["last_seen_at"],
        )
        for row in rows
    ]


def set_rule_enabled(conn: sqlite3.Connection, rule_id: int, enabled: bool) -> bool:
    cursor = conn.execute(
        """
        UPDATE learned_rules
        SET enabled = ?
        WHERE id = ?
        """,
        (1 if enabled else 0, rule_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def update_rule(conn: sqlite3.Connection, rule_id: int, rule: LearnedRule) -> bool:
    cursor = conn.execute(
        """
        UPDATE learned_rules
        SET wrong_pinyin = ?,
            correct_pinyin = ?,
            committed_text = ?,
            confidence = ?,
            weight = ?,
            count = ?,
            mistake_type = ?,
            explanation = ?,
            enabled = ?,
            last_seen_at = datetime('now')
        WHERE id = ?
        """,
        (
            rule.wrong_pinyin,
            rule.correct_pinyin,
            rule.committed_text,
            rule.confidence,
            rule.weight,
            rule.count,
            rule.mistake_type,
            rule.explanation,
            1 if rule.enabled else 0,
            rule_id,
        ),
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_rule(conn: sqlite3.Connection, rule_id: int) -> bool:
    cursor = conn.execute("DELETE FROM learned_rules WHERE id = ?", (rule_id,))
    conn.commit()
    return cursor.rowcount > 0


def clear_events(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM correction_events")
    conn.commit()
    return cursor.rowcount
