import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from ai_ime.db import connect, init_db, insert_event, list_events, list_rules, upsert_rules
from ai_ime.models import CorrectionEvent, LearnedRule
from ai_ime.settings import AppSettings, save_app_settings
from ai_ime.ui_api import SettingsApi, _settings_from_payload, _settings_payload


class SettingsApiTests(unittest.TestCase):
    def test_settings_payload_never_contains_api_key_value(self) -> None:
        settings = _settings_from_payload(
            {
                "listener_enabled": False,
                "provider": "openai-compatible",
                "openai_base_url": "http://relay.test/v1",
                "openai_model": "gpt-5.4-mini",
                "provider_preset": "custom",
            }
        )

        payload = _settings_payload(settings)

        self.assertEqual(payload["apiKey"], "")
        self.assertEqual(payload["provider_preset"], "custom")
        self.assertEqual(payload["openai_model"], "gpt-5.4-mini")
        self.assertFalse(payload["listener_enabled"])

    def test_settings_from_payload_preserves_provider_preset_independent_of_model(self) -> None:
        settings = _settings_from_payload(
            {
                "provider": "openai-compatible",
                "provider_preset": "deepseek",
                "openai_base_url": "https://api.deepseek.com/v1",
                "openai_model": "deepseek-v4-flash",
            }
        )

        self.assertEqual(settings.provider_preset, "deepseek")
        self.assertEqual(settings.openai_model, "deepseek-v4-flash")

    def test_settings_from_payload_defaults_full_keylog_to_false(self) -> None:
        settings = _settings_from_payload({})

        self.assertFalse(settings.record_full_keylog)

    def test_settings_from_payload_preserves_analysis_schedule_config(self) -> None:
        settings = _settings_from_payload(
            {
                "analysis_schedule_mode": "count",
                "analysis_schedule_time_seconds": "3600",
                "analysis_schedule_count_threshold": "3000",
            }
        )

        self.assertEqual(settings.analysis_schedule_mode, "count")
        self.assertEqual(settings.analysis_schedule_time_seconds, 3600)
        self.assertEqual(settings.analysis_schedule_count_threshold, 3000)
        payload = _settings_payload(settings)
        self.assertEqual(payload["analysis_schedule_mode"], "count")
        self.assertEqual(payload["analysis_schedule_time_seconds"], 3600)
        self.assertEqual(payload["analysis_schedule_count_threshold"], 3000)

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

                with patch("ai_ime.ui_api.sync_start_on_login", return_value=False) as mocked_startup:
                    response = api.save_settings(
                        {
                            "settings": {
                                "listener_enabled": True,
                                "record_full_keylog": True,
                                "send_full_keylog": False,
                                "start_on_login": False,
                                "provider": "openai-compatible",
                                "provider_preset": "custom",
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
                    insert_event(conn, CorrectionEvent("zuihuo", "zuihou", "最后", source="manual"))
                    insert_event(conn, CorrectionEvent("anil", "anli", "案例", source="manual"))
                    upsert_rules(
                        conn,
                        [
                            LearnedRule("zuihuo", "zuihou", "最后", 0.9, 150000, 2, "manual", enabled=False),
                            LearnedRule("anil", "anli", "案例", 0.95, 151000, 3, "manual", enabled=True),
                        ],
                    )

                response = api.list_correction_records("pinyin")

                self.assertTrue(response["ok"])
                self.assertEqual([event["wrongPinyin"] for event in response["events"]], ["anil", "zuihuo"])
                self.assertEqual(len(response["rules"]), 1)
                self.assertEqual(response["rules"][0]["committedText"], "案例")
                self.assertIn("storagePaths", api.load_state()["meta"])
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data

    def test_update_and_delete_correction_records(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                db_path = Path(tmp) / "ai-ime.db"
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=db_path)
                with closing(connect(db_path)) as conn:
                    init_db(conn)
                    event_id = insert_event(
                        conn,
                        CorrectionEvent(
                            "xainzai",
                            "xianzai",
                            "现在",
                            wrong_committed_text="喜爱能在",
                            source="test",
                        ),
                    )

                response = api.update_correction_record(
                    "events",
                    event_id,
                    {
                        "wrongPinyin": "xainzai",
                        "correctPinyin": "xianzai",
                        "committedText": "现在",
                        "wrongCommittedText": "喜爱能再",
                    },
                )
                self.assertTrue(response["ok"])
                self.assertEqual(api.list_correction_records()["events"][0]["wrongCommittedText"], "喜爱能再")

                delete_response = api.delete_correction_record("events", event_id)
                self.assertTrue(delete_response["ok"])
                self.assertEqual(api.list_correction_records()["events"], [])
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data

    def test_load_state_disables_unsupported_local_auto_rules(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                db_path = Path(tmp) / "ai-ime.db"
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=db_path)
                with closing(connect(db_path)) as conn:
                    init_db(conn)
                    insert_event(conn, CorrectionEvent("hen", "n", "很", source="auto-ui"))
                    insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在", source="auto-ui"))
                    upsert_rules(
                        conn,
                        [
                            LearnedRule("hen", "n", "很", 0.8, 140000, 1, "edit_distance_2", provider="rule"),
                            LearnedRule("xainzai", "xianzai", "现在", 0.9, 150000, 1, "adjacent_transposition", provider="rule"),
                        ],
                    )

                state = api.load_state()
                with closing(connect(db_path)) as conn:
                    init_db(conn)
                    enabled_rules = list_rules(conn, enabled_only=True)

                self.assertTrue(state["ok"])
                self.assertEqual([(rule.wrong_pinyin, rule.correct_pinyin) for rule in enabled_rules], [("xainzai", "xianzai")])
                self.assertEqual(state["meta"]["enabledRulesCount"], 1)
                self.assertEqual(state["meta"]["rulesCount"], 2)
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

    def test_load_state_repairs_enabled_startup_registration(self) -> None:
        old_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                save_app_settings(AppSettings(start_on_login=True))
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=Path(tmp) / "ai-ime.db")

                with patch("ai_ime.ui_api.sync_start_on_login", return_value=True) as mocked_startup:
                    state = api.load_state()

                self.assertTrue(state["settings"]["start_on_login"])
                mocked_startup.assert_called_once_with(True)
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

    def test_run_analysis_now_forces_provider_and_returns_visible_rules(self) -> None:
        class MixedProvider:
            def analyze_events(self, events, keylog_entries=None):
                return [
                    LearnedRule(
                        wrong_pinyin="xainzai",
                        correct_pinyin="xianzai",
                        committed_text="现在",
                        confidence=0.8,
                        weight=141000,
                        count=1,
                        mistake_type="adjacent_transposition",
                        provider="fake",
                    ),
                    LearnedRule(
                        wrong_pinyin="hen",
                        correct_pinyin="n",
                        committed_text="很",
                        confidence=0.9,
                        weight=150000,
                        count=1,
                        mistake_type="unknown",
                        provider="fake",
                    ),
                ]

        old_local_app_data = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = str(Path(tmp) / "LocalAppData")
                db_path = Path(tmp) / "ai-ime.db"
                keylog_path = Path(tmp) / "keylog.jsonl"
                api = SettingsApi(env_path=Path(tmp) / ".env", db_path=db_path)
                with closing(connect(db_path)) as conn:
                    init_db(conn)
                    insert_event(conn, CorrectionEvent("xainzai", "xianzai", "现在", source="auto-ui"))
                    insert_event(conn, CorrectionEvent("hen", "n", "很", source="auto-ui"))

                with patch("ai_ime.analysis_scheduler._build_provider", return_value=MixedProvider()), patch(
                    "ai_ime.analysis_scheduler._append_learning_log"
                ):
                    response = api.run_analysis_now(
                        {
                            "settings": {
                                "auto_analyze_with_ai": False,
                                "provider": "openai-compatible",
                                "openai_base_url": "http://relay.test/v1",
                                "openai_model": "gpt-5.4-mini",
                                "keylog_file": str(keylog_path),
                            }
                        }
                    )

                self.assertTrue(response["ok"])
                self.assertTrue(response["attempted"])
                self.assertEqual(response["sentEventCount"], 2)
                self.assertEqual(response["returnedRules"], 2)
                self.assertEqual(response["upsertedRules"], 1)
                self.assertEqual(response["rejectedRules"], 1)
                self.assertEqual(response["rules"][0]["wrongPinyin"], "xainzai")
                self.assertEqual(response["rejectedRuleItems"][0]["wrongPinyin"], "hen")
        finally:
            if old_local_app_data is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = old_local_app_data


if __name__ == "__main__":
    unittest.main()
