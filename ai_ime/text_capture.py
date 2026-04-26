from __future__ import annotations

import re


CJK_RUN_PATTERN = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]+")


class FocusTextReader:
    def __init__(self, automation: object | None = None) -> None:
        self._automation = automation

    def read_text(self) -> str | None:
        automation = self._automation or _load_automation()
        if automation is None:
            return None

        try:
            control = automation.GetFocusedControl()  # type: ignore[attr-defined]
        except Exception:
            return None
        if control is None:
            return None

        for candidate in _control_chain(control):
            for getter in (_read_value_pattern, _read_text_pattern, _read_legacy_accessible_pattern):
                text = getter(candidate)
                if text:
                    return text
        return None


def _load_automation() -> object | None:
    try:
        import uiautomation as automation  # type: ignore[import-not-found]
    except Exception:
        return None
    return automation


def _control_chain(control: object, max_depth: int = 8) -> list[object]:
    chain: list[object] = []
    current = control
    seen: set[int] = set()
    for _ in range(max_depth):
        identity = id(current)
        if identity in seen:
            break
        seen.add(identity)
        chain.append(current)
        parent = _parent_control(current)
        if parent is None:
            break
        current = parent
    return chain


def _parent_control(control: object) -> object | None:
    for method_name in ("GetParentControl", "GetParent"):
        method = getattr(control, method_name, None)
        if not callable(method):
            continue
        try:
            parent = method()
        except Exception:
            continue
        if parent is not None:
            return parent
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


def _read_legacy_accessible_pattern(control: object) -> str | None:
    try:
        pattern = control.GetLegacyIAccessiblePattern()  # type: ignore[attr-defined]
    except Exception:
        return None
    for attr in ("Value", "Name"):
        value = getattr(pattern, attr, None)
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
