import unittest

from ai_ime.correction.detector import CorrectionDetector, KeyStroke, detect_from_sequence, parse_sequence


class DetectorTests(unittest.TestCase):
    def test_detect_from_sequence(self) -> None:
        event = detect_from_sequence("xainzai{backspace*7}xianzai{space}", committed_text="现在")

        self.assertIsNotNone(event)
        self.assertEqual(event.wrong_pinyin, "xainzai")
        self.assertEqual(event.correct_pinyin, "xianzai")
        self.assertEqual(event.committed_text, "现在")
        self.assertEqual(event.commit_key, "space")

    def test_detect_from_sequence_with_candidate_number(self) -> None:
        event = detect_from_sequence("xainzai{backspace*7}xianzai{1}", committed_text="现在")

        self.assertIsNotNone(event)
        self.assertEqual(event.wrong_pinyin, "xainzai")
        self.assertEqual(event.correct_pinyin, "xianzai")
        self.assertEqual(event.committed_text, "现在")
        self.assertEqual(event.commit_key, "1")

    def test_detector_requires_committed_text(self) -> None:
        detector = CorrectionDetector()
        for stroke in parse_sequence("xainzai{delete}xianzai{enter}"):
            event = detector.feed(stroke)
        self.assertIsNone(event)

    def test_detector_emits_pending_correction_without_committed_text(self) -> None:
        detector = CorrectionDetector()
        pending = None
        for stroke in parse_sequence("xainzai{delete}xianzai{enter}"):
            pending = detector.feed_pending(stroke) or pending

        self.assertIsNotNone(pending)
        self.assertEqual(pending.wrong_pinyin, "xainzai")
        self.assertEqual(pending.correct_pinyin, "xianzai")
        self.assertEqual(pending.commit_key, "enter")

    def test_detector_ignores_same_pinyin(self) -> None:
        event = detect_from_sequence("xianzai{backspace}xianzai{space}", committed_text="现在")

        self.assertIsNone(event)

    def test_parse_sequence_unknown_token_as_chars(self) -> None:
        strokes = parse_sequence("a{unknown}b")

        self.assertEqual(strokes[0], KeyStroke("char", "a"))
        self.assertEqual(strokes[-1], KeyStroke("char", "b"))
        self.assertEqual([stroke.value for stroke in strokes[1:-1]], list("{unknown}"))


if __name__ == "__main__":
    unittest.main()
