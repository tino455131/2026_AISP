"""Text meetings (/meeting): messages -> lines -> summary -> stored record, with a fake summarizer."""

import io
import json
import sys

from meeting_ai import MeetingSummary
from meeting_ai.interface import ActionItem, Decision
from meeting_ai import summarize_text_meeting as module
from meeting_ai.summarize_text_meeting import build_text_lines, summarize_text_meeting
from sqlite_api import SQLiteStore

MEETING = {
    "guild_id": "111111111111111111",
    "channel_id": "222222222222222222",
    "started_by": "333333333333333333",
    "started_at": "2026-11-21T06:00:00+00:00",
    "ended_at": "2026-11-21T06:30:00+00:00",
    "start_message_id": "900000000000000001",
    "end_message_id": "900000000000000099",
    "messages": [
        {"message_id": "900000000000000010", "author_id": "333333333333333333", "name": "組長A",
         "created_at": "2026-11-21T06:01:00+00:00", "text": "C 負責第一份小考，\n下週五前完成"},
        {"message_id": "900000000000000020", "author_id": "444444444444444444", "name": "C",
         "created_at": "2026-11-21T06:02:00+00:00", "text": "好，我來"},
        {"message_id": "900000000000000030", "author_id": "333333333333333333", "name": "組長A",
         "created_at": "2026-11-21T06:03:00+00:00", "text": "那就這樣決定"},
    ],
}


class FakeSummarizer:
    name = "fake"
    prompt_version = "test"

    def __init__(self):
        self.seen = None

    def summarize(self, lines, speakers):
        self.seen = (lines, speakers)
        return MeetingSummary(
            "確認小考分工",
            decisions=(Decision("C 負責第一份小考", (1, 2)),),
            action_items=(ActionItem("完成第一份小考", "S2", "下週五前", (1,)),),
        )


def test_messages_become_numbered_lines_with_author_labels():
    lines, names, author_of, source = build_text_lines(MEETING["messages"])
    assert [(line.line_id, line.speaker) for line in lines] == [(1, "S1"), (2, "S2"), (3, "S1")]
    assert lines[0].text == "C 負責第一份小考， 下週五前完成"  # one message stays one line
    assert names == {"S1": "組長A", "S2": "C"}
    assert author_of["S2"] == "444444444444444444"
    assert source[2] == "900000000000000020"


def test_someone_only_mentioned_still_gets_a_label():
    messages = [
        {"message_id": "1", "author_id": "333", "name": "組長A", "created_at": "2026-11-21T06:01:00+00:00",
         "text": "<@555> 負責寫報告，11/25 前完成", "mentions": [{"id": "555", "name": "E"}]},
        {"message_id": "2", "author_id": "555", "name": "E", "created_at": "2026-11-21T06:02:00+00:00", "text": "好"},
    ]
    lines, names, user_of, _ = build_text_lines(messages)
    assert lines[0].text == "@E（S2） 負責寫報告，11/25 前完成"
    assert lines[1].speaker == "S2"  # the same person keeps the same label when they speak
    assert names == {"S1": "組長A", "S2": "E"} and user_of["S2"] == "555"


def test_summary_is_saved_with_sources_and_owners_become_mentions(tmp_path):
    store = SQLiteStore(tmp_path / "messages.sqlite3")
    fake = FakeSummarizer()
    result = summarize_text_meeting(store, MEETING, fake)

    assert fake.seen[1] == {"S1": "組長A", "S2": "C"}
    assert "- <@444444444444444444>：完成第一份小考（下週五前）" in result["markdown"]
    saved = store.get_text_meeting(result["meeting_id"])
    assert saved["message_count"] == 3 and saved["model"] == "fake"
    assert saved["summary"]["decisions"][0]["source_line_ids"] == [1, 2]
    assert saved["source_message_ids"][1] == "900000000000000010"  # line 1 -> its Discord message
    assert saved["channel_id"] == 222222222222222222
    assert saved["speakers"] == {"S1": "333333333333333333", "S2": "444444444444444444"}


def test_command_line_reads_stdin_and_prints_result(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(MEETING, ensure_ascii=False)))
    monkeypatch.setattr(module, "get_summarizer", lambda name: FakeSummarizer())
    assert module.main(["--db", str(tmp_path / "db.sqlite3")]) == 0
    result = json.loads(capsys.readouterr().out.splitlines()[-1][len("RESULT "):])
    assert result["decisions"] == 1 and result["meeting_id"].startswith("mtg-222222222222222222-")
