"""Checks that Discord event handlers keep message logs in the configured guild."""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import bot
from bot import BotClient
from sqlite_api import PROJECT_ROOT, SQLiteStore


class BotEventTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp_dir.cleanup)
        self.store = SQLiteStore(Path(self.temp_dir.name) / "messages.sqlite3")
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

        with self.assertLogs(level="INFO") as logs:
            await self.client.on_message(message(1, 10, 100))
            await self.client.on_message(message(2, 10, 200))
            await self.client.on_message(message(3, 11, 100))
            await self.client.on_message(message(4, None, 100))
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            [
                "New message [channel=100, author=7]: 'hello'",
                "New message [channel=200, author=7]: 'hello'",
            ],
        )
        self.assertEqual(len(self.store.get_channel_message_list(10, 100)), 1)
        self.assertEqual(len(self.store.get_channel_message_list(10, 200)), 1)

        await self.client.on_raw_message_edit(
            SimpleNamespace(guild_id=10, message_id=1, data={"content": "updated"})
        )
        self.assertEqual(self.store.get_channel_message_list(10, 100)[0]["content"], "updated")
        await self.client.on_raw_message_edit(
            SimpleNamespace(
                guild_id=10, message_id=5, channel_id=100,
                data={"content": "added after an attachment"}, message=message(5, 10, 100),
            )
        )
        self.assertEqual(self.store.get_channel_message_list(10, 100)[-1]["content"], "added after an attachment")
        await self.client.on_raw_message_delete(SimpleNamespace(guild_id=10, message_id=1))
        self.assertEqual([row["message_id"] for row in self.store.get_channel_message_list(10, 100)], [5])

    async def test_reordering_an_uncached_edit_cannot_undo_a_newer_edit(self) -> None:
        created = datetime(2026, 10, 28, tzinfo=timezone.utc)
        message = SimpleNamespace(guild=SimpleNamespace(id=10), author=SimpleNamespace(id=7), created_at=created)
        first = SimpleNamespace(
            guild_id=10, channel_id=100, message_id=9, message=None,
            data={"content": "first edit", "edited_timestamp": "2026-10-28T00:01:00+00:00"},
        )
        latest = SimpleNamespace(
            guild_id=10, channel_id=100, message_id=9, message=message,
            data={"content": "latest edit", "edited_timestamp": "2026-10-28T00:02:00+00:00"},
        )

        async def fetch_message(message_id: int):
            self.assertEqual(message_id, 9)
            await self.client.on_raw_message_edit(latest)
            return message

        channel = SimpleNamespace(fetch_message=AsyncMock(side_effect=fetch_message))
        with patch.object(self.client, "get_channel", return_value=channel):
            await self.client.on_raw_message_edit(first)
            await self.client.on_raw_message_edit(first)
        channel.fetch_message.assert_awaited_once_with(9)
        row = self.store.get_channel_message_list(10, 100)[0]
        self.assertEqual(row["content"], "latest edit")
        self.assertEqual(row["edited_at"], latest.data["edited_timestamp"])

    async def test_main_uses_text_token_and_root_relative_database(self) -> None:
        fixture = Path(self.temp_dir.name)
        (fixture / ".env").write_text(
            "TEXT_BOT_TOKEN=file-text\nVOICE_BOT_TOKEN=file-voice\n"
            "DISCORD_GUILD_ID=1234567890\nBOT_DB=data/example.sqlite3\n",
            encoding="utf-8",
        )
        with (
            patch.object(bot, "PROJECT_ROOT", fixture),
            patch.dict(os.environ, {"TEXT_BOT_TOKEN": "env-text"}, clear=True),
            patch.object(bot, "SQLiteStore") as store,
            patch.object(bot, "BotClient") as client,
        ):
            bot.main()
        store.assert_called_once_with(PROJECT_ROOT / "data" / "example.sqlite3")
        client.assert_called_once_with(1234567890, store.return_value)
        client.return_value.run.assert_called_once_with("env-text")

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
        self.assertEqual([row["message_id"] for row in self.store.get_channel_message_list(10, 100)], [5, 6])


if __name__ == "__main__":
    unittest.main()
