"""OpenAISummarizer：用 OpenAI（ChatGPT）API 整理會議。預設沒有開啟。

開啟方式（換到別台電腦時）：
1. 在執行 meeting_ai 的 Python 環境安裝套件：voice_stt/.venv/Scripts/pip install openai
2. 在 voice_bot/.env 填 OPENAI_API_KEY=...（這是密碼，只能放 .env）
3. 改成 MEETING_SUMMARIZER=openai，或啟動時加 --summarizer openai
模型用 MEETING_SUMMARY_OPENAI_MODEL 換（預設 gpt-4.1-mini，名稱以 OpenAI 官網為準）。

提示詞、輸出格式和解析都在 llm.py，跟 Claude 共用；這裡只負責呼叫 API。
用的是 Chat Completions 的 structured outputs（response_format 指定 JSON schema），
llm.py 的 SCHEMA 每一層都有 required 和 additionalProperties: false，符合 strict 模式的要求。
"""

from __future__ import annotations

import os

from .interface import SummaryError
from .llm import LLMSummarizer

MODEL = os.environ.get("MEETING_SUMMARY_OPENAI_MODEL", "gpt-4.1-mini")


class OpenAISummarizer(LLMSummarizer):
    name = f"openai:{MODEL}"

    def __init__(self, client=None) -> None:
        self._client = client  # tests pass a fake; otherwise created on first use

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise SummaryError("沒有安裝 openai 套件：在 voice_stt/.venv 執行 pip install openai") from exc
            if not os.environ.get("OPENAI_API_KEY", "").strip():
                raise SummaryError("沒有 OPENAI_API_KEY：請填在 voice_bot/.env")
            self._client = openai.OpenAI()
        return self._client

    def generate(self, system_prompt: str, transcript: str, schema: dict) -> str:
        response = self._get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": True},
            },
        )
        choice = response.choices[0]
        if getattr(choice.message, "refusal", None):
            raise SummaryError(f"模型拒絕處理：{choice.message.refusal}")
        if choice.finish_reason == "length":
            raise SummaryError("回覆太長被截斷")
        if not choice.message.content:
            raise SummaryError("模型沒有回傳文字")
        return choice.message.content
