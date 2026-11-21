"""SimpleSummarizer：不用任何 API 的「假 AI」，只靠關鍵字，讓整條流程可以先測試。

它不懂語意，結果很粗糙；正式的摘要由 AI 組的實作（或 OpenAISummarizer）取代。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Mapping, Sequence

from .interface import ActionItem, Decision, MeetingLine, MeetingSummary

TASK_WORDS = re.compile(r"負責|要把|會把|我來|我會|補上|完成|處理|上傳|交給|做完|之前|deadline|due", re.I)
DECISION_WORDS = re.compile(r"決定|就這樣|確定|定案|就用|採用|同意")
DUE_WORDS = re.compile(
    r"(下?(週|周|禮拜|星期)[一二三四五六日天]|今天|明天|後天|今晚|下週|下周|月底|\d{1,2}/\d{1,2}|\d{1,2}月\d{1,2}[日號])"
    r"(之前|前|以前)?"
)


class SimpleSummarizer:
    name = "keyword-rules"
    prompt_version = "rules-1"

    def summarize(self, lines: Sequence[MeetingLine], speakers: Mapping[str, str]) -> MeetingSummary:
        if not lines:
            return MeetingSummary(summary="這場錄音沒有任何發言。")

        counts = Counter(line.speaker for line in lines)
        who = "、".join(f"{speakers.get(s, s)}（{n} 句）" for s, n in counts.most_common())
        opening = "；".join(line.text for line in lines[:3])
        summary = f"共 {len(lines)} 句，發言：{who}。開頭談到：{opening}。（關鍵字版本，僅供測試）"

        decisions, actions = [], []
        for line in lines:
            if line.uncertain:
                continue  # may be misheard: never turn it into a decision or a task
            if DECISION_WORDS.search(line.text):
                decisions.append(Decision(line.text, (line.line_id,)))
            elif TASK_WORDS.search(line.text) and not line.text.rstrip().endswith(("？", "?", "嗎")):
                due = DUE_WORDS.search(line.text)
                actions.append(ActionItem(line.text, line.speaker, due.group(0) if due else "", (line.line_id,)))
        return MeetingSummary(summary, tuple(decisions), tuple(actions))
