"""Integration tests for the shared text and voice SQLite interface."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from sqlite_api import DEFAULT_DB, PROJECT_ROOT, NewLine, SQLiteStore, resolve_database_path


CREATED = "2026-11-18T06:00:00+00:00"


def line(text: str) -> NewLine:
    return NewLine(7, CREATED, CREATED, text, text, 0.9)


def meeting(meeting_id: str, guild_id: int, channel_id: int) -> dict:
    return {
        "meeting_id": meeting_id, "guild_id": guild_id, "channel_id": channel_id, "started_by": 7,
        "started_at": CREATED, "ended_at": CREATED, "start_message_id": 1, "end_message_id": 9,
        "message_count": 2, "summary": {"summary": "確認分工", "decisions": [], "action_items": []},
        "source_message_ids": {1: "5", 2: "6"}, "speakers": {"S1": "7"},
        "model": "test", "prompt_version": "v1", "created_at": CREATED,
    }


class SQLiteAPITests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "messages.sqlite3"

    def test_shared_database_path_resolves_relative_to_project(self) -> None:
        self.assertEqual(resolve_database_path(), PROJECT_ROOT / "data" / "messages.sqlite3")
        self.assertEqual(resolve_database_path("  "), DEFAULT_DB)
        self.assertEqual(resolve_database_path("archive/shared.sqlite3"), PROJECT_ROOT / "archive/shared.sqlite3")
        self.assertEqual(resolve_database_path(str(self.path)), self.path)

    def test_one_store_round_trips_text_transcript_and_summary(self) -> None:
        store = SQLiteStore(self.path)
        store.save_message(1, 10, 101, 7, "進度已完成", CREATED)
        store.create_voice_session("s1", 10, 301, CREATED)
        store.add_transcript_lines("s1", [line("會議中確認進度")])
        store.save_session_summary("s1", "進度摘要", "test", "v1", CREATED)

        reopened = SQLiteStore(self.path)
        self.assertEqual(reopened.list_recent_messages(10, 101)[0]["content"], "進度已完成")
        self.assertEqual(reopened.list_transcript_lines("s1")[0].text, "會議中確認進度")
        self.assertEqual(reopened.get_session_summary("s1").content, "進度摘要")
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_text_meeting_round_trip_and_replace(self) -> None:
        store = SQLiteStore(self.path)
        store.save_text_meeting(meeting("mtg-101-1", 10, 101))
        saved = SQLiteStore(self.path).get_text_meeting("mtg-101-1")
        self.assertEqual(saved["summary"]["summary"], "確認分工")
        self.assertEqual(saved["source_message_ids"], {1: "5", 2: "6"})  # keys back to int
        self.assertEqual(saved["speakers"], {"S1": "7"})
        store.save_text_meeting({**meeting("mtg-101-1", 10, 101), "message_count": 3})  # ended again: replaced
        self.assertEqual(store.get_text_meeting("mtg-101-1")["message_count"], 3)
        self.assertIsNone(store.get_text_meeting("mtg-nope"))
        with self.assertRaises(KeyError):
            store.save_text_meeting({"meeting_id": "mtg-incomplete"})

    def test_existing_text_and_voice_rows_survive_initialization(self) -> None:
        # A file created with the old table layout should open without data migration.
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE messages (message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL, author_id INTEGER NOT NULL, content TEXT NOT NULL,
                    created_at TEXT NOT NULL, edited_at TEXT);
                CREATE TABLE voice_sessions (session_id TEXT PRIMARY KEY, guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL, started_at TEXT NOT NULL, ended_at TEXT,
                    started_by INTEGER);
                CREATE TABLE voice_lines (line_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,
                    speaker_id INTEGER NOT NULL, started_at TEXT NOT NULL, ended_at TEXT NOT NULL,
                    text TEXT NOT NULL, text_raw TEXT NOT NULL, confidence REAL NOT NULL,
                    flags TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE voice_session_summaries (session_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
                    source_line_count INTEGER NOT NULL, created_at TEXT NOT NULL);
                """
            )
            connection.execute("INSERT INTO messages VALUES (1, 10, 101, 7, '舊訊息', ?, NULL)", (CREATED,))
            connection.execute("INSERT INTO voice_sessions VALUES ('old', 10, 301, ?, NULL, 7)", (CREATED,))
            connection.execute(
                "INSERT INTO voice_lines (session_id, guild_id, channel_id, speaker_id, started_at, "
                "ended_at, text, text_raw, confidence, flags) VALUES ('old', 10, 301, 7, ?, ?, "
                "'舊逐字稿', '舊逐字稿', 0.9, '[]')",
                (CREATED, CREATED),
            )
            connection.execute(
                "INSERT INTO voice_session_summaries VALUES ('old', '舊摘要', 'test', 'v1', 1, ?)",
                (CREATED,),
            )

        store = SQLiteStore(self.path)
        self.assertEqual(store.list_recent_messages(10, 101)[0]["content"], "舊訊息")
        self.assertEqual(store.list_transcript_lines("old")[0].text, "舊逐字稿")
        self.assertEqual(store.get_session_summary("old").content, "舊摘要")

    def test_channel_and_guild_delete_both_kinds_without_touching_others(self) -> None:
        store = SQLiteStore(self.path)
        for message_id, guild_id, channel_id, session_id in (
            (1, 10, 301, "target"),
            (2, 10, 302, "same-guild"),
            (3, 11, 301, "other-guild"),
        ):
            store.save_historical_message(message_id, guild_id, channel_id, 7, session_id, CREATED, None)
            store.create_voice_session(session_id, guild_id, channel_id, CREATED)
            store.add_transcript_lines(session_id, [line(session_id)])
            store.save_session_summary(session_id, session_id, "test", "v1", CREATED)
            store.save_text_meeting(meeting(f"mtg-{session_id}", guild_id, channel_id))

        store.delete_channel(10, 301)
        self.assertIsNone(store.get_text_meeting("mtg-target"))  # a summary of that channel goes with it
        self.assertIsNotNone(store.get_text_meeting("mtg-same-guild"))
        self.assertEqual(store.list_recent_messages(10, 301), [])
        self.assertIsNone(store.get_last_backfilled_message_id(10, 301))
        self.assertEqual(store.list_transcript_lines("target"), [])
        self.assertIsNone(store.get_session_summary("target"))
        self.assertEqual(len(store.list_recent_messages(10, 302)), 1)
        self.assertEqual(len(store.list_transcript_lines("same-guild")), 1)
        self.assertEqual(len(store.list_recent_messages(11, 301)), 1)

        store.delete_guild(10)
        self.assertEqual(store.list_recent_messages(10, 302), [])
        self.assertEqual(store.list_transcript_lines("same-guild"), [])
        self.assertIsNone(store.get_session_summary("same-guild"))
        self.assertIsNone(store.get_text_meeting("mtg-same-guild"))
        self.assertIsNotNone(store.get_text_meeting("mtg-other-guild"))
        self.assertEqual(len(store.list_recent_messages(11, 301)), 1)
        self.assertEqual(len(store.list_transcript_lines("other-guild")), 1)


if __name__ == "__main__":
    unittest.main()
