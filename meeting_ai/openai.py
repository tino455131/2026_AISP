"""OpenAISummarizer: summarize a meeting with the OpenAI API (Responses API).

The prompt, output schema and reply parsing live in llm.py and are shared with claude-code,
so every summarizer follows the same rules; this file only sends the request.
Model: MEETING_SUMMARY_MODEL (default gpt-6-luna). Needs OPENAI_API_KEY in the root .env.
"""

from __future__ import annotations

import os

from .interface import SummaryError
from .llm import LLMSummarizer, format_transcript  # noqa: F401 (format_transcript re-exported)

DEFAULT_MODEL = "gpt-6-luna"


class OpenAISummarizer(LLMSummarizer):
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

    def generate(self, system_prompt: str, transcript: str, schema: dict) -> str:
        """One structured reply as JSON text (also used by ai_demo); raises SummaryError on failure."""
        response = self._get_client().responses.create(
            model=self.name,
            max_output_tokens=16000,
            store=False,
            instructions=system_prompt,
            input=transcript,
            text={"format": {"type": "json_schema", "name": "result", "schema": schema, "strict": True}},
        )
        if response.status == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            if reason == "max_output_tokens":
                raise SummaryError("回覆太長被截斷")
            raise SummaryError("模型沒有完成回覆")
        if response.status != "completed":
            raise SummaryError("模型沒有完成回覆")
        for item in response.output:
            if item.type == "message" and any(block.type == "refusal" for block in item.content):
                raise SummaryError("模型拒絕處理這份內容")

        text = response.output_text
        if not text or not text.strip():
            raise SummaryError("模型沒有回傳文字")
        return text
