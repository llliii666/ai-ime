import unittest

from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent
from ai_ime.providers.base import ProviderError
from ai_ime.providers.prompt import SYSTEM_PROMPT, build_user_prompt
from ai_ime.providers.schema import parse_rules_json


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
                    role="correction",
                )
            ],
        )

        self.assertIn('"keylog_entries"', prompt)
        self.assertIn('"wrong_committed_text": "喜爱能在"', prompt)
        self.assertIn('"role": "correction"', prompt)
        self.assertIn("原始按键事件只能帮助理解操作顺序，不能单独生成规则", SYSTEM_PROMPT)
        self.assertIn("规则三元组必须严格来自证据", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
