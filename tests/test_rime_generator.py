import tempfile
import unittest
from pathlib import Path

from ai_ime.models import LearnedRule
from ai_ime.rime.generator import export_rime_files, render_dictionary, render_schema_patch


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

    def test_render_schema_patch_adds_dedicated_typo_translator(self) -> None:
        content = render_schema_patch()

        self.assertIn("engine/translators/@before 1: table_translator@ai_typo", content)
        self.assertIn("ai_typo:\n    dictionary: ai_typo", content)
        self.assertNotIn("translator/dictionary: ai_typo", content)

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
            self.assertIn("现在\txainzai", dictionary_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
