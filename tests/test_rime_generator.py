import tempfile
import unittest
from pathlib import Path

from ai_ime.models import LearnedRule
from ai_ime.rime.generator import (
    export_rime_files,
    remove_lua_bootstrap,
    render_dictionary,
    render_lua_logger,
    render_schema_patch,
    render_support_schema,
)


class RimeGeneratorTests(unittest.TestCase):
    def test_render_dictionary_contains_typo_entry(self) -> None:
        content = render_dictionary(
            [
                LearnedRule(
                    wrong_pinyin="xainzai",
                    correct_pinyin="xianzai",
                    committed_text="现在",
                    confidence=0.8,
                    weight=141000,
                    count=1,
                    mistake_type="adjacent_transposition",
                )
            ]
        )
        self.assertNotIn("import_tables:", content)
        self.assertIn("use_preset_vocabulary: false", content)
        self.assertIn("现在\txainzai\t141000", content)

    def test_render_dictionary_can_import_base_dictionary_when_requested(self) -> None:
        content = render_dictionary([], base_dictionary="rime_ice")

        self.assertIn("import_tables:\n  - rime_ice", content)

    def test_render_dictionary_dedupes_entries_by_highest_weight(self) -> None:
        content = render_dictionary(
            [
                LearnedRule(
                    wrong_pinyin="xainzai",
                    correct_pinyin="xianzai",
                    committed_text="现在",
                    confidence=0.8,
                    weight=141000,
                    count=1,
                    mistake_type="adjacent_transposition",
                ),
                LearnedRule(
                    wrong_pinyin="xainzai",
                    correct_pinyin="xianzai",
                    committed_text="现在",
                    confidence=0.95,
                    weight=151000,
                    count=1,
                    mistake_type="adjacent_transposition",
                    provider="openai-compatible",
                ),
            ]
        )

        self.assertEqual(content.count("现在\txainzai"), 1)
        self.assertIn("现在\txainzai\t151000", content)

    def test_render_dictionary_rejects_control_characters_in_rule_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid dictionary entry"):
            render_dictionary(
                [
                    LearnedRule(
                        wrong_pinyin="xain\tzai",
                        correct_pinyin="xianzai",
                        committed_text="鐜板湪",
                        confidence=0.8,
                        weight=141000,
                        count=1,
                        mistake_type="adjacent_transposition",
                    )
                ]
            )

    def test_render_schema_patch_adds_dedicated_typo_translator(self) -> None:
        content = render_schema_patch()

        self.assertIn("schema/dependencies/@next: ai_typo", content)
        self.assertIn("engine/translators/@before 1: table_translator@ai_typo", content)
        self.assertIn("engine/processors/@before 0: lua_processor@*ai_ime_logger", content)
        self.assertIn("ai_typo:\n    dictionary: ai_typo", content)
        self.assertIn("enable_completion: false", content)
        self.assertNotIn("translator/dictionary: ai_typo", content)

    def test_render_support_schema_compiles_typo_dictionary(self) -> None:
        content = render_support_schema()

        self.assertIn("schema_id: ai_typo", content)
        self.assertIn("translator:\n  dictionary: ai_typo", content)
        self.assertIn("enable_completion: false", content)
        self.assertIn("table_translator", content)

    def test_render_lua_logger_writes_semantic_commit_fields(self) -> None:
        content = render_lua_logger(Path(r"C:\Users\tester\AppData\Local\AIIME\keylog.jsonl"))

        self.assertIn("LOG_PATH = [[C:\\Users\\tester\\AppData\\Local\\AIIME\\keylog.jsonl]]", content)
        self.assertIn('LOCK_PATH = LOG_PATH .. ".lock"', content)
        self.assertIn("local function acquire_lock()", content)
        self.assertIn("write_string_field", content)
        self.assertIn('write_string_field(file, first, "source", "rime-lua", true)', content)
        self.assertIn('write_string_field(file, first, "candidate_text", event.candidate_text, false)', content)
        self.assertIn("commit_notifier:connect", content)

    def test_remove_lua_bootstrap_removes_generated_block(self) -> None:
        content = "-- custom\n-- AI IME logger bootstrap: start\nold = true\n-- AI IME logger bootstrap: end\n"

        cleaned = remove_lua_bootstrap(content)

        self.assertEqual(cleaned, "-- custom\n")

    def test_export_rime_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dictionary_path, patch_path = export_rime_files(
                [
                    LearnedRule(
                        wrong_pinyin="xainzai",
                        correct_pinyin="xianzai",
                        committed_text="现在",
                        confidence=0.8,
                        weight=141000,
                        count=1,
                        mistake_type="adjacent_transposition",
                    )
                ],
                Path(tmp),
            )
            self.assertTrue(dictionary_path.exists())
            self.assertTrue(patch_path.exists())
            self.assertEqual(patch_path.name, "rime_ice.custom.yaml")
            self.assertTrue((Path(tmp) / "ai_typo.schema.yaml").exists())
            self.assertIn("现在\txainzai", dictionary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
