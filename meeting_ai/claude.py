"""ClaudeSummarizer：用 Claude API 整理會議（選用，需要 ANTHROPIC_API_KEY 或 `ant auth login`）。

換成這個：MEETING_SUMMARIZER=claude，並在 voice_bot/.env 填 ANTHROPIC_API_KEY（照用量計費）。
模型預設 claude-opus-5-5，可用 MEETING_SUMMARY_MODEL 換。
安裝：pip install anthropic（在執行 meeting_ai 的那個 Python 環境；voice_stt/.venv 已經有）

提示詞、輸出格式和解析都在 llm.py，跟其他來源共用；這裡只負責呼叫 API。
"""

from __future__ import annotations

import os

from .interface import SummaryError
from .llm import SCHEMA, SYSTEM_PROMPT, LLMSummarizer, format_transcript  # noqa: F401 (re-exported)

MODEL = os.environ.get("MEETING_SUMMARY_MODEL", "claude-opus-5-5")


class ClaudeSummarizer(LLMSummarizer):
    name = MODEL

    def __init__(self, client=None) -> None:
        self._client = client  # tests pass a fake; otherwise created on first use

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise SummaryError("沒有安裝 anthropic 套件：pip install anthropic") from exc
            self._client = anthropic.Anthropic()
        return self._client

    def generate(self, system_prompt: str, transcript: str, schema: dict) -> str:
        response = self._get_client().beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            # If the model declines, the API retries on a fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system_prompt,
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": transcript}],
        )
        if response.stop_reason == "refusal":
            raise SummaryError("模型拒絕整理這份逐字稿")
        if response.stop_reason == "max_tokens":
            raise SummaryError("回覆太長被截斷")
        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            raise SummaryError("模型沒有回傳文字")
        return text
