import unittest

from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent, LearnedRule
from ai_ime.providers.base import ProviderError
from ai_ime.providers.prompt import SYSTEM_PROMPT, build_user_prompt
from ai_ime.providers.schema import parse_analysis_json, parse_rules_json


class ProviderSchemaTests(unittest.TestCase):
    def test_parse_rules_json_validates_and_normalizes(self) -> None:
        rules = parse_rules_json(
            """
            {
              "rules": [
                {
                  "wrong_pinyin": "Xain-Zai",
                  "correct_pinyin": "xianzai",
                  "committed_text": "现在",
                  "confidence": 1.2,
                  "weight": 150000,
                  "mistake_type": "adjacent_transposition",
                  "explanation": "observed pattern",
                  "count": 2
                }
              ]
            }
            """,
            provider="test",
        )

        self.assertEqual(rules[0].wrong_pinyin, "xainzai")
        self.assertEqual(rules[0].confidence, 1.0)
        self.assertEqual(rules[0].weight, 152000)
        self.assertEqual(rules[0].provider, "test")

    def test_parse_rules_json_rejects_bad_shape(self) -> None:
        with self.assertRaises(ProviderError):
            parse_rules_json('{"rules": {}}', provider="test")

    def test_parse_analysis_json_includes_invalid_rules(self) -> None:
        result = parse_analysis_json(
            """
            {
              "rules": [],
              "invalid_rules": [
                {
                  "id": 76,
                  "wrong_pinyin": "zhegeshiyiduanhenchangdepinyin",
                  "correct_pinyin": "zhegeshiyiduanhenchangdepinyin",
                  "committed_text": "这是一段很长的候选内容",
                  "action": "delete",
                  "reason": "long phrase"
                }
              ]
            }
            """,
            provider="test",
        )

        self.assertEqual(len(result.rules), 0)
        self.assertEqual(result.invalid_rules[0].rule_id, 76)
        self.assertEqual(result.invalid_rules[0].action, "delete")
        self.assertEqual(result.invalid_rules[0].reason, "long phrase")

    def test_prompt_can_include_keylog_context(self) -> None:
        prompt = build_user_prompt(
            [CorrectionEvent("xainzai", "xianzai", "现在", wrong_committed_text="喜爱能在")],
            keylog_entries=[
                KeyLogEntry(
                    timestamp=1.0,
                    event_type="commit",
                    name="xianzai",
                    pinyin="xianzai",
                    committed_text="现在",
                    role="rime_commit",
                    source="rime-lua",
                    candidate_text="现在",
                    selection_index=0,
                    commit_key="1",
                )
            ],
            existing_rules=[
                LearnedRule(
                    id=76,
                    wrong_pinyin="henchang",
                    correct_pinyin="henchang",
                    committed_text="很长的一段候选内容",
                    confidence=0.92,
                    weight=160000,
                    count=1,
                    mistake_type="unknown",
                    provider="openai-compatible",
                )
            ],
        )

        self.assertIn('"keylog_entries"', prompt)
        self.assertIn('"existing_rules"', prompt)
        self.assertIn('"id": 76', prompt)
        self.assertIn('"wrong_committed_text": "喜爱能在"', prompt)
        self.assertIn('"role": "rime_commit"', prompt)
        self.assertIn('"source": "rime-lua"', prompt)
        self.assertIn('"candidate_text": "现在"', prompt)
        self.assertIn("不能单独生成规则", SYSTEM_PROMPT)
        self.assertIn("rime_commit(错误拼音/错误中文) -> backspace/delete -> rime_commit", SYSTEM_PROMPT)
        self.assertIn("existing_rules", SYSTEM_PROMPT)
        self.assertIn("invalid_rules", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
