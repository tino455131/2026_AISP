"""ai_demo with a temporary database and a fake AI: nothing is sent anywhere."""

import json
import sqlite3

import pytest

from ai_demo import cli
from ai_demo.ask import ask
from ai_demo.local_data import LocalData
from ai_demo.tasks import propose_tasks
from sqlite_api import NewLine, SQLiteStore

LEADER, MEMBER, OTHER = 111, 222, 333


class FakeAI:
    """Answers the tasks prompt or the ask prompt with a fixed reply."""

    def __init__(self, tasks=None, answer=None):
        self.tasks, self.answer, self.calls = tasks or {"items": []}, answer, []

    def generate(self, system_prompt, user_text, schema):
        self.calls.append((system_prompt, user_text))
        return self.tasks if "items" in schema["properties"] else self.answer


def item(**overrides):
    base = {
        "title": "完成第一份小考", "description": "", "owner_label": "S2", "collaborator_labels": [],
        "assigned_by_label": "S1", "explicit_assignment": True, "due_text": "下週五前",
        "due_at": "2026-11-27T23:59:00+08:00", "question": "", "source_line_ids": [1],
    }
    return {**base, **overrides}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "messages.sqlite3"
    store = SQLiteStore(path)
    store.create_voice_session("rec-1", 9, 10, "2026-11-20T06:00:00+00:00", started_by=LEADER)
    line = lambda who, at, text, conf=0.9: NewLine(who, at, at, text, text, conf)  # noqa: E731
    store.add_transcript_lines("rec-1", [
        line(LEADER, "2026-11-20T06:00:01+00:00", "C 負責第一份小考，下週五前完成"),
        line(MEMBER, "2026-11-20T06:00:05+00:00", "好，我來"),
        line(MEMBER, "2026-11-20T06:00:09+00:00", "要不要讓 D 先準備期中考", 0.2),
    ])
    recordings = tmp_path / "recordings" / "rec-1"
    recordings.mkdir(parents=True)
    (recordings / "manifest.json").write_text(json.dumps({"names": {str(LEADER): "A", str(MEMBER): "C"}}), encoding="utf-8")
    store.save_text_meeting({
        "meeting_id": "mtg-10-1", "guild_id": 9, "channel_id": 10, "started_by": LEADER,
        "started_at": "2026-11-21T06:00:00+00:00", "ended_at": "2026-11-21T06:30:00+00:00",
        "start_message_id": 1, "end_message_id": 99, "message_count": 2,
        "summary": {"summary": "確認分工", "decisions": [{"text": "下週一 merge", "source_line_ids": [1]}],
                    "action_items": [{"task": "寫測試", "owner": "S2", "due": "週五前", "source_line_ids": [2]}]},
        "source_message_ids": {1: "5", 2: "6"}, "speakers": {"S1": str(LEADER), "S2": str(MEMBER)},
        "model": "fake", "prompt_version": "t", "created_at": "2026-11-21T06:31:00+00:00",
    })
    return LocalData(path, tmp_path / "recordings")


def test_lists_and_reads_both_kinds_of_meetings(db):
    assert [m["meeting_id"] for m in db.meetings()] == ["mtg-10-1", "rec-1"]  # newest first
    voice = db.meeting("rec-1")
    assert [(line.line_id, line.speaker_label) for line in voice.lines] == [(1, "S1"), (2, "S2"), (3, "S2")]
    assert voice.names == {"S1": "A", "S2": "C"} and voice.lines[2].uncertain
    assert voice.lines[0].source_ref["kind"] == "voice_line"
    text = db.meeting("mtg-10-1")  # no messages table: works from the summary's items
    assert text.lines[0].speaker_label == "摘要" and "寫測試" in text.lines[2].text
    with pytest.raises(LookupError):
        db.meeting("rec-nope")


def test_only_the_leaders_clear_assignment_with_owner_and_deadline_becomes_a_task(db):
    record = db.meeting("rec-1")
    fake = FakeAI(tasks={"items": [
        item(),                                                           # A assigns C, with a deadline
        item(title="準備期中考", owner_label="S9", source_line_ids=[3]),  # unknown person, unsure line
        item(title="寫測試", assigned_by_label="S2", source_line_ids=[2]),  # a member, model says explicit anyway
        item(title="沒有期限的事", due_at=""),
        item(title="編出來的", source_line_ids=[42]),                      # no such line
    ]})
    result = propose_tasks(record, LEADER, fake)

    assert "組長（TeamLeader）的代號是 S1" in fake.calls[0][0]
    [task] = result["tasks"]
    assert task["owner_user_id"] == MEMBER and task["status"] == "not_started"
    assert task["due_at"] == "2026-11-27T15:59:00Z"  # stored as UTC
    assert task["source_refs"][0]["kind"] == "voice_line"
    missing = {p["payload"]["title"]: p["missing"] for p in result["proposals"]}
    assert missing["準備期中考"] == ["explicit_assignment", "owner_user_id", "reliable_evidence"]
    assert missing["寫測試"] == ["explicit_assignment"]
    assert missing["沒有期限的事"] == ["due_at"]
    assert all(p["state"] == "needs_clarification" for p in result["proposals"])
    assert result["rejected"] == 1


def test_without_a_leader_nothing_is_a_formal_task(db):
    result = propose_tasks(db.meeting("rec-1"), None, FakeAI(tasks={"items": [item()]}))
    assert result["tasks"] == [] and result["proposals"][0]["missing"] == ["explicit_assignment"]


def test_answers_need_real_sources(db):
    record = db.meeting("rec-1")
    good = ask(record, "誰負責小考？", FakeAI(answer={"found": True, "answer": "C", "source_line_ids": [1, 2]}))
    assert good["ok"] and good["source_line_ids"] == [1, 2]
    for reply in ({"found": False, "answer": "", "source_line_ids": []},
                  {"found": True, "answer": "D", "source_line_ids": [77]}):
        assert ask(record, "誰負責期末考？", FakeAI(answer=reply))["error_code"] == "NOT_FOUND"


def test_command_line_list_and_missing_meeting(db, capsys):
    assert cli.main(["--db", str(db.db), "list"]) == 0
    assert "rec-1" in capsys.readouterr().out
    assert cli.main(["--db", str(db.db), "show", "rec-nope"]) == 1
    assert "NOT_FOUND" in capsys.readouterr().out


def test_bot_mode_prints_one_result_line_with_ids_as_strings(db, capsys, monkeypatch):
    def run(*args):
        assert cli.main(["--bot", "--db", str(db.db), *args]) == 0
        out = capsys.readouterr().out.strip().splitlines()
        assert len(out) == 1 and out[0].startswith("RESULT ")
        return json.loads(out[0][len("RESULT "):])

    assert {m["meeting_id"] for m in run("list")["meetings"]} == {"rec-1", "mtg-10-1"}
    assert run("show", "rec-nope")["error_code"] == "NOT_FOUND"
    fake = FakeAI(answer={"found": True, "answer": "C", "source_line_ids": [1]})
    monkeypatch.setattr(cli, "get_engine", lambda name: fake)
    answer = run("ask", "rec-1", "誰負責小考？")
    assert answer["ok"] and answer["meeting"]["channel_id"] == 10
    assert cli._safe_ids({"user": 702000000000000000, "n": 5, "flag": True}) == {
        "user": "702000000000000000", "n": 5, "flag": True,
    }


def test_database_is_opened_read_only(db):
    with pytest.raises(sqlite3.OperationalError):
        with db._connect() as connection:
            connection.execute("DELETE FROM voice_lines")
