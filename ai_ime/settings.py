from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from ai_ime.config import default_data_dir, env_value
from ai_ime.providers.presets import infer_provider_preset

SETTINGS_FILE_NAME = "settings.json"
ANALYSIS_SCHEDULE_MODES = {"time", "count"}
ANALYSIS_TIME_SECONDS = (0, 600, 1800, 3600, 7200, 18000, 28800, 43200)
ANALYSIS_COUNT_THRESHOLDS = (1500, 2000, 3000, 4000, 5000)
DEFAULT_ANALYSIS_SCHEDULE_MODE = "time"
DEFAULT_ANALYSIS_TIME_SECONDS = 0
DEFAULT_ANALYSIS_COUNT_THRESHOLD = 1500


@dataclass
class AppSettings:
    listener_enabled: bool = True
    auto_learn_enabled: bool = True
    auto_analyze_with_ai: bool = False
    auto_deploy_rime: bool = True
    record_full_keylog: bool = False
    record_candidate_commits: bool = True
    send_full_keylog: bool = False
    delete_sent_keylog: bool = True
    analysis_schedule_mode: str = DEFAULT_ANALYSIS_SCHEDULE_MODE
    analysis_schedule_time_seconds: int = DEFAULT_ANALYSIS_TIME_SECONDS
    analysis_schedule_count_threshold: int = DEFAULT_ANALYSIS_COUNT_THRESHOLD
    start_on_login: bool = False
    provider: str = "openai-compatible"
    provider_preset: str = "openai"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-5.4-mini"
    openai_api_key_env: str = "AI_IME_OPENAI_API_KEY"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = ""
    rime_dir: str = ""
    rime_schema: str = "rime_ice"
    rime_dictionary: str = "ai_typo"
    rime_base_dictionary: str = ""
    keylog_file: str = ""


def default_settings_path() -> Path:
    return default_data_dir() / SETTINGS_FILE_NAME


def resolved_keylog_path(settings: AppSettings) -> Path:
    text = str(settings.keylog_file or "").strip()
    if text:
        return Path(text)
    return default_data_dir() / "keylog.jsonl"


def load_app_settings(path: Path | None = None) -> AppSettings:
    settings = settings_from_env()
    settings_path = path or default_settings_path()
    if not settings_path.exists():
        return settings
    payload = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        return settings
    allowed = {field.name for field in fields(AppSettings)}
    for key, value in payload.items():
        if key in allowed:
            setattr(settings, key, value)
    if "provider_preset" not in payload:
        settings.provider_preset = infer_provider_preset(
            settings.provider,
            openai_base_url=settings.openai_base_url,
            ollama_base_url=settings.ollama_base_url,
        )
    return normalize_app_settings(settings)


def save_app_settings(settings: AppSettings, path: Path | None = None) -> Path:
    normalize_app_settings(settings)
    settings_path = path or default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return settings_path


def settings_from_env() -> AppSettings:
    data_dir = default_data_dir()
    provider = env_value("AI_IME_PROVIDER", default="openai-compatible")
    openai_base_url = env_value("AI_IME_OPENAI_BASE_URL", default="https://api.openai.com/v1")
    ollama_base_url = env_value("AI_IME_OLLAMA_BASE_URL", default="http://localhost:11434")
    return AppSettings(
        auto_learn_enabled=env_value("AI_IME_AUTO_LEARN", default="true").lower() != "false",
        auto_analyze_with_ai=env_value("AI_IME_AUTO_ANALYZE_WITH_AI", default="false").lower() == "true",
        auto_deploy_rime=env_value("AI_IME_AUTO_DEPLOY_RIME", default="true").lower() != "false",
        record_full_keylog=env_value("AI_IME_RECORD_FULL_KEYLOG", default="false").lower() == "true",
        record_candidate_commits=env_value("AI_IME_RECORD_CANDIDATE_COMMITS", default="true").lower() != "false",
        send_full_keylog=env_value("AI_IME_SEND_FULL_KEYLOG", default="false").lower() == "true",
        delete_sent_keylog=env_value("AI_IME_DELETE_SENT_KEYLOG", default="true").lower() != "false",
        analysis_schedule_mode=normalize_analysis_schedule_mode(
            env_value("AI_IME_ANALYSIS_SCHEDULE_MODE", default=DEFAULT_ANALYSIS_SCHEDULE_MODE)
        ),
        analysis_schedule_time_seconds=normalize_analysis_time_seconds(
            _env_int("AI_IME_ANALYSIS_SCHEDULE_TIME_SECONDS", DEFAULT_ANALYSIS_TIME_SECONDS)
        ),
        analysis_schedule_count_threshold=normalize_analysis_count_threshold(
            _env_int("AI_IME_ANALYSIS_SCHEDULE_COUNT_THRESHOLD", DEFAULT_ANALYSIS_COUNT_THRESHOLD)
        ),
        provider=provider,
        provider_preset=env_value(
            "AI_IME_PROVIDER_PRESET",
            default=infer_provider_preset(provider, openai_base_url=openai_base_url, ollama_base_url=ollama_base_url),
        ),
        openai_base_url=openai_base_url,
        openai_model=env_value("AI_IME_OPENAI_MODEL", "AI_IME_AI_MODEL", default="gpt-5.4-mini"),
        openai_api_key_env=env_value("AI_IME_OPENAI_API_KEY_ENV", default="AI_IME_OPENAI_API_KEY"),
        ollama_base_url=ollama_base_url,
        ollama_model=env_value("AI_IME_OLLAMA_MODEL", "AI_IME_AI_MODEL"),
        keylog_file=str(data_dir / "keylog.jsonl"),
    )


