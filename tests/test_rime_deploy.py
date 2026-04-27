import tempfile
import unittest
from pathlib import Path

from ai_ime.models import LearnedRule
from ai_ime.rime.deploy import deploy_rime_files, merge_schema_patch, rollback_backup


def sample_rules() -> list[LearnedRule]:
    return [
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


class RimeDeployTests(unittest.TestCase):
    def test_deploy_writes_files_and_rollback_removes_new_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rime_dir = Path(tmp)
            result = deploy_rime_files(sample_rules(), rime_dir)

            self.assertTrue(result.dictionary_path.exists())
            self.assertTrue(result.support_schema_path.exists())
            self.assertTrue(result.patch_path.exists())
            self.assertTrue(result.lua_path.exists())
            self.assertIsNone(result.rime_lua_path)
            self.assertTrue(result.patch_applied)

            restored = rollback_backup(rime_dir, result.backup_dir)
            self.assertIn(result.dictionary_path, restored)
            self.assertIn(result.support_schema_path, restored)
            self.assertIn(result.lua_path, restored)
            self.assertFalse(result.dictionary_path.exists())
            self.assertFalse(result.support_schema_path.exists())
            self.assertFalse(result.patch_path.exists())
            self.assertFalse(result.lua_path.exists())

    def test_existing_patch_is_merged_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rime_dir = Path(tmp)
            existing_patch = rime_dir / "luna_pinyin.custom.yaml"
            existing_patch.write_text("patch:\n  menu/page_size: 9\n", encoding="utf-8")

            result = deploy_rime_files(sample_rules(), rime_dir)

            self.assertTrue(result.patch_applied)
            content = existing_patch.read_text(encoding="utf-8")
            self.assertIn("schema/dependencies/@next: ai_typo", content)
            self.assertIn("engine/translators/@before 1: table_translator@ai_typo", content)
            self.assertIn("engine/processors/@before 0: lua_processor@*ai_ime_logger", content)
            self.assertIn("ai_typo:\n    dictionary: ai_typo", content)
            self.assertIn("menu/page_size: 9", content)
            self.assertEqual(result.patch_path, existing_patch)

    def test_deploy_removes_legacy_rime_lua_bootstrap_without_replacing_custom_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rime_dir = Path(tmp)
            rime_lua = rime_dir / "rime.lua"
            rime_lua.write_text(
                "local keep = true\n"
                "-- AI IME logger bootstrap: start\n"
                "old = true\n"
                "-- AI IME logger bootstrap: end\n",
                encoding="utf-8",
            )

            result = deploy_rime_files(sample_rules(), rime_dir, semantic_log_path=Path(tmp) / "keylog.jsonl")

            self.assertTrue(result.lua_path.exists())
            self.assertIn("LOG_PATH = [[" + str(Path(tmp) / "keylog.jsonl") + "]]", result.lua_path.read_text(encoding="utf-8"))
            content = rime_lua.read_text(encoding="utf-8")
            self.assertIn("local keep = true", content)
            self.assertNotIn("old = true", content)
            self.assertEqual(result.rime_lua_path, rime_lua)

    def test_merge_schema_patch_appends_top_level_patch(self) -> None:
        content = "__include: octagram\n\noctagram:\n  __patch:\n    translator/max_homophones: 5\n"

        merged = merge_schema_patch(content)

        self.assertIn("octagram:\n  __patch:\n    translator/max_homophones: 5", merged)
        self.assertIn("\npatch:\n  schema/dependencies/@next: ai_typo\n", merged)
        self.assertIn("engine/processors/@before 0: lua_processor@*ai_ime_logger", merged)
        self.assertIn("engine/translators/@before 1: table_translator@ai_typo", merged)

    def test_merge_schema_patch_removes_legacy_dictionary_override(self) -> None:
        content = "patch:\n  translator/dictionary: old_dict\n  menu/page_size: 9\n"

        merged = merge_schema_patch(content, dictionary_id="ai_typo")

        self.assertIn("translator/dictionary: old_dict", merged)
        self.assertIn("engine/translators/@before 1: table_translator@ai_typo", merged)

    def test_merge_schema_patch_removes_bad_ai_typo_dictionary_override(self) -> None:
        content = "patch:\n  translator/dictionary: ai_typo\n  menu/page_size: 9\n"

        merged = merge_schema_patch(content, dictionary_id="ai_typo")

        self.assertNotIn("translator/dictionary: ai_typo", merged)
        self.assertIn("engine/translators/@before 1: table_translator@ai_typo", merged)
        self.assertIn("menu/page_size: 9", merged)

    def test_merge_schema_patch_replaces_existing_typo_translator_block(self) -> None:
        content = (
            "patch:\n"
            "  engine/translators/@before 3: table_translator@ai_typo\n"
            "  ai_typo:\n"
            "    dictionary: old\n"
            "  menu/page_size: 9\n"
        )

        merged = merge_schema_patch(content, dictionary_id="ai_typo")

        self.assertNotIn("dictionary: old", merged)
        self.assertNotIn("@before 3", merged)
        self.assertIn("engine/processors/@before 0: lua_processor@*ai_ime_logger", merged)
        self.assertIn("engine/translators/@before 1: table_translator@ai_typo", merged)
        self.assertIn("ai_typo:\n    dictionary: ai_typo", merged)
        self.assertIn("menu/page_size: 9", merged)

    def test_merge_schema_patch_replaces_existing_lua_processor(self) -> None:
        content = (
            "patch:\n"
            "  engine/processors/@before 5: lua_processor@*ai_ime_logger\n"
            "  menu/page_size: 9\n"
        )

        merged = merge_schema_patch(content, dictionary_id="ai_typo")

        self.assertNotIn("@before 5", merged)
        self.assertEqual(merged.count("lua_processor@*ai_ime_logger"), 1)
        self.assertIn("menu/page_size: 9", merged)

    def test_merge_schema_patch_replaces_existing_schema_dependency(self) -> None:
        content = (
            "patch:\n"
            "  schema/dependencies/@before 0: ai_typo\n"
            "  menu/page_size: 9\n"
        )

        merged = merge_schema_patch(content, dictionary_id="ai_typo")

        self.assertNotIn("@before 0: ai_typo", merged)
        self.assertEqual(merged.count("schema/dependencies/@next: ai_typo"), 1)
        self.assertIn("menu/page_size: 9", merged)


if __name__ == "__main__":
    unittest.main()
