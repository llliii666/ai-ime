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
        self.assertIn("import_tables:", content)
        self.assertIn("现在\txainzai\t141000", content)

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

    def test_render_schema_patch_points_to_dictionary(self) -> None:
        self.assertIn("translator/dictionary: ai_typo", render_schema_patch())

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
