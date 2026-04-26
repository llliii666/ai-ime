from __future__ import annotations

import re


_PINYIN_RE = re.compile(r"[a-z]+")


def normalize_pinyin(value: str) -> str:
    return "".join(_PINYIN_RE.findall(value.lower()))
