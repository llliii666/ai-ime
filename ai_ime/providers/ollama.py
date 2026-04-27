from __future__ import annotations

from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent, LearnedRule, ProviderAnalysis
from ai_ime.providers.base import AIProvider, ProviderError
from ai_ime.providers.http import get_json, post_json
from ai_ime.providers.prompt import SYSTEM_PROMPT, build_user_prompt
from ai_ime.providers.schema import parse_analysis_json


class OllamaProvider(AIProvider):
    def __init__(self, model: str, base_url: str = "http://localhost:11434", timeout: float = 120.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def analyze_events(
        self,
        events: list[CorrectionEvent],
        keylog_entries: list[KeyLogEntry] | None = None,
        existing_rules: list[LearnedRule] | None = None,
    ) -> ProviderAnalysis:
        if not self.model:
            raise ProviderError("Ollama provider requires a model.")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(events, keylog_entries=keylog_entries, existing_rules=existing_rules),
                },
            ],
            "stream": False,
            "format": "json",
        }
        response = post_json(f"{self.base_url}/api/chat", payload=payload, timeout=self.timeout)
        message = response.get("message")
        if not isinstance(message, dict):
            raise ProviderError("Ollama response missing message.")
        content = message.get("content")
        if not isinstance(content, str):
            raise ProviderError("Ollama message content must be a string.")
        return parse_analysis_json(content, provider="ollama")

    def list_models(self) -> list[str]:
        response = get_json(f"{self.base_url}/api/tags", timeout=self.timeout)
        data = response.get("models")
        if not isinstance(data, list):
            raise ProviderError("Ollama models response missing models array.")
        models: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("model")
            if isinstance(name, str) and name.strip():
                models.append(name.strip())
        return sorted(set(models), key=str.lower)
