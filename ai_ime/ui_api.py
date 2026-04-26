from __future__ import annotations

import os
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_ime.config import default_db_path, load_env_file
from ai_ime.db import connect, init_db, list_events, list_rules
from ai_ime.providers import MockProvider, OllamaProvider, OpenAICompatibleProvider, ProviderError
from ai_ime.rime.deploy import deploy_rime_files
from ai_ime.rime.paths import detect_active_schema, find_existing_user_dir
from ai_ime.settings import AppSettings, default_settings_path, env_api_key, load_app_settings, save_app_settings, write_provider_env
from ai_ime.startup import set_start_on_login


class SettingsApi:
    def __init__(self, env_path: Path = Path(".env"), db_path: Path | None = None) -> None:
        self.env_path = env_path
        self.db_path = db_path or default_db_path()
        self.window: Any = None
        load_env_file(self.env_path)

    def bind_window(self, window: Any) -> None:
        self.window = window

    def load_state(self) -> dict[str, Any]:
        settings = _settings_with_detected_rime(load_app_settings())
        return {
            "ok": True,
            "settings": _settings_payload(settings),
            "meta": {
                "settingsPath": str(default_settings_path()),
                "envPath": str(self.env_path.resolve()),
                "dbPath": str(self.db_path),
                "apiKeySaved": bool(env_api_key(settings)),
                "apiKeyMask": _mask_secret(env_api_key(settings)),
                **self._database_stats(),
            },
        }

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_settings = payload.get("settings", {})
        if not isinstance(raw_settings, dict):
            return _error("设置数据格式不正确。")

        settings = _settings_from_payload(raw_settings)
        api_key = str(payload.get("apiKey", "") or "").strip()
        save_app_settings(settings)
        write_provider_env(settings, api_key=api_key or None, path=self.env_path)
        load_env_file(self.env_path, override=True)
        set_start_on_login(settings.start_on_login)
        return {"ok": True, "message": "设置已保存。", "settings": _settings_payload(settings)}

    def detect_rime(self) -> dict[str, Any]:
        rime_dir = find_existing_user_dir()
        if rime_dir is None:
            return _error("没有检测到 Rime 用户目录。")
        schema = detect_active_schema(rime_dir) or ""
        return {
            "ok": True,
            "rimeDir": str(rime_dir),
            "rimeSchema": schema,
            "message": f"已检测到 Rime 目录：{rime_dir}",
        }

    def choose_path(self, kind: str, current: str = "") -> dict[str, Any]:
        if self.window is None:
            return _error("设置窗口还未就绪。")
        directory = current if kind == "directory" else str(Path(current).parent) if current else ""
        try:
            import webview

            if kind == "directory":
                result = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=directory)
            else:
                result = self.window.create_file_dialog(
                    webview.FileDialog.SAVE,
                    directory=directory,
                    save_filename=Path(current).name if current else "keylog.jsonl",
                )
        except Exception as exc:
            return _error(f"打开选择窗口失败：{exc}")

        if not result:
            return {"ok": False, "cancelled": True}
        return {"ok": True, "path": str(result[0])}

    def deploy_rime(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_settings = payload.get("settings", {})
        if not isinstance(raw_settings, dict):
            return _error("设置数据格式不正确。")
        settings = _settings_from_payload(raw_settings)
        if not settings.rime_dir:
            return _error("请先设置 Rime 用户目录。")
        rime_dir = Path(settings.rime_dir)
        if not rime_dir.exists():
            return _error(f"Rime 用户目录不存在：{rime_dir}")

        try:
            with connect(self.db_path) as conn:
                init_db(conn)
                rules = list_rules(conn, enabled_only=True)
            result = deploy_rime_files(
                rules,
                rime_dir=rime_dir,
                schema_id=settings.rime_schema,
                dictionary_id=settings.rime_dictionary,
                base_dictionary=settings.rime_base_dictionary,
            )
        except Exception as exc:
            return _error(f"部署到小狼毫失败：{exc}")

        return {
            "ok": True,
            "message": f"已写入 {len(rules)} 条启用规则。请在小狼毫中重新部署一次。",
            "dictionaryPath": str(result.dictionary_path),
            "patchPath": str(result.patch_path),
            "backupDir": str(result.backup_dir),
        }

    def test_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_settings = payload.get("settings", {})
        if not isinstance(raw_settings, dict):
            return _error("设置数据格式不正确。")
        settings = _settings_from_payload(raw_settings)
        api_key = str(payload.get("apiKey", "") or "").strip()
        if api_key:
            os.environ[settings.openai_api_key_env] = api_key
        try:
            provider = _build_provider(settings)
            provider.analyze_events([])
        except ProviderError as exc:
            return _error(f"模型连接失败：{exc}")
        except Exception as exc:
            return _error(f"模型连接失败：{exc}")
        return {"ok": True, "message": "模型接口可以正常返回。"}

    def open_path(self, value: str) -> dict[str, Any]:
        path = Path(value)
        if not path.exists():
            return _error(f"路径不存在：{path}")
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["open", str(path)])
        except Exception as exc:
            return _error(f"打开路径失败：{exc}")
        return {"ok": True}

    def _database_stats(self) -> dict[str, int]:
        try:
            with connect(self.db_path) as conn:
                init_db(conn)
                events_count = len(list_events(conn))
                enabled_rules_count = len(list_rules(conn, enabled_only=True))
                rules_count = len(list_rules(conn))
        except Exception:
            return {"eventsCount": 0, "enabledRulesCount": 0, "rulesCount": 0}
        return {
            "eventsCount": events_count,
            "enabledRulesCount": enabled_rules_count,
            "rulesCount": rules_count,
        }


