"""Current Discord permissions must gate every saved-message read."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord

from bot import BotClient
from channel_access import AccessDenied, AccessUnavailable, AuthorizedMessageReader, ChannelAccess
from message_store import MessageStore


def permissions(*, view: bool, history: bool = True, manage_threads: bool = False):
    return SimpleNamespace(
        view_channel=view,
        read_message_history=history,
        manage_threads=manage_threads,
    )


class ChannelAccessTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp_dir.cleanup)
        self.store = MessageStore(Path(self.temp_dir.name) / "messages.sqlite3")
        self.store.save_message(1001, 10, 101, 1, "team only", "2026-11-17T10:00:00+00:00")
        self.store.save_message(1002, 10, 102, 2, "leader only", "2026-11-17T10:01:00+00:00")

        self.members = {}
        for member_id, name in ((1, "Alice"), (2, "Bob"), (3, "Admin")):
            member = Mock(spec=discord.Member)
            member.id = member_id
            member.display_name = name
            member.bot = False
            self.members[member_id] = member
        bot_member = Mock(spec=discord.Member)
        bot_member.id = 4
        bot_member.display_name = "Another bot"
        bot_member.bot = True
        self.members[4] = bot_member

        self.guild = Mock(spec=discord.Guild)
        self.guild.id = 10
        self.guild.fetch_member = AsyncMock(side_effect=lambda member_id: self.members[member_id])

        async def fetch_members(*, limit):
            self.assertIsNone(limit)
            for member in self.members.values():
                yield member

        self.guild.fetch_members = fetch_members
        self.channel_permissions = {
            101: {
                1: permissions(view=True),
                2: permissions(view=False),
                3: permissions(view=True, manage_threads=True),
            },
            102: {
                1: permissions(view=False),
                2: permissions(view=True),
                3: permissions(view=True, manage_threads=True),
            },
        }
        self.channels = {}
        for channel_id, name in ((101, "team"), (102, "leader")):
            channel = Mock(spec=discord.TextChannel)
            channel.id = channel_id
            channel.name = name
            channel.type = discord.ChannelType.text
            channel.guild = self.guild
            channel.permissions_for.side_effect = (
                lambda member, channel_id=channel_id: self.channel_permissions[channel_id][member.id]
            )
            self.channels[channel_id] = channel

        self.client = Mock(spec=discord.Client)
        self.client.get_guild.return_value = self.guild
        self.client.fetch_channel = AsyncMock(side_effect=lambda channel_id: self.channels[channel_id])
        self.access = ChannelAccess(self.client, 10)
        self.reader = AuthorizedMessageReader(self.access, self.store)

    async def test_distinct_channels_and_permission_changes(self) -> None:
        team = await self.access.visible_members(101)
        leader = await self.access.visible_members(102)
        self.assertEqual((team.channel_id, team.name, team.kind), (101, "team", "text"))
        self.assertEqual([member.id for member in team.members], [1, 3])
        self.assertEqual([member.id for member in leader.members], [2, 3])
        self.assertFalse(await self.access.can_read_history(4, 101))
        self.assertEqual([row["content"] for row in await self.reader.recent_messages_for(1, 101)], ["team only"])
        with self.assertRaises(AccessDenied):
            await self.reader.recent_messages_for(1, 102)

        # A revoked role or channel overwrite takes effect on the next check.
        self.channel_permissions[101][1] = permissions(view=False)
        self.assertFalse(await self.access.can_read_history(1, 101))
        with self.assertRaises(AccessDenied):
            await self.reader.recent_messages_for(1, 101)

    async def test_history_permission_and_private_thread_membership(self) -> None:
        self.channel_permissions[101][1] = permissions(view=True, history=False)
        self.assertEqual([member.id for member in (await self.access.visible_members(101)).members], [1, 3])
        with self.assertRaises(AccessDenied):
            await self.reader.recent_messages_for(1, 101)

        thread = Mock(spec=discord.Thread)
        thread.id = 201
        thread.name = "private discussion"
        thread.type = discord.ChannelType.private_thread
        thread.guild = self.guild
        thread.parent = self.channels[101]
        thread.parent_id = 101
        thread.is_private.return_value = True
        thread.fetch_members = AsyncMock(return_value=[SimpleNamespace(id=1)])
        self.channels[201] = thread
        self.channel_permissions[101][1] = permissions(view=True)
        self.channel_permissions[101][2] = permissions(view=True)
        self.store.save_message(1003, 10, 201, 1, "private thread text", "2026-11-17T10:02:00+00:00")

        visibility = await self.access.visible_members(201)
        self.assertEqual(visibility.parent_channel_id, 101)
        self.assertEqual([member.id for member in visibility.members], [1, 3])
        self.assertEqual(len(await self.reader.recent_messages_for(1, 201)), 1)
        self.assertEqual(len(await self.reader.recent_messages_for(3, 201)), 1)
        with self.assertRaises(AccessDenied):
            await self.reader.recent_messages_for(2, 201)

        thread.fetch_members.side_effect = discord.ClientException("membership unavailable")
        with self.assertRaises(AccessUnavailable):
            await self.access.visible_members(201)
        with self.assertRaises(AccessUnavailable):
            await self.reader.recent_messages_for(1, 201)

    async def test_public_thread_uses_current_parent_permissions(self) -> None:
        thread = Mock(spec=discord.Thread)
        thread.id = 202
        thread.name = "public discussion"
        thread.type = discord.ChannelType.public_thread
        thread.guild = self.guild
        thread.parent_id = 101
        thread.is_private.return_value = False
        thread.fetch_members = AsyncMock()
        self.channels[202] = thread

        self.assertEqual([member.id for member in (await self.access.visible_members(202)).members], [1, 3])
        self.assertFalse(await self.access.can_read_history(2, 202))
        thread.fetch_members.assert_not_called()

    async def test_unavailable_permissions_return_no_partial_list_or_text(self) -> None:
        async def incomplete_members(*, limit):
            yield self.members[1]
            raise discord.ClientException("member list unavailable")

        self.guild.fetch_members = incomplete_members
        with self.assertRaises(AccessUnavailable):
            await self.access.visible_members(101)

        self.client.fetch_channel.side_effect = discord.ClientException("channel unavailable")
        with self.assertRaises(AccessUnavailable):
            await self.reader.recent_messages_for(1, 101)

    async def test_bot_enables_members_intent(self) -> None:
        client = BotClient(10, self.store)
        self.assertTrue(client.intents.members)
        self.assertTrue(client.intents.message_content)


if __name__ == "__main__":
    unittest.main()