def write_provider_env(settings: AppSettings, api_key: str | None = None, path: Path = Path(".env")) -> Path:
    existing = _read_env_map(path)
    existing.update(
        {
            "AI_IME_AUTO_LEARN": "true" if settings.auto_learn_enabled else "false",
            "AI_IME_AUTO_ANALYZE_WITH_AI": "true" if settings.auto_analyze_with_ai else "false",
            "AI_IME_AUTO_DEPLOY_RIME": "true" if settings.auto_deploy_rime else "false",
            "AI_IME_RECORD_FULL_KEYLOG": "true" if settings.record_full_keylog else "false",
            "AI_IME_RECORD_CANDIDATE_COMMITS": "true" if settings.record_candidate_commits else "false",
            "AI_IME_SEND_FULL_KEYLOG": "true" if settings.send_full_keylog else "false",
            "AI_IME_DELETE_SENT_KEYLOG": "true" if settings.delete_sent_keylog else "false",
            "AI_IME_ANALYSIS_SCHEDULE_MODE": normalize_analysis_schedule_mode(settings.analysis_schedule_mode),
            "AI_IME_ANALYSIS_SCHEDULE_TIME_SECONDS": str(
                normalize_analysis_time_seconds(settings.analysis_schedule_time_seconds)
            ),
            "AI_IME_ANALYSIS_SCHEDULE_COUNT_THRESHOLD": str(
                normalize_analysis_count_threshold(settings.analysis_schedule_count_threshold)
            ),
            "AI_IME_PROVIDER": settings.provider,
            "AI_IME_PROVIDER_PRESET": settings.provider_preset,
            "AI_IME_OPENAI_BASE_URL": settings.openai_base_url,
            "AI_IME_OPENAI_MODEL": settings.openai_model,
            "AI_IME_OPENAI_API_KEY_ENV": settings.openai_api_key_env,
            "AI_IME_OLLAMA_BASE_URL": settings.ollama_base_url,
            "AI_IME_OLLAMA_MODEL": settings.ollama_model,
        }
    )
    if api_key is not None:
        existing[settings.openai_api_key_env] = api_key
    lines = [f"{key}={_quote_env_value(value)}" for key, value in sorted(existing.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def normalize_app_settings(settings: AppSettings) -> AppSettings:
    settings.analysis_schedule_mode = normalize_analysis_schedule_mode(settings.analysis_schedule_mode)
    settings.analysis_schedule_time_seconds = normalize_analysis_time_seconds(settings.analysis_schedule_time_seconds)
    settings.analysis_schedule_count_threshold = normalize_analysis_count_threshold(
        settings.analysis_schedule_count_threshold
    )
    return settings


def normalize_analysis_schedule_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in ANALYSIS_SCHEDULE_MODES else DEFAULT_ANALYSIS_SCHEDULE_MODE


def normalize_analysis_time_seconds(value: Any) -> int:
    seconds = _as_int(value, DEFAULT_ANALYSIS_TIME_SECONDS)
    return seconds if seconds in ANALYSIS_TIME_SECONDS else DEFAULT_ANALYSIS_TIME_SECONDS


def normalize_analysis_count_threshold(value: Any) -> int:
    threshold = _as_int(value, DEFAULT_ANALYSIS_COUNT_THRESHOLD)
    return threshold if threshold in ANALYSIS_COUNT_THRESHOLDS else DEFAULT_ANALYSIS_COUNT_THRESHOLD


def _read_env_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = _unquote_env_value(value.strip())
    return values


def _quote_env_value(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    if any(char.isspace() for char in text) or "#" in text:
        return json.dumps(text, ensure_ascii=False)
    return text


def _env_int(name: str, default: int) -> int:
    return _as_int(env_value(name, default=str(default)), default)


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _unquote_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def env_api_key(settings: AppSettings) -> str:
    return os.environ.get(settings.openai_api_key_env, "")
