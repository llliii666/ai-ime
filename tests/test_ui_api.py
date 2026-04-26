import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ai_ime.db import connect, init_db, insert_event, list_events, list_rules, upsert_rules
from ai_ime.models import CorrectionEvent, LearnedRule
from ai_ime.ui_api import SettingsApi, _settings_from_payload, _settings_payload


class SettingsApiTests(unittest.TestCase):
    def test_settings_payload_never_contains_api_key_value(self) -> None:
        settings = _settings_from_payload(
            {
                "listener_enabled": False,
                "provider": "openai-compatible",
                "openai_base_url": "http://relay.test/v1",
                "openai_model": "gpt-5.4-mini",
            }
        )

        payload = _settings_payload(settings)

        self.assertEqual(payload["apiKey"], "")
        self.assertEqual(payload["openai_model"], "gpt-5.4-mini")
        self.assertFalse(payload["listener_enabled"])

    def test_save_settings_preserves_existing_env_key_when_api_key_blank(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        old_key = os.environ.get("AI_IME_OPENAI_API_KEY")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                os.environ.pop("AI_IME_OPENAI_API_KEY", None)
                env_path = Path(tmp) / ".env"
                env_path.write_text("AI_IME_OPENAI_API_KEY=secret-value\n", encoding="utf-8")
                api = SettingsApi(env_path=env_path, db_path=Path(tmp) / "ai-ime.db")

                with patch("ai_ime.ui_api.set_start_on_login") as mocked_startup:
                    response = api.save_settings(
                        {
                            "settings": {
                                "listener_enabled": True,
                                "record_full_keylog": True,
                                "send_full_keylog": False,
                                "start_on_login": False,
                                "provider": "openai-compatible",
                                "openai_base_url": "http://relay.test/v1",
                                "openai_model": "gpt-5.4-mini",
                                "ollama_base_url": "http://localhost:11434",
                                "ollama_model": "",
                                "rime_dir": "",
                                "rime_schema": "rime_ice",
                                "rime_dictionary": "ai_typo",
                                "rime_base_dictionary": "",
                                "keylog_file": str(Path(tmp) / "keylog.jsonl"),
                            },
                            "apiKey": "",
                        }
                    )

                self.assertTrue(response["ok"])
                self.assertIn("AI_IME_OPENAI_API_KEY=secret-value", env_path.read_text(encoding="utf-8"))
                mocked_startup.assert_called_once_with(False)
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data
            if old_key is None:
                os.environ.pop("AI_IME_OPENAI_API_KEY", None)
            else:
                os.environ["AI_IME_OPENAI_API_KEY"] = old_key

    def test_add_manual_correction_records_event_and_rule(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                db_path = Path(tmp) / "ai-ime.db"
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=db_path)

                with patch("ai_ime.learning._append_learning_log"):
                    response = api.add_manual_correction(
                        {
                            "settings": {
                                "auto_deploy_rime": False,
                                "auto_analyze_with_ai": False,
                                "keylog_file": str(Path(tmp) / "keylog.jsonl"),
                            },
                            "correction": {
                                "wrongPinyin": "xainzai",
                                "correctPinyin": "xianzai",
                                "committedText": "现在",
                            },
                        }
                    )

                with closing(connect(db_path)) as conn:
                    init_db(conn)
                    events = list_events(conn)
                    rules = list_rules(conn)

                self.assertTrue(response["ok"])
                self.assertEqual(events[0].source, "manual-ui")
                self.assertEqual(rules[0].committed_text, "现在")
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data

    def test_list_correction_records_returns_sorted_triples_and_enabled_rules(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                db_path = Path(tmp) / "ai-ime.db"
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=db_path)

                with closing(connect(db_path)) as conn:
                    init_db(conn)
                    insert_event(conn, CorrectionEvent("zuihou", "zuihou", "最后", source="manual"))
                    insert_event(conn, CorrectionEvent("anli", "anli", "案例", source="manual"))
                    upsert_rules(
                        conn,
                        [
                            LearnedRule("zuihou", "zuihou", "最后", 0.9, 150000, 2, "manual", enabled=False),
                            LearnedRule("anli", "anli", "案例", 0.95, 151000, 3, "manual", enabled=True),
                        ],
                    )

                response = api.list_correction_records("pinyin")

                self.assertTrue(response["ok"])
                self.assertEqual([event["wrongPinyin"] for event in response["events"]], ["anli", "zuihou"])
                self.assertEqual(len(response["rules"]), 1)
                self.assertEqual(response["rules"][0]["committedText"], "案例")
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data

    def test_load_state_exposes_provider_presets(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=Path(tmp) / "ai-ime.db")

                state = api.load_state()

                preset_ids = {preset["id"] for preset in state["meta"]["providerPresets"]}
                self.assertIn("openai", preset_ids)
                self.assertIn("ollama", preset_ids)
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data

    def test_test_provider_returns_model_list(self) -> None:
        class FakeProvider:
            def list_models(self) -> list[str]:
                return ["alpha", "beta"]

        with tempfile.TemporaryDirectory() as tmp:
            api = SettingsApi(env_path=Path(tmp) / ".env", db_path=Path(tmp) / "ai-ime.db")

            with patch("ai_ime.ui_api._build_provider", return_value=FakeProvider()):
                response = api.test_provider(
                    {
                        "settings": {
                            "provider": "openai-compatible",
                            "openai_base_url": "http://relay.test/v1",
                            "openai_model": "",
                            "keylog_file": str(Path(tmp) / "keylog.jsonl"),
                        }
                    }
                )

        self.assertTrue(response["ok"])
        self.assertEqual(response["models"], ["alpha", "beta"])


if __name__ == "__main__":
    unittest.main()
