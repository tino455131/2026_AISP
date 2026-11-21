"""Resolve current Discord channel visibility before reading saved messages."""

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import discord

from sqlite_api import SQLiteStore


class AccessUnavailable(RuntimeError):
    """Discord could not confirm current access; no messages may be returned."""


class AccessDenied(PermissionError):
    """The requesting member cannot read the channel's message history."""


@dataclass(frozen=True)
class VisibleMember:
    id: int
    display_name: str


@dataclass(frozen=True)
class ChannelVisibility:
    guild_id: int
    channel_id: int
    name: str
    kind: str
    parent_channel_id: int | None
    members: tuple[VisibleMember, ...]
    checked_at: datetime


MessageChannel = discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread


class ChannelAccess:
    """Compute access from current Discord state; never cache a viewer list."""

    def __init__(self, client: discord.Client, guild_id: int) -> None:
        self.client = client
        self.guild_id = guild_id

    async def visible_members(self, channel_id: int) -> ChannelVisibility:
        """List human members who can currently view this channel or thread."""
        guild, channel, permission_channel = await self._resolve_channel(channel_id)
        private_members = await self._private_thread_members(channel)
        visible: list[VisibleMember] = []
        try:
            async for member in guild.fetch_members(limit=None):
                if not member.bot and self._can_view(
                    permission_channel, member, private_members
                ):
                    visible.append(VisibleMember(member.id, member.display_name))
        except (discord.HTTPException, discord.ClientException) as exc:
            raise AccessUnavailable("Could not retrieve the complete guild member list") from exc

        return ChannelVisibility(
            guild_id=self.guild_id,
            channel_id=channel.id,
            name=channel.name,
            kind=channel.type.name,
            parent_channel_id=channel.parent_id if isinstance(channel, discord.Thread) else None,
            members=tuple(sorted(visible, key=lambda item: item.id)),
            checked_at=datetime.now(timezone.utc),
        )

    async def can_read_history(self, member_id: int, channel_id: int) -> bool:
        """Check one person's current right to read stored channel history."""
        guild, channel, permission_channel = await self._resolve_channel(channel_id)
        try:
            member = await guild.fetch_member(member_id)
        except discord.NotFound:
            return False
        except (discord.HTTPException, discord.ClientException) as exc:
            raise AccessUnavailable("Could not confirm guild membership") from exc

        if member.bot:
            return False
        private_members = await self._private_thread_members(channel)
        try:
            permissions = permission_channel.permissions_for(member)
        except discord.ClientException as exc:
            raise AccessUnavailable("Could not resolve member channel permissions") from exc
        return (
            permissions.view_channel
            and permissions.read_message_history
            and (private_members is None or permissions.manage_threads or member.id in private_members)
        )

    async def _resolve_channel(
        self, channel_id: int
    ) -> tuple[discord.Guild, MessageChannel, discord.abc.GuildChannel]:
        guild = self.client.get_guild(self.guild_id)
        if guild is None:
            raise AccessUnavailable("Configured guild is unavailable")
        try:
            channel = await self.client.fetch_channel(channel_id)
        except (discord.HTTPException, discord.ClientException) as exc:
            raise AccessUnavailable("Could not confirm current channel access") from exc

        if not isinstance(
            channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.Thread)
        ) or channel.guild.id != self.guild_id:
            raise AccessUnavailable("Channel is outside the configured guild or cannot hold messages")

        if isinstance(channel, discord.Thread):
            try:
                parent = await self.client.fetch_channel(channel.parent_id)
            except (discord.HTTPException, discord.ClientException) as exc:
                raise AccessUnavailable("Could not confirm thread parent permissions") from exc
            if not isinstance(parent, (discord.TextChannel, discord.ForumChannel)) or parent.guild.id != self.guild_id:
                raise AccessUnavailable("Thread parent is unavailable")
            return guild, channel, parent
        return guild, channel, channel

    async def _private_thread_members(self, channel: MessageChannel) -> set[int] | None:
        if not isinstance(channel, discord.Thread) or not channel.is_private():
            return None
        try:
            return {member.id for member in await channel.fetch_members()}
        except (discord.HTTPException, discord.ClientException) as exc:
            raise AccessUnavailable("Could not confirm private thread membership") from exc

    @staticmethod
    def _can_view(
        channel: discord.abc.GuildChannel,
        member: discord.Member,
        private_members: set[int] | None,
    ) -> bool:
        try:
            permissions = channel.permissions_for(member)
        except discord.ClientException as exc:
            raise AccessUnavailable("Could not resolve member channel permissions") from exc
        return permissions.view_channel and (
            private_members is None or permissions.manage_threads or member.id in private_members
        )


class AuthorizedMessageReader:
    """The only entry point future AI features should use for saved message text."""

    def __init__(self, access: ChannelAccess, store: SQLiteStore) -> None:
        self.access = access
        self.store = store

    async def recent_messages_for(
        self, member_id: int, channel_id: int, limit: int = 100
    ) -> list[sqlite3.Row]:
        if not await self.access.can_read_history(member_id, channel_id):
            raise AccessDenied("Member cannot read this channel's message history")
        return await asyncio.to_thread(self.store.list_recent_messages, self.access.guild_id, channel_id, limit)
