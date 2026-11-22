"""Checks that stored text stays scoped and follows Discord edits/deletions."""

import tempfile
import unittest
from pathlib import Path

from sqlite_api import SQLiteStore


class SQLiteStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp_dir.cleanup)
        self.store = SQLiteStore(Path(self.temp_dir.name) / "messages.sqlite3")

    def test_channel_scope_and_message_lifecycle(self) -> None:
        self.store.save_message(1, 10, 100, 7, "first", "2026-10-28T10:00:00+00:00")
        self.store.save_message(2, 10, 200, 8, "private", "2026-10-28T10:01:00+00:00")
        self.store.save_message(3, 11, 100, 9, "other server", "2026-10-28T10:02:00+00:00")
        self.store.save_message(1, 10, 100, 7, "duplicate", "2026-10-28T10:00:00+00:00")

        rows = self.store.get_channel_message_list(10, 100)
        self.assertEqual([row["content"] for row in rows], ["first"])
        self.store.update_message(1, 10, "revised", "2026-10-28T10:03:00+00:00")
        self.assertEqual(self.store.get_channel_message_list(10, 100)[0]["content"], "revised")
        self.store.update_message(1, 10, "", "2026-10-28T10:04:00+00:00")
        self.assertEqual(self.store.get_channel_message_list(10, 100), [])
        self.store.update_message(1, 10, "restored", "2026-10-28T10:05:00+00:00")
        self.assertEqual(self.store.get_channel_message_list(10, 100)[0]["content"], "restored")

        self.store.delete_message(1, 11)  # A different guild cannot delete it.
        self.assertEqual(len(self.store.get_channel_message_list(10, 100)), 1)
        self.store.delete_message(1, 10)
        self.assertEqual(self.store.get_channel_message_list(10, 100), [])
        self.store.save_historical_message(1, 10, 100, 7, "late backfill", "2026-10-28T10:00:00+00:00", None)
        self.assertEqual(self.store.get_channel_message_list(10, 100), [])
        self.assertEqual(self.store.get_channel_message_list(10, 200)[0]["content"], "private")

    def test_bulk_channel_and_guild_deletion(self) -> None:
        for message_id, guild_id, channel_id in ((1, 10, 100), (2, 10, 100), (3, 10, 200), (4, 11, 100)):
            self.store.save_message(message_id, guild_id, channel_id, 7, "text", "2026-10-28T10:00:00+00:00")
        self.store.delete_messages({1, 2, 4}, 10)
        self.assertEqual(self.store.get_channel_message_list(10, 100), [])
        self.assertEqual(len(self.store.get_channel_message_list(11, 100)), 1)
        self.store.delete_channel(10, 200)
        self.assertEqual(self.store.get_channel_message_list(10, 200), [])
        self.store.delete_guild(11)
        self.assertEqual(self.store.get_channel_message_list(11, 100), [])

    def test_history_resume_point_and_deduplication(self) -> None:
        self.assertIsNone(self.store.get_last_backfilled_message_id(10, 100))
        self.store.save_historical_message(5, 10, 100, 7, "old", "2026-10-28T10:00:00+00:00", None)
        self.store.save_historical_message(6, 10, 100, 7, "", "2026-10-28T10:01:00+00:00", None)
        self.store.save_historical_message(5, 10, 100, 7, "old", "2026-10-28T10:00:00+00:00", None)
        self.assertEqual(self.store.get_last_backfilled_message_id(10, 100), 6)
        self.assertEqual([row["message_id"] for row in self.store.get_channel_message_list(10, 100)], [5])
        self.assertIsNone(self.store.get_last_backfilled_message_id(10, 200))
        self.store.delete_channel(10, 100)
        self.assertIsNone(self.store.get_last_backfilled_message_id(10, 100))

    def test_channel_message_list_selects_latest_then_orders_oldest_first(self) -> None:
        for message_id, created_at in (
            (1, "2026-10-28T10:00:00+00:00"),
            (2, "2026-10-28T10:02:00+00:00"),
            (3, "2026-10-28T10:01:00+00:00"),
            (4, "2026-10-28T10:03:00+00:00"),
        ):
            self.store.save_message(message_id, 10, 100, 7, str(message_id), created_at)

        rows = self.store.get_channel_message_list(10, 100, limit=2)
        self.assertEqual([row["message_id"] for row in rows], [2, 4])


if __name__ == "__main__":
    unittest.main()
