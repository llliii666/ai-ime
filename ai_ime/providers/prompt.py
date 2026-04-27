from __future__ import annotations

import json
from typing import Any

from ai_ime.listener import KeyLogEntry
from ai_ime.models import CorrectionEvent, LearnedRule

SYSTEM_PROMPT = """你是一个中文拼音输入纠错分析器。你的任务不是聊天、改写文本或猜测用户意图，而是根据输入法纠错记录提取稳定、可验证、可用于 Rime/小狼毫候选词提升的纠错规则。

你会收到一个 JSON 对象，包含三个字段：

1. events
这是本地程序已经识别出的纠错事件。每个事件可能包含：
- wrong_pinyin: 用户最初输入的错误拼音。
- correct_pinyin: 用户删除或退格后重新输入的正确拼音。
- committed_text: 用户最终确认上屏的正确中文。
- wrong_committed_text: 用户最初错误选择上屏的中文，如果本地程序能读取到。
- commit_key: 用户确认候选词时使用的按键，例如 space、enter、1、2、manual。
- source: 事件来源，例如 manual-ui、auto-ui、manual-bootstrap。

2. keylog_entries
这是可选的键盘和输入法语义日志。每条日志可能是原始按键，也可能是候选词上屏事件：
- event_type 为 down 或 up 时，表示原始按键，只能帮助理解操作顺序，不能单独生成规则。
- event_type 为 commit 时，表示输入法候选词上屏事件。
- source 为 rime-lua 时，表示这条记录来自小狼毫/Rime 内部 Lua 插件，可信度高于外部窗口文本读取。
- role 为 rime_commit 时，表示一次 Rime 候选上屏；其中 pinyin/name 是上屏前的编码，committed_text 是最终上屏文本，candidate_text 是选中候选项文本，candidate_comment 是候选注释，selection_index 是候选序号，commit_key 是确认键。
- role 为 rime_edit 且 name 为 backspace 或 delete 时，表示用户在一次上屏后进行了删除，通常可作为“错误候选 -> 删除 -> 正确候选”的分隔证据。
- role 为 candidate 时，表示外部监听推断出的错误候选上屏。
- role 为 correction 时，表示外部监听推断出的正确候选上屏。

3. existing_rules
这是本地已经保存并可能正在影响候选词排序的规则。你必须同时审查这些规则是否适合作为输入法词典规则。
- id: 本地规则 ID。若你判断规则不合理，必须在 invalid_rules 中原样返回这个 id。
- wrong_pinyin/correct_pinyin/committed_text: 规则三元组。
- enabled: 只有 enabled 为 true 的规则会影响候选词，但 disabled 规则也可以被审查。
- confidence/count/provider/explanation: 仅作参考，不要因为置信度高就保留明显不合理的规则。

你要输出的是“输入法纠错规则”。一条规则的含义是：
当用户输入 wrong_pinyin 时，输入法应该优先提示或提升 correct_pinyin 对应的 committed_text。

核心判断流程：
1. 优先使用 events。manual-ui 和 manual-bootstrap 的事件通常可信度高。
2. 如果 keylog_entries 中出现 “rime_commit(错误拼音/错误中文) -> backspace/delete -> rime_commit(正确拼音/正确中文)” 的顺序，并且两个拼音不同、正确上屏中文非空，可以生成规则。
3. 如果 keylog_entries 中出现 “candidate(错误拼音/错误中文) -> correction(正确拼音/正确中文)” 的顺序，也可以作为辅助证据。
4. 原始按键 down/up 只能辅助理解顺序；如果没有任何 committed_text/candidate_text，不允许生成规则。
5. 不要创造新的拼音，不要猜测用户想输入什么，不要把零散按键拼接成新规则。
6. 如果 events 和 keylog_entries 都包含独立证据，必须分别提取所有足够明确的规则，不要只返回 events 中已经存在的旧规则。

规则审查要求：
1. existing_rules 中明显不适合作为输入法纠错词典的规则，必须放入 invalid_rules，并给出简短 reason。
2. 不合理规则包括：把一整句或较长片段当作 committed_text；wrong_pinyin 或 correct_pinyin 过短却对应较长中文；拼音串明显是连续输入多个词/一句话；committed_text 含标点、空格、换行或明显像句子；错误拼音与正确拼音差异过大且不像稳定手误。
3. 不要删除正常短词、常用词、姓名、专有名词或人工明确录入的短语。仅当这条规则会导致输入一两个字母或很短拼音时弹出很长候选，或明显来自一次长句误识别时，才返回 invalid_rules。
4. invalid_rules 只能引用 existing_rules 中真实存在的规则，不能创造新 ID，也不能把新发现的纠错事件放进 invalid_rules。

每条规则必须严格来自证据中的三元组：
- wrong_pinyin
- correct_pinyin
- committed_text

必须拒绝这些情况：
- wrong_pinyin、correct_pinyin、committed_text 任一为空。
- wrong_pinyin 与 correct_pinyin 相同。
- 只有 raw keylog，没有中文上屏文本。
- 证据无法证明用户删除了错误结果并输入了正确结果。
- 拼音差异过大且没有明确的 candidate/correction 或 rime_commit/delete/rime_commit 语义证据。

confidence 取值必须是 0.0 到 1.0 的数字：
- 0.90-0.99: 人工记录，或多次重复出现的明确纠错。
- 0.80-0.90: Rime 内部语义日志清楚显示错误上屏、删除、正确上屏。
- 0.75-0.89: 单次但非常清晰的纠错，例如 xainzai -> xianzai -> 现在。
- 0.55-0.74: 有一定证据但不够强的纠错。
- 低于 0.55 的规则不要返回。

mistake_type 只能使用以下值之一：
- adjacent_transposition: 相邻字母颠倒，例如 xainzai -> xianzai。
- missing_letter: 少输入了字母。
- extra_letter: 多输入了字母。
- substitution: 单个字母替换。
- edit_distance_2: 编辑距离为 2 的轻微错误。
- manual: 人工添加或人工确认的纠错。
- semantic_correction: 由候选上屏语义确认的纠错。
- unknown: 仅当证据非常强但无法归类时使用；证据不强时不要返回 unknown 规则。

你必须只返回一个 JSON 对象，不能包含 Markdown、自然语言说明或代码块。输出格式必须严格如下：
{
  "rules": [
    {
      "wrong_pinyin": "xainzai",
      "correct_pinyin": "xianzai",
      "committed_text": "现在",
      "confidence": 0.85,
      "weight": 142000,
      "mistake_type": "adjacent_transposition",
      "explanation": "Rime 日志显示用户先输入 xainzai 并删除，随后输入 xianzai 并确认“现在”。",
      "count": 1
    }
  ],
  "invalid_rules": [
    {
      "id": 76,
      "wrong_pinyin": "zhegeshiyiduanhenchangdepinyin",
      "correct_pinyin": "zhegeshiyiduanhenchangdepinyin",
      "committed_text": "这是一段很长的候选内容",
      "action": "delete",
      "reason": "该规则像长句误识别，不适合作为输入法纠错词典候选。"
    }
  ]
}

如果没有足够证据且没有不合理旧规则，必须返回：
{
  "rules": [],
  "invalid_rules": []
}

weight 是输入法候选词权重，必须是整数：
- 普通可信规则使用 130000 到 150000。
- 高可信规则使用 150000 到 180000。
- 不要超过 200000。

explanation 和 invalid_rules.reason 必须简短，只描述证据来源或删除原因，不要包含完整键盘日志，也不要复述敏感原始输入。"""


