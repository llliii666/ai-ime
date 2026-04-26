import unittest

from ai_ime.text_capture import FocusTextReader, changed_segment, extract_committed_text


class FakeAutomation:
    def __init__(self, focused: object) -> None:
        self.focused = focused

    def GetFocusedControl(self) -> object:
        return self.focused


class FakeControl:
    def __init__(self, value: str = "", text: str = "", legacy: str = "", parent: object | None = None) -> None:
        self._value = value
        self._text = text
        self._legacy = legacy
        self._parent = parent

    def GetValuePattern(self) -> object:
        if self._value:
            return type("ValuePattern", (), {"Value": self._value})()
        raise RuntimeError("no value")

    def GetTextPattern(self) -> object:
        if self._text:
            range_obj = type("Range", (), {"GetText": lambda _self, _count: self._text})()
            return type("TextPattern", (), {"DocumentRange": range_obj})()
        raise RuntimeError("no text")

    def GetLegacyIAccessiblePattern(self) -> object:
        if self._legacy:
            return type("LegacyPattern", (), {"Value": self._legacy, "Name": ""})()
        raise RuntimeError("no legacy")

    def GetParentControl(self) -> object | None:
        return self._parent


class TextCaptureTests(unittest.TestCase):
    def test_changed_segment_extracts_inserted_middle_text(self) -> None:
        self.assertEqual(changed_segment("我很好", "我现在很好"), "现在")

    def test_extract_committed_text_uses_cjk_insert(self) -> None:
        self.assertEqual(extract_committed_text("我", "我现在"), "现在")

    def test_extract_committed_text_ignores_non_cjk_insert(self) -> None:
        self.assertEqual(extract_committed_text("abc", "abcd"), "")

    def test_extract_committed_text_requires_before_and_after(self) -> None:
        self.assertEqual(extract_committed_text(None, "现在"), "")

    def test_focus_text_reader_walks_parent_controls(self) -> None:
        parent = FakeControl(value="我现在")
        child = FakeControl(parent=parent)

        reader = FocusTextReader(automation=FakeAutomation(child))

        self.assertEqual(reader.read_text(), "我现在")

    def test_focus_text_reader_uses_legacy_accessible_pattern(self) -> None:
        control = FakeControl(legacy="我现在")

        reader = FocusTextReader(automation=FakeAutomation(control))

        self.assertEqual(reader.read_text(), "我现在")


if __name__ == "__main__":
    unittest.main()
