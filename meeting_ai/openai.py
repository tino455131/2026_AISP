"""OpenAISummarizer: summarize a meeting with the OpenAI API."""

from __future__ import annotations

import json
import os
from typing import Mapping, Sequence

from .interface import MeetingLine, MeetingSummary, SummaryError

DEFAULT_MODEL = "gpt-6-luna"

SYSTEM_PROMPT = """你是小型專案團隊的會議記錄助理。使用者會給你一場會議的逐字稿（台灣繁體中文，可能中英夾雜），
每一行的格式是「[行號] 說話者代號（名字）：內容」。

請整理：
1. summary：3～5 句話的重點摘要。
2. decisions：會議中明確做出的決定。
3. action_items：明確被提出、有人要做的事；owner 填說話者代號（如 S1）或會議中提到的人名，期限照原話填。

規則：
- 只根據逐字稿，不要補充逐字稿沒有的內容；負責人或期限不清楚就留空字串，不要猜。
- 每個決定與待辦都要附上 source_line_ids（依據的行號）。
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


class OpenAISummarizer:
    prompt_version = "openai-1"

    def __init__(self, client=None, model: str | None = None) -> None:
        self._client = client  # tests inject a fake; production creates it on first use
        self.name = model or os.environ.get("MEETING_SUMMARY_MODEL") or DEFAULT_MODEL

    def _get_client(self):
        if self._client is None:
            if not os.environ.get("OPENAI_API_KEY", "").strip():
                raise SummaryError("尚未設定 OPENAI_API_KEY")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise SummaryError("沒有安裝 openai 套件：請在 voice_stt 的 Python 環境安裝 requirements.txt") from exc
            self._client = OpenAI()
        return self._client

    def summarize(self, lines: Sequence[MeetingLine], speakers: Mapping[str, str]) -> MeetingSummary:
        if not lines:
            return MeetingSummary(summary="這場錄音沒有任何發言。")

        response = self._get_client().responses.create(
            model=self.name,
            max_output_tokens=16000,
            store=False,
            instructions=SYSTEM_PROMPT,
            input=f"<transcript>\n{format_transcript(lines, speakers)}\n</transcript>\n\n請整理這場會議。",
            text={"format": {"type": "json_schema", "name": "meeting_summary", "schema": SCHEMA, "strict": True}},
        )
        if response.status == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            if reason == "max_output_tokens":
                raise SummaryError("回覆太長被截斷")
            raise SummaryError("模型沒有完成摘要")
        if response.status != "completed":
            raise SummaryError("模型沒有完成摘要")
        for item in response.output:
            if item.type == "message":
                if any(block.type == "refusal" for block in item.content):
                    raise SummaryError("模型拒絕整理這份逐字稿")

        text = response.output_text
        if not text or not text.strip():
            raise SummaryError("模型沒有回傳文字")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SummaryError("模型回傳的摘要不是有效 JSON") from exc
        if not isinstance(data, dict):
            raise SummaryError("模型回傳的摘要格式不正確")
        return MeetingSummary.from_dict(data, valid_ids={line.line_id for line in lines})
