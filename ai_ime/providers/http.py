from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ai_ime.providers.base import ProviderError


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: float = 60.0) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {exc.code} from provider: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Cannot reach provider: {exc}") from exc

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Provider HTTP response was not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError("Provider HTTP response must be a JSON object.")
    return data


def get_json(url: str, headers: dict[str, str] | None = None, timeout: float = 60.0) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {exc.code} from provider: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Cannot reach provider: {exc}") from exc

    try:
        data = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Provider HTTP response was not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError("Provider HTTP response must be a JSON object.")
    return data
