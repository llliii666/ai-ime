from __future__ import annotations

import json
from typing import Any

from ai_ime.correction.normalize import normalize_pinyin
from ai_ime.correction.rules import classify_mistake
from ai_ime.models import LearnedRule, ProviderAnalysis, RuleAuditFinding
from ai_ime.providers.base import ProviderError


def parse_rules_json(content: str, provider: str) -> list[LearnedRule]:
    return list(parse_analysis_json(content, provider=provider).rules)


def parse_analysis_json(content: str, provider: str) -> ProviderAnalysis:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Provider returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProviderError("Provider response must be a JSON object.")
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise ProviderError("Provider response must contain a rules array.")

    rules: list[LearnedRule] = []
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict):
            raise ProviderError(f"Rule #{index + 1} must be an object.")
        rules.append(_parse_rule(raw_rule, provider=provider, index=index))

    raw_invalid_rules = payload.get("invalid_rules", [])
    if not isinstance(raw_invalid_rules, list):
        raise ProviderError("Provider response invalid_rules must be an array.")
    invalid_rules: list[RuleAuditFinding] = []
    for index, raw_invalid_rule in enumerate(raw_invalid_rules):
        if not isinstance(raw_invalid_rule, dict):
            raise ProviderError(f"Invalid rule #{index + 1} must be an object.")
        invalid_rules.append(_parse_invalid_rule(raw_invalid_rule, index=index))
    return ProviderAnalysis(rules=rules, invalid_rules=invalid_rules)


def _parse_rule(raw_rule: dict[str, Any], provider: str, index: int) -> LearnedRule:
    wrong = normalize_pinyin(_required_str(raw_rule, "wrong_pinyin", index))
    correct = normalize_pinyin(_required_str(raw_rule, "correct_pinyin", index))
    text = _required_str(raw_rule, "committed_text", index).strip()
    if not wrong or not correct or not text:
        raise ProviderError(f"Rule #{index + 1} has empty required fields.")
    confidence = _optional_float(raw_rule, "confidence", 0.65)
    confidence = max(0.0, min(confidence, 1.0))
    count = max(1, _optional_int(raw_rule, "count", 1))
    local_weight = int(100_000 + confidence * 50_000 + min(count, 50) * 1_000)
    weight = max(_optional_int(raw_rule, "weight", local_weight), local_weight)
    mistake_type = str(raw_rule.get("mistake_type") or classify_mistake(wrong, correct))
    explanation = str(raw_rule.get("explanation") or f"AI provider {provider} recommended this rule.")
    return LearnedRule(
        wrong_pinyin=wrong,
        correct_pinyin=correct,
        committed_text=text,
        confidence=confidence,
        weight=weight,
        count=count,
        mistake_type=mistake_type,
        provider=provider,
        explanation=explanation,
    )


def _parse_invalid_rule(raw_rule: dict[str, Any], index: int) -> RuleAuditFinding:
    rule_id = _optional_rule_id(raw_rule)
    wrong = normalize_pinyin(_required_str(raw_rule, "wrong_pinyin", index))
    correct = normalize_pinyin(_required_str(raw_rule, "correct_pinyin", index))
    text = _required_str(raw_rule, "committed_text", index).strip()
    if not wrong or not correct or not text:
        raise ProviderError(f"Invalid rule #{index + 1} has empty required fields.")
    action = str(raw_rule.get("action") or "delete").strip().lower()
    if action not in {"delete", "disable"}:
        raise ProviderError(f"Invalid rule #{index + 1} action must be delete or disable.")
    reason = str(raw_rule.get("reason") or raw_rule.get("explanation") or "AI suggested removing this rule.").strip()
    return RuleAuditFinding(
        rule_id=rule_id,
        wrong_pinyin=wrong,
        correct_pinyin=correct,
        committed_text=text,
        action=action,
        reason=reason,
    )


def _required_str(raw_rule: dict[str, Any], key: str, index: int) -> str:
    value = raw_rule.get(key)
    if not isinstance(value, str):
        raise ProviderError(f"Rule #{index + 1} field {key} must be a string.")
    return value


def _optional_float(raw_rule: dict[str, Any], key: str, default: float) -> float:
    value = raw_rule.get(key, default)
    if isinstance(value, int | float):
        return float(value)
    raise ProviderError(f"Field {key} must be a number.")


def _optional_int(raw_rule: dict[str, Any], key: str, default: int) -> int:
    value = raw_rule.get(key, default)
    if isinstance(value, bool):
        raise ProviderError(f"Field {key} must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ProviderError(f"Field {key} must be an integer.")


def _optional_rule_id(raw_rule: dict[str, Any]) -> int | None:
    value = raw_rule.get("id", raw_rule.get("rule_id"))
    if value is None:
        return None
    if isinstance(value, bool):
        raise ProviderError("Invalid rule id must be an integer.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ProviderError("Invalid rule id must be an integer.")
