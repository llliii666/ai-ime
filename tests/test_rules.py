import unittest

from ai_ime.correction.normalize import normalize_pinyin
from ai_ime.correction.rules import aggregate_rules, classify_mistake, levenshtein_distance
from ai_ime.models import CorrectionEvent


class RuleTests(unittest.TestCase):
    def test_normalize_pinyin_keeps_letters_only(self) -> None:
        self.assertEqual(normalize_pinyin(" Xain-Zai 123 "), "xainzai")

    def test_classify_adjacent_transposition(self) -> None:
        self.assertEqual(classify_mistake("xainzai", "xianzai"), "adjacent_transposition")

    def test_levenshtein_distance(self) -> None:
        self.assertEqual(levenshtein_distance("xinzai", "xianzai"), 1)

    def test_aggregate_rules_skips_same_pinyin(self) -> None:
        rules = aggregate_rules(
            [
                CorrectionEvent("xainzai", "xianzai", "现在"),
                CorrectionEvent("xianzai", "xianzai", "现在"),
            ]
        )
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].wrong_pinyin, "xainzai")
        self.assertEqual(rules[0].committed_text, "现在")
        self.assertGreater(rules[0].confidence, 0.7)

    def test_aggregate_rules_rejects_low_confidence_auto_fragments(self) -> None:
        rules = aggregate_rules(
            [
                CorrectionEvent("hen", "n", "很", source="auto-ui"),
                CorrectionEvent("w", "zai", "再", source="auto-ui"),
                CorrectionEvent("woami", "daingshi", "我当时", source="auto-ui"),
                CorrectionEvent("xainzai", "xianzai", "现在", source="auto-ui"),
                CorrectionEvent("xuenaze", "xuanze", "选择", source="manual-ui"),
            ]
        )

        triples = {(rule.wrong_pinyin, rule.correct_pinyin, rule.committed_text) for rule in rules}
        self.assertNotIn(("hen", "n", "很"), triples)
        self.assertNotIn(("w", "zai", "再"), triples)
        self.assertNotIn(("woami", "daingshi", "我当时"), triples)
        self.assertIn(("xainzai", "xianzai", "现在"), triples)
        self.assertIn(("xuenaze", "xuanze", "选择"), triples)


if __name__ == "__main__":
    unittest.main()
