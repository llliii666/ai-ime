from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionEvent:
    wrong_pinyin: str
    correct_pinyin: str
    committed_text: str
    commit_key: str = "unknown"
    source: str = "manual"
    app_id_hash: str | None = None
    id: int | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class LearnedRule:
    wrong_pinyin: str
    correct_pinyin: str
    committed_text: str
    confidence: float
    weight: int
    count: int
    mistake_type: str
    provider: str = "rule"
    explanation: str = ""
    enabled: bool = True
    id: int | None = None
    last_seen_at: str | None = None
