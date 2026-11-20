"""OpenAISummarizer is tested with a fake client: nothing is sent to OpenAI."""

import json
from types import SimpleNamespace

import pytest

from meeting_ai import MeetingLine, SummaryError, get_summarizer
from meeting_ai.llm import SCHEMA, SYSTEM_PROMPT
from meeting_ai.openai_summarizer import OpenAISummarizer

LINES = [
    MeetingLine(1, "S1", "2026-11-21T06:00:01+00:00", "我們決定下週一 merge"),
    MeetingLine(2, "S2", "2026-11-21T06:00:05+00:00", "我週五前把測試寫完"),
]
REPLY = {
    "summary": "討論 merge 時間與測試分工。",
    "decisions": [{"text": "下週一 merge", "source_line_ids": [1]}],
    "action_items": [{"task": "寫測試", "owner": "S2（小明）", "due": "週五前", "source_line_ids": [2, 77]}],
}


class FakeOpenAI:
    """Stands in for openai.OpenAI(): chat.completions.create returns a fixed reply."""

    def __init__(self, content, finish_reason="stop", refusal=None):
        self.calls = []
        message = SimpleNamespace(content=content, refusal=refusal)
        self._response = SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def test_sends_shared_prompt_and_strict_schema():
    fake = FakeOpenAI(json.dumps(REPLY, ensure_ascii=False))
    summary = OpenAISummarizer(client=fake).summarize(LINES, {"S2": "小明"})

    call = fake.calls[0]
    assert call["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert "[2] S2（小明）：我週五前把測試寫完" in call["messages"][1]["content"]
    assert call["response_format"]["json_schema"]["schema"] == SCHEMA
    assert call["response_format"]["json_schema"]["strict"] is True
    assert summary.action_items[0].owner == "S2"  # same clean-up as every other source
    assert summary.action_items[0].source_line_ids == (2,)


@pytest.mark.parametrize("fake", [FakeOpenAI(None, refusal="不行"), FakeOpenAI("{", finish_reason="length")])
def test_refusal_and_cut_off_become_summary_errors(fake):
    with pytest.raises(SummaryError):
        OpenAISummarizer(client=fake).summarize(LINES, {})


def test_missing_key_is_a_clear_error(monkeypatch):
    pytest.importorskip("openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SummaryError, match="OPENAI_API_KEY"):
        OpenAISummarizer().summarize(LINES, {})


def test_picked_by_name():
    assert isinstance(get_summarizer("openai"), OpenAISummarizer)
