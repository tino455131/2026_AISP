"""Checks that Discord event handlers keep message logs in the configured guild."""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

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
                author=SimpleNamespace(id=7, bot=False),
                webhook_id=None,
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
                "New message [channel=100, user=7]: 'hello'",
                "New message [channel=200, user=7]: 'hello'",
            ],
        )
        self.assertEqual(len(self.store.get_channel_message_list(10, 100)), 1)
        self.assertEqual(len(self.store.get_channel_message_list(10, 200)), 1)

        await self.client.on_raw_message_edit(
            SimpleNamespace(guild_id=10, message_id=1, cached_message=message(1, 10, 100), data={"content": "updated"})
        )
        self.assertEqual(self.store.get_channel_message_list(10, 100)[0]["content"], "updated")
        await self.client.on_raw_message_edit(
            SimpleNamespace(
                guild_id=10, message_id=5, channel_id=100, cached_message=None,
                data={"content": "added after an attachment"}, message=message(5, 10, 100),
            )
        )
        self.assertEqual(self.store.get_channel_message_list(10, 100)[-1]["content"], "added after an attachment")
        await self.client.on_raw_message_delete(SimpleNamespace(guild_id=10, message_id=1))
        self.assertEqual([row["message_id"] for row in self.store.get_channel_message_list(10, 100)], [5])

    async def test_reordering_an_uncached_edit_cannot_undo_a_newer_edit(self) -> None:
        created = datetime(2026, 10, 28, tzinfo=timezone.utc)
        message = SimpleNamespace(guild=SimpleNamespace(id=10), author=SimpleNamespace(id=7, bot=False), webhook_id=None, created_at=created)
        first = SimpleNamespace(
            guild_id=10, channel_id=100, message_id=9, message=None, cached_message=None,
            data={"content": "first edit", "edited_timestamp": "2026-10-28T00:01:00+00:00"},
        )
        latest = SimpleNamespace(
            guild_id=10, channel_id=100, message_id=9, message=message, cached_message=None,
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
        self.assertEqual(channel.fetch_message.await_count, 2)
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
        client.return_value.tree.command.assert_not_called()

    async def test_username_sync_on_ready_and_scoped_user_events(self) -> None:
        guild_id = 10
        user = SimpleNamespace(id=7, name="initial", guild=SimpleNamespace(id=guild_id))

        async def fetch_members(*, limit):
            self.assertIsNone(limit)
            yield user
            yield SimpleNamespace(id=8, name="other")

        guild = SimpleNamespace(fetch_members=fetch_members, get_member=lambda uid: user if uid == user.id else None)
        with (
            patch.object(self.client, "get_guild", return_value=guild),
            patch.object(self.client, "backfill_history", new_callable=AsyncMock),
        ):
            await self.client.on_ready()
            await self.client._backfill_task
            self.assertEqual(self.store.get_user_name(7), "initial")
            self.assertEqual(self.store.get_user_name(8), "other")
            await self.client.on_user_update(user, SimpleNamespace(id=7, name="renamed"))
            await self.client.on_user_update(user, SimpleNamespace(id=99, name="unrelated"))
            await self.client.on_member_join(SimpleNamespace(id=9, name="joined", guild=user.guild))
            await self.client.on_member_join(SimpleNamespace(id=10, name="unrelated", guild=SimpleNamespace(id=2)))

        self.assertEqual(self.store.get_user_name(7), "renamed")
        self.assertEqual(self.store.get_user_name(9), "joined")
        self.assertEqual(self.store.get_user_name(99), "")
        self.assertEqual(self.store.get_user_name(10), "")

    async def test_bot_and_webhook_messages_are_skipped_but_backfill_advances(self) -> None:
        now = datetime(2026, 10, 28, tzinfo=timezone.utc)
        guild = SimpleNamespace(id=10)
        channel = SimpleNamespace(id=100)
        ignored = [
            SimpleNamespace(id=1, author=SimpleNamespace(id=20, bot=True), webhook_id=None),
            SimpleNamespace(id=2, author=SimpleNamespace(id=21, bot=False), webhook_id=99),
        ]
        for message in ignored:
            message.guild = guild
            message.channel = channel
            message.content = "bot reply"
            message.created_at = now
            message.edited_at = None
            await self.client.on_message(message)
        self.assertEqual(self.store.get_channel_message_list(10, 100), [])

        async def history(**kwargs):
            for message in ignored:
                self.assertTrue(kwargs["after"] is None or message.id > kwargs["after"].id)
                yield message

        channel.history = history
        await self.client._backfill_channel(channel)
        self.assertEqual(self.store.get_last_backfilled_message_id(10, 100), 2)
        self.assertEqual(self.store.get_channel_message_list(10, 100), [])

        # A legacy row is preserved when the corresponding bot edits its message.
        self.store.save_message(1, 10, 100, 20, "old recording", now.isoformat())
        for message in ignored:
            await self.client.on_raw_message_edit(SimpleNamespace(
                guild_id=10, channel_id=100, message_id=message.id,
                message=message, cached_message=None, data={"content": "edited bot reply"},
            ))
        channel.fetch_message = AsyncMock(return_value=ignored[1])
        with patch.object(self.client, "get_channel", return_value=channel):
            await self.client.on_raw_message_edit(SimpleNamespace(
                guild_id=10, channel_id=100, message_id=2, message=None, cached_message=None,
                data={"content": "uncached bot reply"},
            ))
            channel.fetch_message.assert_awaited_once_with(2)
            response = SimpleNamespace(status=403, reason="Forbidden")
            channel.fetch_message.side_effect = discord.Forbidden(response, "cannot verify")
            await self.client.on_raw_message_edit(SimpleNamespace(
                guild_id=10, channel_id=100, message_id=3, message=None, cached_message=None,
                data={"content": "unknown author"},
            ))
        self.assertEqual(
            [(row["message_id"], row["content"]) for row in self.store.get_channel_message_list(10, 100)],
            [(1, "old recording")],
        )

    async def test_history_resumes_after_saved_message(self) -> None:
        now = datetime(2026, 10, 28, tzinfo=timezone.utc)
        messages = [
            SimpleNamespace(id=5, author=SimpleNamespace(id=7, bot=False), webhook_id=None, content="old", created_at=now, edited_at=None),
            SimpleNamespace(id=6, author=SimpleNamespace(id=8, bot=False), webhook_id=None, content="new", created_at=now, edited_at=None),
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
