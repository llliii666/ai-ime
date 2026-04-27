from __future__ import annotations

from collections import Counter, defaultdict

from ai_ime.correction.normalize import normalize_pinyin
from ai_ime.models import CorrectionEvent, LearnedRule


def classify_mistake(wrong: str, correct: str) -> str:
    if wrong == correct:
        return "same"
    if _is_adjacent_transposition(wrong, correct):
        return "adjacent_transposition"
    distance = levenshtein_distance(wrong, correct)
    if distance == 1:
        if len(wrong) + 1 == len(correct):
            return "missing_letter"
        if len(wrong) == len(correct) + 1:
            return "extra_letter"
        return "substitution"
    if distance == 2:
        return "edit_distance_2"
    return "unknown"


def aggregate_rules(events: list[CorrectionEvent], min_count: int = 1) -> list[LearnedRule]:
    groups: Counter[tuple[str, str, str]] = Counter()
    sources: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    for event in events:
        wrong = normalize_pinyin(event.wrong_pinyin)
        correct = normalize_pinyin(event.correct_pinyin)
        text = event.committed_text.strip()
        if not wrong or not correct or not text:
            continue
        if wrong == correct:
            continue
        groups[(wrong, correct, text)] += 1
        sources[(wrong, correct, text)].add(event.source)

    rules: list[LearnedRule] = []
    for (wrong, correct, text), count in groups.items():
        if count < min_count:
            continue
        mistake_type = classify_mistake(wrong, correct)
        if not should_learn_rule(wrong, correct, mistake_type, sources[(wrong, correct, text)], count):
            continue
        confidence = _confidence_for(mistake_type, count)
        weight = _weight_for(confidence, count)
        rules.append(
            LearnedRule(
                wrong_pinyin=wrong,
                correct_pinyin=correct,
                committed_text=text,
                confidence=confidence,
                weight=weight,
                count=count,
                mistake_type=mistake_type,
                explanation=f"{mistake_type}; observed {count} time(s)",
            )
        )
    return sorted(rules, key=lambda rule: (-rule.confidence, -rule.count, rule.wrong_pinyin))


def should_learn_rule(
    wrong: str,
    correct: str,
    mistake_type: str,
    sources: set[str] | frozenset[str],
    count: int = 1,
) -> bool:
    if not wrong or not correct or wrong == correct:
        return False
    if any(not _is_auto_source(source) for source in sources):
        return True
    if mistake_type == "unknown":
        return False
    if min(len(wrong), len(correct)) < 3:
        return False
    return count >= 1


def event_supports_rule(event: CorrectionEvent) -> bool:
    wrong = normalize_pinyin(event.wrong_pinyin)
    correct = normalize_pinyin(event.correct_pinyin)
    text = event.committed_text.strip()
    if not wrong or not correct or not text or wrong == correct:
        return False
    return should_learn_rule(wrong, correct, classify_mistake(wrong, correct), {event.source}, 1)


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            substitution = previous[right_index - 1] + (left_char != right_char)
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]


def _is_adjacent_transposition(wrong: str, correct: str) -> bool:
    if len(wrong) != len(correct):
        return False
    differences = [index for index, pair in enumerate(zip(wrong, correct, strict=True)) if pair[0] != pair[1]]
    if len(differences) != 2:
        return False
    first, second = differences
    return second == first + 1 and wrong[first] == correct[second] and wrong[second] == correct[first]


def _is_auto_source(source: str) -> bool:
    return source.startswith("auto")


def _confidence_for(mistake_type: str, count: int) -> float:
    type_bonus = {
        "adjacent_transposition": 0.25,
        "missing_letter": 0.2,
        "extra_letter": 0.18,
        "substitution": 0.12,
        "edit_distance_2": 0.08,
    }.get(mistake_type, 0.0)
    count_bonus = min(0.05 * max(count - 1, 0), 0.2)
    return round(min(0.55 + type_bonus + count_bonus, 0.99), 3)


def _weight_for(confidence: float, count: int) -> int:
    return int(100_000 + confidence * 50_000 + min(count, 50) * 1_000)
