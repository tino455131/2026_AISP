"""【測試用】progress tracking: tasks, inquiries and progress updates follow the spec's rules."""

import io
import json
import sys

import pytest

from ai_demo import cli
from ai_demo.tracking import TrackingError, TrackingStore

OWNER, LEADER, OTHER = 222, 111, 333
CONFIRMATION = {
    "confirmation_id": "c1",
    "meeting_id": "mtg-10-1",
    "guild_id": "9",
    "channel_id": "10",
    "created_by": str(LEADER),
    "tasks": [
        {"title": "寫報告", "owner_user_id": str(OWNER), "due_at": "2026-11-25T10:00:00Z",
         "source_refs": [{"kind": "message", "message_id": "5"}]},
        {"title": "訂教室", "owner_user_id": str(OTHER), "due_at": "2026-11-26T10:00:00Z",
         "activation_state": "awaiting_leader_decision"},
    ],
}


@pytest.fixture
def store(tmp_path):
    return TrackingStore(tmp_path / "messages.sqlite3")


def test_confirming_twice_does_not_create_tasks_twice(store):
    first = store.create_tasks(CONFIRMATION)
    again = store.create_tasks(CONFIRMATION)
    assert [t["task_id"] for t in first] == [t["task_id"] for t in again] == ["task-c1-1", "task-c1-2"]
    assert first[0]["status"] == "not_started" and first[0]["activation_state"] == "active"
    assert first[1]["activation_state"] == "awaiting_leader_decision"  # owner cannot read the channel (R18)
    assert len(store.tasks(9)) == 2


def test_only_the_owner_reports_and_a_reply_closes_the_inquiry(store):
    [task, _] = store.create_tasks(CONFIRMATION)
    store.record_inquiry(task["task_id"], OWNER, "sent", "999")
    with pytest.raises(TrackingError) as denied:
        store.record_progress(task["task_id"], LEADER, "completed")  # not the leader's to report
    assert denied.value.error_code == "ROLE_REQUIRED"
    with pytest.raises(TrackingError):
        store.record_progress(task["task_id"], OWNER, "cancelled")  # only the leader may cancel

    updated = store.record_progress(task["task_id"], OWNER, "in_progress")
    assert updated["status"] == "in_progress" and updated["version"] == 2
    with store._connection() as connection:
        row = connection.execute("SELECT state, reply_received_at FROM demo_inquiries").fetchone()
    assert row["state"] == "closed" and row["reply_received_at"]  # the button press is the confirmed report


def test_completed_is_final_for_the_owner(store):
    [task, _] = store.create_tasks(CONFIRMATION)
    store.record_progress(task["task_id"], OWNER, "completed")
    with pytest.raises(TrackingError) as reopened:
        store.record_progress(task["task_id"], OWNER, "in_progress")  # reopening is the leader's
    assert reopened.value.error_code == "INVALID_ARGUMENT"


def test_a_failed_message_is_not_an_unanswered_question(store):
    [task, _] = store.create_tasks(CONFIRMATION)
    store.record_inquiry(task["task_id"], OWNER, "delivery_failed", None)
    with store._connection() as connection:
        row = connection.execute("SELECT delivery_state, state FROM demo_inquiries").fetchone()
    assert tuple(row) == ("delivery_failed", "closed")


def test_bot_mode_track_reads_the_confirmation_from_stdin(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(CONFIRMATION, ensure_ascii=False)))
    assert cli.main(["--bot", "--stdin", "--db", str(tmp_path / "db.sqlite3"), "track"]) == 0
    result = json.loads(capsys.readouterr().out.strip()[len("RESULT "):])
    assert result["ok"] and result["tasks"][0]["owner_user_id"] == OWNER

    assert cli.main(["--bot", "--db", str(tmp_path / "db.sqlite3"), "progress",
                     "--task", "task-c1-1", "--user", str(OTHER), "--status", "completed"]) == 0
    refused = json.loads(capsys.readouterr().out.strip()[len("RESULT "):])
    assert refused == {"ok": False, "error_code": "ROLE_REQUIRED", "message": "只有這項任務的負責人可以回報進度。"}
