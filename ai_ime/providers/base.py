from __future__ import annotations

from abc import ABC, abstractmethod

from ai_ime.models import CorrectionEvent, LearnedRule


class ProviderError(RuntimeError):
    """Raised when an AI provider cannot return valid learned rules."""


class AIProvider(ABC):
    @abstractmethod
    def analyze_events(self, events: list[CorrectionEvent]) -> list[LearnedRule]:
        """Analyze correction events and return learned rules."""
