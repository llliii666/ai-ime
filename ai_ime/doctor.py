from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

from ai_ime.config import default_db_path
from ai_ime.rime.paths import find_existing_user_dir


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str


def run_checks(db_path: Path | None = None) -> list[CheckResult]:
    resolved_db_path = db_path or default_db_path()
    return [
        _check_keyboard_package(),
        _check_env_config(),
        _check_rime_user_dir(),
        _check_database_parent(resolved_db_path),
    ]


def format_checks(results: list[CheckResult]) -> str:
    return "\n".join(f"[{result.status}] {result.name}: {result.detail}" for result in results)


def has_error(results: list[CheckResult]) -> bool:
    return any(result.status == "ERROR" for result in results)


def _check_keyboard_package() -> CheckResult:
    if importlib.util.find_spec("keyboard") is None:
        return CheckResult("keyboard", "ERROR", "keyboard package is not installed")
    return CheckResult("keyboard", "OK", "keyboard package is installed")


def _check_env_config() -> CheckResult:
    provider = os.environ.get("AI_IME_PROVIDER", "mock")
    if provider == "openai-compatible":
        base_url = os.environ.get("AI_IME_OPENAI_BASE_URL")
        key = os.environ.get("AI_IME_OPENAI_API_KEY")
        model = os.environ.get("AI_IME_OPENAI_MODEL", "gpt-5.4-mini")
        if not base_url:
            return CheckResult("env", "WARN", "AI_IME_OPENAI_BASE_URL is not set")
        if not key:
            return CheckResult("env", "WARN", "AI_IME_OPENAI_API_KEY is not set")
        return CheckResult("env", "OK", f"openai-compatible configured with model {model}")
    if provider == "ollama":
        model = os.environ.get("AI_IME_OLLAMA_MODEL") or os.environ.get("AI_IME_AI_MODEL")
        if not model:
            return CheckResult("env", "WARN", "AI_IME_OLLAMA_MODEL is not set")
        return CheckResult("env", "OK", f"ollama configured with model {model}")
    return CheckResult("env", "OK", f"provider {provider}")


def _check_rime_user_dir() -> CheckResult:
    user_dir = find_existing_user_dir()
    if user_dir is None:
        return CheckResult("rime", "WARN", "Rime user data directory was not found")
    return CheckResult("rime", "OK", str(user_dir))


def _check_database_parent(db_path: Path) -> CheckResult:
    parent = db_path.parent
    if parent.exists():
        return CheckResult("database", "OK", str(db_path))
    return CheckResult("database", "WARN", f"database parent directory does not exist yet: {parent}")
