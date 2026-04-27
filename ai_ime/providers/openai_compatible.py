from __future__ import annotations

import os

from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent, LearnedRule, ProviderAnalysis
from ai_ime.providers.base import AIProvider, ProviderError
from ai_ime.providers.http import get_json, post_json
from ai_ime.providers.prompt import SYSTEM_PROMPT, build_user_prompt
from ai_ime.providers.schema import parse_analysis_json


class OpenAICompatibleProvider(AIProvider):
    def __init__(
        self,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        api_key_env: str = "OPENAI_API_KEY",
        timeout: float = 60.0,
        use_json_mode: bool = True,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.use_json_mode = use_json_mode

    def analyze_events(
        self,
        events: list[CorrectionEvent],
        keylog_entries: list[KeyLogEntry] | None = None,
        existing_rules: list[LearnedRule] | None = None,
    ) -> ProviderAnalysis:
        if not self.model:
            raise ProviderError("OpenAI-compatible provider requires a model.")
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(events, keylog_entries=keylog_entries, existing_rules=existing_rules),
                },
            ],
            "temperature": 0,
        }
        if self.use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        response = post_json(
            f"{self.base_url}/chat/completions",
            payload=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        content = _extract_chat_content(response)
        return parse_analysis_json(content, provider="openai-compatible")

    def list_models(self) -> list[str]:
        response = get_json(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
        data = response.get("data")
        if not isinstance(data, list):
            raise ProviderError("Provider models response missing data array.")
        models: list[str] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if isinstance(model_id, str) and model_id.strip():
                models.append(model_id.strip())
        return sorted(set(models), key=str.lower)

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        api_key = os.environ.get(self.api_key_env)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers


def _extract_chat_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("Provider response missing choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise ProviderError("Provider choice must be an object.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ProviderError("Provider choice missing message.")
    content = message.get("content")
    if not isinstance(content, str):
        raise ProviderError("Provider message content must be a string.")
    return content
