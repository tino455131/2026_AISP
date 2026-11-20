"""LLMSummarizer：所有「把逐字稿交給語言模型整理」的摘要器共用的部分。

提示詞、輸出格式（JSON schema）、逐字稿怎麼排、回覆怎麼解析和檢查，都在這裡。
每個來源（Claude API、Claude Code、其他模型）只要寫一個子類別，實作一個方法：

    from meeting_ai.llm import LLMSummarizer

    class MySummarizer(LLMSummarizer):
        name = "my-model"  # 會跟摘要一起存進資料庫

        def generate(self, system_prompt: str, transcript: str, schema: dict) -> str | dict:
            # 把 system_prompt 當系統指示、transcript 當使用者訊息送給模型，
            # 要求它回傳符合 schema 的 JSON。回傳 JSON 字串或 dict 都可以。
            ...

然後設定 MEETING_SUMMARIZER=模組路徑:類別名稱（例如 my_summarizers.openai_one:MySummarizer），
不用改 meeting_ai 裡任何檔案。換來源時，摘要的格式、檢查和顯示都不會變。
"""

from __future__ import annotations

import json
from typing import Mapping, Sequence

from .interface import MeetingLine, MeetingSummary, SummaryError

# Bump when SYSTEM_PROMPT or SCHEMA changes, so old summaries can be told apart and redone.
# (The name started with the Claude summarizer; it is the shared prompt for every source.)
PROMPT_VERSION = "claude-2"

SYSTEM_PROMPT = """你是小型專案團隊的會議記錄助理。使用者會給你一場會議的逐字稿（台灣繁體中文，可能中英夾雜），
每一行的格式是「[行號] 說話者代號（名字）：內容」。

請整理：
1. summary：3～5 句話的重點摘要。
2. decisions：會議中明確做出的決定。
3. action_items：明確被提出、有人要做的事；owner 填說話者代號（如 S1）或會議中提到的人名，期限照原話填。

規則：
- 只根據逐字稿，不要補充逐字稿沒有的內容；負責人或期限不清楚就留空字串，不要猜。
- 每個決定與待辦都要附上 source_line_ids（依據的行號）。行號只放在 source_line_ids，summary 和各項文字裡不要寫行號。
- 文字裡提到人時用名字（括號裡的那個），沒有名字才用 S1 這種代號；owner 欄位則照上面填代號。
- 標記「可能聽錯」的行不要當成確定的事實；若它是唯一依據，就不要列成決定或待辦。
- 這是給團隊看的事實性紀錄：不要評價任何人的表現。
- 全部用台灣繁體中文。"""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_line_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["text", "source_line_ids"],
                "additionalProperties": False,
            },
        },
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due": {"type": "string"},
                    "source_line_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["task", "owner", "due", "source_line_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "decisions", "action_items"],
    "additionalProperties": False,
}


def format_transcript(lines: Sequence[MeetingLine], speakers: Mapping[str, str]) -> str:
    rows = []
    for line in lines:
        name = speakers.get(line.speaker)
        who = f"{line.speaker}（{name}）" if name else line.speaker
        mark = "（可能聽錯）" if line.uncertain else ""
        rows.append(f"[{line.line_id}] {who}：{line.text}{mark}")
    return "\n".join(rows)


def transcript_message(lines: Sequence[MeetingLine], speakers: Mapping[str, str]) -> str:
    """The user message every source receives."""
    return f"<transcript>\n{format_transcript(lines, speakers)}\n</transcript>\n\n請整理這場會議。"


def parse_reply(reply: str | dict) -> dict:
    """A model's answer as a dict: accepts a dict, a JSON string, or JSON inside a ``` fence."""
    if isinstance(reply, dict):
        return reply
    text = str(reply or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SummaryError("模型沒有照格式回傳摘要（不是 JSON）") from exc
    if not isinstance(data, dict):
        raise SummaryError("模型沒有照格式回傳摘要（不是 JSON 物件）")
    return data


def label_only(data: dict, labels: set[str]) -> dict:
    """Models sometimes write an owner as "S2（皓元）"; keep just "S2" so it becomes a mention."""
    for item in data.get("action_items", []):
        owner = str(item.get("owner", "")).strip()
        for label in labels:
            if owner.startswith(label) and owner[len(label):len(label) + 1] in ("（", "("):
                item["owner"] = label
    return data


class LLMSummarizer:
    """Base class: subclasses only send the prompt to a model in generate()."""

    name = "llm"
    prompt_version = PROMPT_VERSION

    def generate(self, system_prompt: str, transcript: str, schema: dict) -> str | dict:
        """Ask the model; return its JSON answer (string or dict). Raise SummaryError on failure."""
        raise NotImplementedError

    def summarize(self, lines: Sequence[MeetingLine], speakers: Mapping[str, str]) -> MeetingSummary:
        if not lines:
            return MeetingSummary(summary="這場錄音沒有任何發言。")
        reply = self.generate(SYSTEM_PROMPT, transcript_message(lines, speakers), SCHEMA)
        data = label_only(parse_reply(reply), {line.speaker for line in lines})
        # Source ids the model invented (not real lines of this meeting) are dropped here.
        return MeetingSummary.from_dict(data, valid_ids={line.line_id for line in lines})
