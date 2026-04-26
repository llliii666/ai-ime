from __future__ import annotations

import os
import subprocess
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ai_ime.config import default_data_dir
from ai_ime.config import default_db_path, load_env_file
from ai_ime.correction.normalize import normalize_pinyin
from ai_ime.analysis_scheduler import SCHEDULER_STATE_FILE
from ai_ime.db import connect, delete_event, delete_rule, init_db, list_events, list_rules, update_event, update_rule
from ai_ime.learning import AutoLearningEngine
from ai_ime.models import CorrectionEvent, LearnedRule
from ai_ime.providers import MockProvider, OllamaProvider, OpenAICompatibleProvider, ProviderError
from ai_ime.providers.presets import provider_presets_payload
from ai_ime.rime.deploy import deploy_rime_files
from ai_ime.rime.paths import detect_active_schema, find_existing_user_dir
from ai_ime.settings import (
    AppSettings,
    default_settings_path,
    env_api_key,
    load_app_settings,
    resolved_keylog_path,
    save_app_settings,
    write_provider_env,
)
from ai_ime.startup import set_start_on_login


class SettingsApi:
    def __init__(self, env_path: Path = Path(".env"), db_path: Path | None = None) -> None:
        self.env_path = env_path
        self.db_path = db_path or default_db_path()
        self._window: Any = None
        load_env_file(self.env_path)

    def bind_window(self, window: Any) -> None:
        self._window = window

    def load_state(self) -> dict[str, Any]:
        settings = _settings_with_detected_rime(load_app_settings())
        return {
            "ok": True,
            "settings": _settings_payload(settings),
            "meta": {
                "settingsPath": str(default_settings_path()),
                "envPath": str(self.env_path.resolve()),
                "dbPath": str(self.db_path),
                "learningLogPath": str(default_data_dir() / "learning.log"),
                "apiKeySaved": bool(env_api_key(settings)),
                "apiKeyMask": _mask_secret(env_api_key(settings)),
                "providerPresets": provider_presets_payload(),
                "storagePaths": _storage_paths(settings, self.env_path, self.db_path),
                **self._database_stats(),
            },
        }

    def list_correction_records(self, sort: str = "time_desc") -> dict[str, Any]:
        try:
            with closing(connect(self.db_path)) as conn:
                init_db(conn)
                events = _sort_events(list_events(conn), sort)
                rules = _sort_rules(list_rules(conn, enabled_only=True), sort)
        except Exception as exc:
            return _error(f"读取纠错记录失败：{exc}")
        return {
            "ok": True,
            "sort": _normalize_record_sort(sort),
            "events": [_event_payload(event) for event in events],
            "rules": [_rule_payload(rule) for rule in rules],
        }

    def update_correction_record(self, kind: str, record_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        wrong = normalize_pinyin(str(payload.get("wrongPinyin", "")))
        correct = normalize_pinyin(str(payload.get("correctPinyin", "")))
        text = str(payload.get("committedText", "")).strip()
        wrong_text = str(payload.get("wrongCommittedText", "") or "").strip()
        if not wrong or not correct or not text:
            return _error("请填写错误拼音、正确拼音和正确汉字。")
        try:
            with closing(connect(self.db_path)) as conn:
                init_db(conn)
                if kind == "events":
                    updated = update_event(
                        conn,
                        int(record_id),
                        CorrectionEvent(
                            wrong_pinyin=wrong,
                            correct_pinyin=correct,
                            committed_text=text,
                            wrong_committed_text=wrong_text or None,
                        ),
                    )
                elif kind == "rules":
                    updated = update_rule(
                        conn,
                        int(record_id),
                        LearnedRule(
                            wrong_pinyin=wrong,
                            correct_pinyin=correct,
                            committed_text=text,
                            confidence=float(payload.get("confidence") or 1.0),
                            weight=int(payload.get("weight") or 150000),
                            count=int(payload.get("count") or 1),
                            mistake_type=str(payload.get("mistakeType") or "manual_edit"),
                            provider=str(payload.get("provider") or "manual"),
                            explanation=str(payload.get("explanation") or "manual edit"),
                            enabled=True,
                        ),
                    )
                else:
                    return _error("未知记录类型。")
        except Exception as exc:
            return _error(f"更新记录失败：{exc}")
        if not updated:
            return _error("没有找到要更新的记录。")
        return {"ok": True, "message": "记录已更新。"}

    def delete_correction_record(self, kind: str, record_id: int) -> dict[str, Any]:
        try:
            with closing(connect(self.db_path)) as conn:
                init_db(conn)
                if kind == "events":
                    deleted = delete_event(conn, int(record_id))
                elif kind == "rules":
                    deleted = delete_rule(conn, int(record_id))
                else:
                    return _error("未知记录类型。")
        except Exception as exc:
            return _error(f"删除记录失败：{exc}")
        if not deleted:
            return _error("没有找到要删除的记录。")
        return {"ok": True, "message": "记录已删除。"}

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

    def add_manual_correction(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_settings = payload.get("settings", {})
        raw_correction = payload.get("correction", {})
        if not isinstance(raw_settings, dict) or not isinstance(raw_correction, dict):
            return _error("手动纠错数据格式不正确。")

        wrong = normalize_pinyin(str(raw_correction.get("wrongPinyin", "")))
        correct = normalize_pinyin(str(raw_correction.get("correctPinyin", "")))
        text = str(raw_correction.get("committedText", "")).strip()
        if not wrong or not correct or not text:
            return _error("请填写错误拼音、正确拼音和对应中文。")
        if wrong == correct:
            return _error("错误拼音和正确拼音不能相同。")

        settings = _settings_from_payload(raw_settings)
        event = CorrectionEvent(
            wrong_pinyin=wrong,
            correct_pinyin=correct,
            committed_text=text,
            commit_key="manual",
            source="manual-ui",
        )
        try:
            result = AutoLearningEngine(settings, db_path=self.db_path, capture_delay=0, async_finalize=False).learn_event(event)
        except Exception as exc:
            return _error(f"手动纠错记录失败：{exc}")
        return {
            "ok": True,
            "message": f"已记录：{wrong} -> {correct} -> {text}",
            "upsertedRules": result.upserted_rules,
            "deployed": result.deployed,
        }

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
        if self._window is None:
            return _error("设置窗口还未就绪。")
        directory = current if kind == "directory" else str(Path(current).parent) if current else ""
        try:
            import webview

            if kind == "directory":
                result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=directory)
            else:
                result = self._window.create_file_dialog(
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
            models = _list_provider_models(provider)
        except ProviderError as exc:
            return _error(f"模型连接失败：{exc}")
        except Exception as exc:
            return _error(f"模型连接失败：{exc}")
        return {
            "ok": True,
            "message": f"模型接口连接正常，获取到 {len(models)} 个模型。" if models else "模型接口连接正常，但没有返回模型列表。",
            "models": models,
        }

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

    def open_record_file(self, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if kind == "learning":
            path = default_data_dir() / "learning.log"
        elif kind == "keylog":
            raw_settings = (payload or {}).get("settings", {})
            settings = _settings_from_payload(raw_settings if isinstance(raw_settings, dict) else {})
            path = resolved_keylog_path(settings)
        else:
            return _error("未知记录类型。")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
        except Exception as exc:
            return _error(f"创建记录文件失败：{exc}")
        return self.open_path(str(path))

    def open_location(self, value: str) -> dict[str, Any]:
        path = Path(value)
        target = path if path.is_dir() else path.parent
        if not target.exists():
            try:
                target.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                return _error(f"创建目录失败：{exc}")
        return self.open_path(str(target))

    def _database_stats(self) -> dict[str, int]:
        conn = None
        try:
            conn = connect(self.db_path)
            init_db(conn)
            events_count = len(list_events(conn))
            enabled_rules_count = len(list_rules(conn, enabled_only=True))
            rules_count = len(list_rules(conn))
        except Exception:
            return {"eventsCount": 0, "enabledRulesCount": 0, "rulesCount": 0}
        finally:
            if conn is not None:
                conn.close()
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
        auto_learn_enabled=_as_bool(payload.get("auto_learn_enabled"), True),
        auto_analyze_with_ai=_as_bool(payload.get("auto_analyze_with_ai"), False),
        auto_deploy_rime=_as_bool(payload.get("auto_deploy_rime"), True),
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
        keylog_file=_as_string(payload.get("keylog_file"), str(default_data_dir() / "keylog.jsonl")),
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


def _list_provider_models(provider: object) -> list[str]:
    list_models = getattr(provider, "list_models", None)
    if callable(list_models):
        return list_models()
    if isinstance(provider, MockProvider):
        return ["mock-model"]
    raise ProviderError("当前模型通道不支持获取模型列表。")


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


def _sort_events(events: list[CorrectionEvent], sort: str) -> list[CorrectionEvent]:
    normalized = _normalize_record_sort(sort)
    if normalized == "pinyin":
        return sorted(events, key=lambda item: _triple_sort_key(item.wrong_pinyin, item.correct_pinyin, item.committed_text))
    reverse = normalized == "time_desc"
    return sorted(events, key=lambda item: (item.created_at or "", item.id or 0), reverse=reverse)


def _sort_rules(rules: list[LearnedRule], sort: str) -> list[LearnedRule]:
    normalized = _normalize_record_sort(sort)
    if normalized == "pinyin":
        return sorted(rules, key=lambda item: _triple_sort_key(item.wrong_pinyin, item.correct_pinyin, item.committed_text))
    reverse = normalized == "time_desc"
    return sorted(rules, key=lambda item: (item.last_seen_at or "", item.id or 0), reverse=reverse)


def _normalize_record_sort(value: str) -> str:
    if value in {"time_desc", "time_asc", "pinyin"}:
        return value
    return "time_desc"


def _triple_sort_key(wrong_pinyin: str, correct_pinyin: str, committed_text: str) -> tuple[str, str, str]:
    return (wrong_pinyin.lower(), correct_pinyin.lower(), committed_text)


def _event_payload(event: CorrectionEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "wrongPinyin": event.wrong_pinyin,
        "correctPinyin": event.correct_pinyin,
        "committedText": event.committed_text,
        "wrongCommittedText": event.wrong_committed_text or "",
        "commitKey": event.commit_key,
        "source": event.source,
        "createdAt": event.created_at,
    }


def _rule_payload(rule: LearnedRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "wrongPinyin": rule.wrong_pinyin,
        "correctPinyin": rule.correct_pinyin,
        "committedText": rule.committed_text,
        "wrongCommittedText": "",
        "confidence": rule.confidence,
        "weight": rule.weight,
        "count": rule.count,
        "provider": rule.provider,
        "mistakeType": rule.mistake_type,
        "explanation": rule.explanation,
        "lastSeenAt": rule.last_seen_at,
    }


def _storage_paths(settings: AppSettings, env_path: Path, db_path: Path) -> list[dict[str, str]]:
    data_dir = default_data_dir()
    paths = [
        _path_payload("dataDir", "应用数据目录", data_dir, "settings.json、数据库、日志和缓存的默认目录。"),
        _path_payload("settings", "设置文件", default_settings_path(), "保存监听、隐私、模型、Rime 等界面设置。"),
        _path_payload("env", ".env 密钥文件", env_path.resolve(), "保存 Base URL、模型名和 API Key，已被 git 忽略。"),
        _path_payload("database", "纠错数据库", db_path, "保存纠错事件和学习规则。"),
        _path_payload("keylog", "键盘日志", resolved_keylog_path(settings), "仅在开启完整日志时保存原始按键和语义提交记录。"),
        _path_payload("learningLog", "学习日志", data_dir / "learning.log", "记录自动学习、跳过原因和 AI 分析结果。"),
        _path_payload("scheduler", "AI 分析状态", data_dir / SCHEDULER_STATE_FILE, "记录上次分析位置；已上传日志不会自动删除，只用 offset 避免重复发送。"),
        _path_payload("webview", "WebView 缓存", data_dir / "webview", "设置窗口的本地 WebView 存储目录。"),
    ]
    if settings.rime_dir:
        rime_dir = Path(settings.rime_dir)
        paths.extend(
            [
                _path_payload("rimeDir", "Rime 用户目录", rime_dir, "小狼毫用户词典和方案配置目录。"),
                _path_payload("rimeDict", "AI 纠错词典", rime_dir / f"{settings.rime_dictionary}.dict.yaml", "AI IME 写入的纠错词典文件。"),
                _path_payload("rimeBackups", "Rime 备份目录", rime_dir / ".ai-ime-backups", "部署 Rime 文件前创建的备份目录。"),
            ]
        )
    return paths


def _path_payload(path_id: str, label: str, path: Path, description: str) -> dict[str, str]:
    return {
        "id": path_id,
        "label": label,
        "path": str(path),
        "description": description,
    }


def _error(message: str) -> dict[str, Any]:
    return {"ok": False, "message": message}
