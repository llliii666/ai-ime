from __future__ import annotations

from dataclasses import dataclass

from ai_ime.correction.normalize import normalize_pinyin
from ai_ime.models import CorrectionEvent

CANDIDATE_SELECTION_KEYS = {str(index) for index in range(10)}
CONFIRM_KEYS = {"space", "enter", *CANDIDATE_SELECTION_KEYS}
DELETE_KEYS = {"backspace", "delete"}


@dataclass(frozen=True)
class KeyStroke:
    kind: str
    value: str = ""


@dataclass(frozen=True)
class PendingCorrection:
    wrong_pinyin: str
    correct_pinyin: str
    commit_key: str
    wrong_committed_text: str = ""

    def to_event(
        self,
        committed_text: str,
        source: str = "detector",
        wrong_committed_text: str | None = None,
    ) -> CorrectionEvent | None:
        text = committed_text.strip()
        if not text:
            return None
        return CorrectionEvent(
            wrong_pinyin=self.wrong_pinyin,
            correct_pinyin=self.correct_pinyin,
            committed_text=text,
            commit_key=self.commit_key,
            source=source,
            wrong_committed_text=wrong_committed_text or self.wrong_committed_text or None,
        )


class CorrectionDetector:
    def __init__(self) -> None:
        self._current = ""
        self._wrong: str | None = None
        self._correct = ""
        self._editing = False
        self._wrong_confirmed = False
        self._wrong_committed_text = ""

    def feed(self, stroke: KeyStroke, committed_text: str | None = None) -> CorrectionEvent | None:
        pending = self.feed_pending(stroke)
        if pending is None or not committed_text:
            return None
        return pending.to_event(committed_text)

    def feed_pending(self, stroke: KeyStroke) -> PendingCorrection | None:
        if stroke.kind == "char":
            char = normalize_pinyin(stroke.value)
            if not char:
                return None
            if self._editing:
                self._correct += char
            else:
                if self._wrong_confirmed:
                    self.reset()
                self._current += char
            return None

        if stroke.kind in DELETE_KEYS:
            if not self._editing and self._wrong_confirmed and self._wrong:
                self._correct = ""
                self._editing = True
            elif not self._editing and self._current:
                self._wrong = self._current
                self._correct = ""
                self._editing = True
            return None

        if stroke.kind in CONFIRM_KEYS:
            if not self._editing and self._current:
                self._wrong = normalize_pinyin(self._current)
                self._current = ""
                self._wrong_confirmed = bool(self._wrong)
                return None
            pending = self._build_pending(stroke.kind)
            self.reset()
            return pending

        if stroke.kind == "reset":
            self.reset()
            return None

        return None

    def reset(self) -> None:
        self._current = ""
        self._wrong = None
        self._correct = ""
        self._editing = False
        self._wrong_confirmed = False
        self._wrong_committed_text = ""

    def confirming_pinyin_candidate(self) -> str:
        if self._editing or self._wrong_confirmed:
            return ""
        return normalize_pinyin(self._current)

    def note_wrong_committed_text(self, text: str) -> None:
        self._wrong_committed_text = text.strip()

    def _build_pending(self, commit_key: str) -> PendingCorrection | None:
        if not self._wrong or not self._correct:
            return None
        wrong = normalize_pinyin(self._wrong)
        correct = normalize_pinyin(self._correct)
        if not wrong or not correct or wrong == correct:
            return None
        return PendingCorrection(
            wrong_pinyin=wrong,
            correct_pinyin=correct,
            commit_key=commit_key,
            wrong_committed_text=self._wrong_committed_text,
        )


def parse_sequence(sequence: str) -> list[KeyStroke]:
    strokes: list[KeyStroke] = []
    index = 0
    while index < len(sequence):
        char = sequence[index]
        if char == "{":
            end = sequence.find("}", index + 1)
            if end == -1:
                strokes.append(KeyStroke("char", char))
                index += 1
                continue
            token = sequence[index + 1 : end].strip().lower()
            strokes.extend(_parse_token(token))
            index = end + 1
            continue
        strokes.append(KeyStroke("char", char))
        index += 1
    return strokes


def detect_from_sequence(sequence: str, committed_text: str) -> CorrectionEvent | None:
    detector = CorrectionDetector()
    event: CorrectionEvent | None = None
    for stroke in parse_sequence(sequence):
        event = detector.feed(stroke, committed_text=committed_text if stroke.kind in CONFIRM_KEYS else None) or event
    return event


def _parse_token(token: str) -> list[KeyStroke]:
    if "*" in token:
        name, count_text = token.split("*", 1)
        try:
            count = max(1, int(count_text))
        except ValueError:
            count = 1
    else:
        name = token
        count = 1
    name = name.strip()
    if name in {"bs", "backspace"}:
        kind = "backspace"
    elif name in {"del", "delete"}:
        kind = "delete"
    elif name in {"space", "enter", "reset", *CANDIDATE_SELECTION_KEYS}:
        kind = name
    else:
        return [KeyStroke("char", char) for char in f"{{{token}}}"]
    return [KeyStroke(kind) for _ in range(count)]
