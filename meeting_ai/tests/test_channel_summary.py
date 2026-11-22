from meeting_ai.interface import MeetingSummary
from meeting_ai.summarize_channel import summarize_channel
from sqlite_api import SQLiteStore


class SummaryRecorder:
    def __init__(self):
        self.texts = []

    def summarize(self, lines, speakers):
        self.texts = [line.text for line in lines]
        return MeetingSummary("專題進度摘要")


def test_channel_summary_uses_recent_messages_only_from_requested_channel(tmp_path):
    store = SQLiteStore(tmp_path / "messages.sqlite3")
    timestamp = "2026-11-22T01:00:00+00:00"
    for message_id in range(1, 102):
        store.save_message(message_id, 10, 20, 30, f"發言 {message_id}", timestamp)
    store.save_message(102, 10, 21, 30, "其他頻道", timestamp)
    store.save_historical_message(103, 11, 20, 30, "其他伺服器", timestamp, None)

    summarizer = SummaryRecorder()
    result = summarize_channel(store, 10, 20, summarizer)

    assert result == {"count": 100, "summary": "專題進度摘要"}
    assert summarizer.texts == [f"發言 {message_id}" for message_id in range(2, 102)]


def test_channel_summary_does_not_invoke_summarizer_when_channel_is_empty(tmp_path):
    store = SQLiteStore(tmp_path / "messages.sqlite3")

    class UnusedSummarizer:
        def summarize(self, lines, speakers):
            raise AssertionError("no messages to summarize")

    assert summarize_channel(store, 10, 20, UnusedSummarizer()) == {"count": 0, "summary": ""}
