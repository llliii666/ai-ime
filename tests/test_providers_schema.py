import unittest

from ai_ime.providers.base import ProviderError
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


if __name__ == "__main__":
    unittest.main()
