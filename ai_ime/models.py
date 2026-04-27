from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CorrectionEvent:
    wrong_pinyin: str
    correct_pinyin: str
    committed_text: str
    commit_key: str = "unknown"
    source: str = "manual"
    app_id_hash: str | None = None
    wrong_committed_text: str | None = None
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


@dataclass(frozen=True)
class RuleAuditFinding:
    wrong_pinyin: str
    correct_pinyin: str
    committed_text: str
    rule_id: int | None = None
    reason: str = ""
    action: str = "delete"


@dataclass(frozen=True)
class ProviderAnalysis:
    rules: Sequence[LearnedRule]
    invalid_rules: Sequence[RuleAuditFinding] = ()

    def __iter__(self) -> Iterator[LearnedRule]:
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    def __getitem__(self, index: int) -> LearnedRule:
        return self.rules[index]
