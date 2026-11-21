"""Voice transcripts stay scoped by session/channel and leave no trace when deleted."""

import sqlite3
import tempfile
from contextlib import closing
import unittest
from pathlib import Path

from sqlite_api import NewLine, SessionNotFound, SQLiteStore


def line(speaker_id, second, text, flags=()):
    return NewLine(
        speaker_id=speaker_id,
        started_at=f"2026-11-18T06:00:{second:02d}+00:00",
        ended_at=f"2026-11-18T06:00:{second + 2:02d}+00:00",
        text=text,
        text_raw=text,
        confidence=0.9,
        flags=flags,
    )


class SQLiteStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "messages.sqlite3"
        self.store = SQLiteStore(self.path)
        self.store.create_voice_session("s1", 10, 301, "2026-11-18T06:00:00+00:00", started_by=1)
        self.store.add_transcript_lines("s1", [line(2, 9, "API 我做完了"), line(1, 1, "先看這週進度", ("low_confidence",))])

    def test_lines_come_back_in_time_order_with_flags(self) -> None:
        lines = self.store.list_transcript_lines("s1")
        self.assertEqual([item.text for item in lines], ["先看這週進度", "API 我做完了"])
        self.assertEqual(lines[0].flags, ("low_confidence",))
        self.assertEqual(lines[1].flags, ())

    def test_sessions_are_listed_per_channel_newest_first(self) -> None:
        self.store.create_voice_session("s2", 10, 301, "2026-11-19T06:00:00+00:00")
        self.store.create_voice_session("other", 10, 302, "2026-11-19T07:00:00+00:00")
        self.assertEqual([s.session_id for s in self.store.list_recent_voice_sessions(10, 301)], ["s2", "s1"])

    def test_duplicate_session_id_is_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_voice_session("s1", 10, 301, "2026-11-18T06:00:00+00:00")

    def test_unknown_session_raises(self) -> None:
        with self.assertRaises(SessionNotFound):
            self.store.add_transcript_lines("missing", [line(1, 1, "x")])
        with self.assertRaises(SessionNotFound):
            self.store.get_voice_session("missing")

    def test_summary_remembers_how_many_lines_it_saw(self) -> None:
        self.store.save_session_summary("s1", "進度：API 完成", "test-model", "v1", "2026-11-18T07:00:00+00:00")
        self.assertEqual(self.store.get_session_summary("s1").source_line_count, 2)
        self.store.add_transcript_lines("s1", [line(3, 20, "我明天補測試")])
        self.assertEqual(self.store.count_transcript_lines("s1"), 3)  # the reader marks it stale

    def test_withdrawing_one_speaker_removes_their_lines_and_the_summary(self) -> None:
        self.store.save_session_summary("s1", "提到 API", "test-model", "v1", "2026-11-18T07:00:00+00:00")
        self.store.delete_speaker_transcript("s1", 2)
        self.assertEqual([item.speaker_id for item in self.store.list_transcript_lines("s1")], [1])
        self.assertIsNone(self.store.get_session_summary("s1"))

    def test_deleting_channel_or_guild_removes_everything_of_it(self) -> None:
        self.store.create_voice_session("keep", 10, 302, "2026-11-18T08:00:00+00:00")
        self.store.add_transcript_lines("keep", [line(1, 1, "另一個頻道")])
        self.store.save_session_summary("s1", "摘要", "test-model", "v1", "2026-11-18T07:00:00+00:00")

        self.store.delete_channel(10, 301)
        self.assertEqual(self.store.list_recent_voice_sessions(10, 301), [])
        self.assertEqual(self.store.list_transcript_lines("s1"), [])
        self.assertIsNone(self.store.get_session_summary("s1"))
        self.assertEqual(len(self.store.list_transcript_lines("keep")), 1)

        self.store.delete_guild(10)
        self.assertEqual(self.store.list_transcript_lines("keep"), [])

    def test_shares_the_message_database_in_wal_mode(self) -> None:
        messages = SQLiteStore(self.path)
        messages.save_message(1, 10, 101, 7, "text message", "2026-11-18T06:00:00+00:00")
        self.assertEqual(len(messages.list_recent_messages(10, 101)), 1)
        self.assertEqual(len(self.store.list_transcript_lines("s1")), 2)
        with closing(sqlite3.connect(self.path)) as connection:  # closing() so Windows can delete it
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")


if __name__ == "__main__":
    unittest.main()
