from __future__ import annotations

from ai_ime.correction.rules import aggregate_rules
from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent, LearnedRule, ProviderAnalysis
from ai_ime.providers.base import AIProvider


class MockProvider(AIProvider):
    def analyze_events(
        self,
        events: list[CorrectionEvent],
        keylog_entries: list[KeyLogEntry] | None = None,
        existing_rules: list[LearnedRule] | None = None,
    ) -> ProviderAnalysis:
        rules = aggregate_rules(events)
        return ProviderAnalysis(
            rules=[
                LearnedRule(
                    wrong_pinyin=rule.wrong_pinyin,
                    correct_pinyin=rule.correct_pinyin,
                    committed_text=rule.committed_text,
                    confidence=rule.confidence,
                    weight=rule.weight,
                    count=rule.count,
                    mistake_type=rule.mistake_type,
                    provider="mock-ai",
                    explanation=f"mock-ai mirrored rule analysis: {rule.explanation}",
                    enabled=rule.enabled,
                )
                for rule in rules
            ]
        )
