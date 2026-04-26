import unittest

from ai_ime.text_capture import changed_segment, extract_committed_text


class TextCaptureTests(unittest.TestCase):
    def test_changed_segment_extracts_inserted_middle_text(self) -> None:
        self.assertEqual(changed_segment("我很好", "我现在很好"), "现在")

    def test_extract_committed_text_uses_cjk_insert(self) -> None:
        self.assertEqual(extract_committed_text("我", "我现在"), "现在")

    def test_extract_committed_text_ignores_non_cjk_insert(self) -> None:
        self.assertEqual(extract_committed_text("abc", "abcd"), "")

    def test_extract_committed_text_requires_before_and_after(self) -> None:
        self.assertEqual(extract_committed_text(None, "现在"), "")


if __name__ == "__main__":
    unittest.main()