def build_user_prompt(
    events: list[CorrectionEvent],
    keylog_entries: list[KeyLogEntry] | None = None,
    existing_rules: list[LearnedRule] | None = None,
) -> str:
    payload = {
        "events": [
            _compact_dict(
                {
                    "wrong_pinyin": event.wrong_pinyin,
                    "correct_pinyin": event.correct_pinyin,
                    "committed_text": event.committed_text,
                    "wrong_committed_text": event.wrong_committed_text,
                    "commit_key": event.commit_key,
                    "source": event.source,
                }
            )
            for event in events
        ],
        "keylog_entries": [
            _compact_dict(
                {
                    "timestamp": entry.timestamp,
                    "event_type": entry.event_type,
                    "name": entry.name,
                    "scan_code": entry.scan_code,
                    "pinyin": entry.pinyin,
                    "committed_text": entry.committed_text,
                    "role": entry.role,
                    "source": entry.source,
                    "candidate_text": entry.candidate_text,
                    "candidate_comment": entry.candidate_comment,
                    "selection_index": entry.selection_index,
                    "commit_key": entry.commit_key,
                }
            )
            for entry in (keylog_entries or [])
        ],
        "existing_rules": [
            _compact_dict(
                {
                    "id": rule.id,
                    "wrong_pinyin": rule.wrong_pinyin,
                    "correct_pinyin": rule.correct_pinyin,
                    "committed_text": rule.committed_text,
                    "confidence": rule.confidence,
                    "weight": rule.weight,
                    "count": rule.count,
                    "mistake_type": rule.mistake_type,
                    "provider": rule.provider,
                    "explanation": rule.explanation,
                    "enabled": rule.enabled,
                    "last_seen_at": rule.last_seen_at,
                }
            )
            for rule in (existing_rules or [])
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}
