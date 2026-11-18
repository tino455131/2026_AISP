import json
from types import SimpleNamespace

import pytest

from meeting_ai import MeetingLine, MeetingSummary, SummaryError, get_summarizer, render_markdown
from meeting_ai.claude import ClaudeSummarizer, format_transcript
from meeting_ai.simple import SimpleSummarizer
from meeting_ai.summarize_session import load_transcript_store, summarize_session

LINES = [
    MeetingLine(1, "S1", "2026-11-18T06:00:01+00:00", "大家好我們先看這週的進度"),
    MeetingLine(2, "S2", "2026-11-18T06:00:05+00:00", "我週五之前會把測試報告上傳到 Notion"),
    MeetingLine(3, "S1", "2026-11-18T06:00:09+00:00", "好那我們決定下週一 merge"),
    MeetingLine(4, "S2", "2026-11-18T06:00:12+00:00", "我來處理 token 的設定", uncertain=True),
    MeetingLine(5, "S1", "2026-11-18T06:00:15+00:00", "語音的部分做完了嗎？"),
]


def test_simple_summarizer_finds_tasks_and_decisions():
    summary = SimpleSummarizer().summarize(LINES, {"S1": "組長"})
    assert "組長（3 句）" in summary.summary
    assert [d.source_line_ids for d in summary.decisions] == [(3,)]
    # line 4 is uncertain and line 5 is a question: neither becomes a task
    assert [(a.owner, a.due, a.source_line_ids) for a in summary.action_items] == [("S2", "週五之前", (2,))]


def test_summary_json_round_trip_drops_invented_sources():
    data = {
        "summary": "討論進度",
        "decisions": [{"text": "下週一 merge", "source_line_ids": [3, 99]}],
        "action_items": [{"task": "上傳報告", "owner": "S2", "due": "週五", "source_line_ids": [2]}],
    }
    summary = MeetingSummary.from_dict(data, valid_ids={1, 2, 3})
    assert summary.decisions[0].source_line_ids == (3,)
    assert MeetingSummary.from_dict(json.loads(summary.to_json())) == summary


def test_render_markdown_uses_mentions_for_owners():
    summary = MeetingSummary("討論進度", action_items=(SimpleSummarizer().summarize(LINES, {}).action_items))
    text = render_markdown(summary, {"S2": "<@222>"})
    assert "- <@222>：我週五之前會把測試報告上傳到 Notion（週五之前）" in text


def test_get_summarizer_picks_by_name(monkeypatch):
    monkeypatch.delenv("MEETING_SUMMARIZER", raising=False)
    assert isinstance(get_summarizer(), SimpleSummarizer)
    assert isinstance(get_summarizer("claude"), ClaudeSummarizer)
    with pytest.raises(ValueError):
        get_summarizer("gpt")


class FakeClaude:
    """Stands in for anthropic.Anthropic(): returns a fixed structured reply, no network."""

    def __init__(self, reply, stop_reason="end_turn"):
        self.reply, self.stop_reason, self.calls = reply, stop_reason, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=json.dumps(self.reply))]
        )


def test_claude_summarizer_sends_transcript_and_parses_json():
    fake = FakeClaude(
        {
            "summary": "確認測試報告與 merge 時間",
            "decisions": [{"text": "下週一 merge", "source_line_ids": [3]}],
            "action_items": [{"task": "上傳測試報告", "owner": "S2", "due": "週五前", "source_line_ids": [2, 42]}],
        }
    )
    summary = ClaudeSummarizer(client=fake).summarize(LINES, {"S1": "組長"})

    call = fake.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "[1] S1（組長）：大家好" in call["messages"][0]["content"]
    assert "[4] S2：我來處理 token 的設定（可能聽錯）" in call["messages"][0]["content"]
    assert summary.action_items[0].source_line_ids == (2,)  # 42 is not a real line


def test_claude_refusal_raises():
    with pytest.raises(SummaryError):
        ClaudeSummarizer(client=FakeClaude({}, stop_reason="refusal")).summarize(LINES, {})


def test_format_transcript_without_names():
    assert format_transcript(LINES[:1], {}) == "[1] S1：大家好我們先看這週的進度"


def test_summarize_session_saves_summary_with_mentions(tmp_path):
    module = load_transcript_store()
    store = module.TranscriptStore(tmp_path / "messages.sqlite3")
    store.start_session("rec-1", 10, 301, "2026-11-18T06:00:00+00:00")
    store.add_lines(
        "rec-1",
        [
            module.NewLine(111, "2026-11-18T06:00:01+00:00", "2026-11-18T06:00:03+00:00", "先看進度", "先看進度", 0.9),
            module.NewLine(222, "2026-11-18T06:00:05+00:00", "2026-11-18T06:00:07+00:00",
                           "我明天會把報告上傳", "我明天會把報告上傳", 0.9),
        ],
    )

    result = summarize_session(store, "rec-1", SimpleSummarizer(), names={"111": "組長"})

    assert result["action_items"] == 1
    assert "<@222>：我明天會把報告上傳（明天）" in result["markdown"]
    saved = store.summary("rec-1")
    assert saved.model == "keyword-rules" and saved.source_line_count == 2
    assert json.loads(saved.content)["action_items"][0]["owner"] == "S2"
