from __future__ import annotations

import re


CJK_RUN_PATTERN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")


class FocusTextReader:
    def read_text(self) -> str | None:
        try:
            import uiautomation as automation  # type: ignore[import-not-found]
        except Exception:
            return None

        try:
            control = automation.GetFocusedControl()
        except Exception:
            return None
        if control is None:
            return None

        for getter in (_read_value_pattern, _read_text_pattern):
            text = getter(control)
            if text:
                return text
        return None


def extract_committed_text(before: str | None, after: str | None, max_chars: int = 16) -> str:
    if before is None or after is None or before == after:
        return ""
    inserted = changed_segment(before, after)
    if not inserted:
        return ""
    match = _last_cjk_run(inserted)
    if match:
        return match[-max_chars:]
    return ""


def changed_segment(before: str, after: str) -> str:
    prefix = _common_prefix_length(before, after)
    before_tail = before[prefix:]
    after_tail = after[prefix:]
    suffix = _common_suffix_length(before_tail, after_tail)
    if suffix:
        return after_tail[:-suffix].strip()
    return after_tail.strip()


def _read_value_pattern(control: object) -> str | None:
    try:
        pattern = control.GetValuePattern()  # type: ignore[attr-defined]
        value = getattr(pattern, "Value", None)
    except Exception:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None


def _read_text_pattern(control: object) -> str | None:
    try:
        pattern = control.GetTextPattern()  # type: ignore[attr-defined]
        document_range = getattr(pattern, "DocumentRange", None)
        value = document_range.GetText(-1) if document_range is not None else None
    except Exception:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None


def _last_cjk_run(value: str) -> str:
    matches = CJK_RUN_PATTERN.findall(value)
    return matches[-1] if matches else ""


def _common_prefix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def _common_suffix_length(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[-(index + 1)] == right[-(index + 1)]:
        index += 1
    return index
