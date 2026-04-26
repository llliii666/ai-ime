from __future__ import annotations

import json

from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent


SYSTEM_PROMPT = """You analyze Chinese pinyin typo correction events.
Return only JSON. Do not include markdown.
Your output must match this shape:
{
  "rules": [
    {
      "wrong_pinyin": "xainzai",
      "correct_pinyin": "xianzai",
      "committed_text": "现在",
      "confidence": 0.8,
      "weight": 141000,
      "mistake_type": "adjacent_transposition",
      "explanation": "short reason",
      "count": 1
    }
  ]
}
Only recommend rules supported by the events. Use confidence from 0.0 to 1.0.
Use higher weight for more confident and repeated rules.
Keyboard logs are optional context only. Do not invent a rule from keyboard logs alone.
"""


def build_user_prompt(events: list[CorrectionEvent], keylog_entries: list[KeyLogEntry] | None = None) -> str:
    payload = {
        "events": [
            {
                "wrong_pinyin": event.wrong_pinyin,
                "correct_pinyin": event.correct_pinyin,
                "committed_text": event.committed_text,
                "commit_key": event.commit_key,
                "source": event.source,
            }
            for event in events
        ],
        "keylog_entries": [
            {
                "timestamp": entry.timestamp,
                "event_type": entry.event_type,
                "name": entry.name,
                "scan_code": entry.scan_code,
            }
            for entry in (keylog_entries or [])
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
