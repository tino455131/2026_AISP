"""Checks that Discord event handlers keep message logs in the configured guild."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bot import BotClient
from message_store import MessageStore


class BotEventTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp_dir.cleanup)
        self.store = MessageStore(Path(self.temp_dir.name) / "messages.sqlite3")
        self.client = BotClient(10, self.store)

    async def test_live_messages_are_scoped_and_follow_edits_and_deletes(self) -> None:
        now = datetime(2026, 10, 28, tzinfo=timezone.utc)
        def message(message_id: int, guild_id: int | None, channel_id: int):
            return SimpleNamespace(
                id=message_id,
                guild=SimpleNamespace(id=guild_id) if guild_id is not None else None,
                channel=SimpleNamespace(id=channel_id),
                author=SimpleNamespace(id=7),
                content="hello",
                created_at=now,
            )

        await self.client.on_message(message(1, 10, 100))
        await self.client.on_message(message(2, 10, 200))
        await self.client.on_message(message(3, 11, 100))
        await self.client.on_message(message(4, None, 100))
        self.assertEqual(len(self.store.recent_messages(10, 100)), 1)
        self.assertEqual(len(self.store.recent_messages(10, 200)), 1)

        await self.client.on_raw_message_edit(
            SimpleNamespace(guild_id=10, message_id=1, data={"content": "updated"})
        )
        self.assertEqual(self.store.recent_messages(10, 100)[0]["content"], "updated")
        await self.client.on_raw_message_edit(
            SimpleNamespace(
                guild_id=10, message_id=5, channel_id=100,
                data={"content": "added after an attachment"}, message=message(5, 10, 100),
            )
        )
        self.assertEqual(self.store.recent_messages(10, 100)[0]["content"], "added after an attachment")
        await self.client.on_raw_message_delete(SimpleNamespace(guild_id=10, message_id=1))
        self.assertEqual([row["message_id"] for row in self.store.recent_messages(10, 100)], [5])

    async def test_history_resumes_after_saved_message(self) -> None:
        now = datetime(2026, 10, 28, tzinfo=timezone.utc)
        messages = [
            SimpleNamespace(id=5, author=SimpleNamespace(id=7), content="old", created_at=now, edited_at=None),
            SimpleNamespace(id=6, author=SimpleNamespace(id=8), content="new", created_at=now, edited_at=None),
        ]

        class FakeChannel:
            id = 100
            after_ids: list[int | None] = []

            async def history(self, *, limit, after, oldest_first):
                self.after_ids.append(after.id if after else None)
                for item in messages:
                    if after is None or item.id > after.id:
                        yield item

        channel = FakeChannel()
        await self.client._backfill_channel(channel)
        await self.client._backfill_channel(channel)
        self.assertEqual(channel.after_ids, [None, 6])
        self.assertEqual([row["message_id"] for row in self.store.recent_messages(10, 100)], [6, 5])


if __name__ == "__main__":
    unittest.main()