def _settings_with_detected_rime(settings: AppSettings) -> AppSettings:
    if not settings.rime_dir:
        detected = find_existing_user_dir()
        if detected is not None:
            settings.rime_dir = str(detected)
    if settings.rime_dir:
        detected_schema = detect_active_schema(Path(settings.rime_dir))
        if detected_schema and settings.rime_schema in {"", "luna_pinyin"}:
            settings.rime_schema = detected_schema
    return settings


def _settings_payload(settings: AppSettings) -> dict[str, Any]:
    payload = asdict(settings)
    payload["apiKey"] = ""
    return payload


def _settings_from_payload(payload: dict[str, Any]) -> AppSettings:
    return AppSettings(
        listener_enabled=_as_bool(payload.get("listener_enabled"), True),
        record_full_keylog=_as_bool(payload.get("record_full_keylog"), True),
        send_full_keylog=_as_bool(payload.get("send_full_keylog"), False),
        start_on_login=_as_bool(payload.get("start_on_login"), False),
        provider=_as_string(payload.get("provider"), "openai-compatible"),
        openai_base_url=_as_string(payload.get("openai_base_url"), "https://api.openai.com/v1"),
        openai_model=_as_string(payload.get("openai_model"), "gpt-5.4-mini"),
        openai_api_key_env=_as_string(payload.get("openai_api_key_env"), "AI_IME_OPENAI_API_KEY"),
        ollama_base_url=_as_string(payload.get("ollama_base_url"), "http://localhost:11434"),
        ollama_model=_as_string(payload.get("ollama_model"), ""),
        rime_dir=_as_string(payload.get("rime_dir"), ""),
        rime_schema=_as_string(payload.get("rime_schema"), "luna_pinyin"),
        rime_dictionary=_as_string(payload.get("rime_dictionary"), "ai_typo"),
        rime_base_dictionary=_as_string(payload.get("rime_base_dictionary"), ""),
        keylog_file=_as_string(payload.get("keylog_file"), ""),
    )


def _build_provider(settings: AppSettings):
    if settings.provider == "mock":
        return MockProvider()
    if settings.provider == "ollama":
        return OllamaProvider(model=settings.ollama_model, base_url=settings.ollama_base_url, timeout=15.0)
    if settings.provider == "openai-compatible":
        return OpenAICompatibleProvider(
            model=settings.openai_model,
            base_url=settings.openai_base_url,
            api_key_env=settings.openai_api_key_env,
            timeout=15.0,
        )
    raise ProviderError(f"不支持的模型通道：{settings.provider}")


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _as_string(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}
