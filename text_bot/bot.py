"""Discord bot with slash commands and guild text message logging."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from dotenv import load_dotenv

from channel_access import AuthorizedMessageReader, ChannelAccess
from sqlite_api import PROJECT_ROOT, SQLiteStore, resolve_database_path
from transcript_reader import AuthorizedTranscriptReader


class BotClient(discord.Client):
    def __init__(self, guild_id: int, store: SQLiteStore) -> None:
        intents = discord.Intents.default()
        intents.guild_messages = True
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.guild_id = guild_id
        self.store = store
        self.channel_access = ChannelAccess(self, guild_id)
        self.message_reader = AuthorizedMessageReader(self.channel_access, store)
        # Voice transcripts (F6) live in the same database file as messages.
        self.transcript_reader = AuthorizedTranscriptReader(self.channel_access, store)
        self._backfill_started = False
        self._backfill_task: asyncio.Task[None] | None = None

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        commands = await self.tree.sync(guild=guild)
        logging.info("Synced %d command(s) to guild %d", len(commands), self.guild_id)

    async def on_ready(self) -> None:
        logging.info("Logged in as %s; logging guild %d", self.user, self.guild_id)
        if not self._backfill_started:
            self._backfill_started = True
            self._backfill_task = asyncio.create_task(self.backfill_history())

    async def backfill_history(self) -> None:
        """Import accessible text channel and thread history on startup."""
        guild = self.get_guild(self.guild_id)
        if guild is None:
            logging.error("Guild %d is unavailable; history import skipped", self.guild_id)
            return

        try:
            channels = await guild.fetch_channels()
        except discord.HTTPException:
            logging.exception("Could not list channels for guild %d", self.guild_id)
            return

        message_channels = [
            channel for channel in channels
            if isinstance(channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel))
        ]
        threads = {thread.id: thread for thread in guild.threads}
        for channel in channels:
            if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                continue
            try:
                async for thread in channel.archived_threads(limit=None):
                    threads[thread.id] = thread
            except discord.HTTPException:
                logging.warning("Could not list archived threads in channel %d", channel.id)
            if isinstance(channel, discord.TextChannel):
                for joined in (False, True):
                    try:
                        async for thread in channel.archived_threads(
                            private=True, joined=joined, limit=None
                        ):
                            threads[thread.id] = thread
                    except discord.HTTPException:
                        logging.warning(
                            "Could not list private archived threads in channel %d", channel.id
                        )

        for channel in [*message_channels, *threads.values()]:
            try:
                await self._backfill_channel(channel)
            except discord.HTTPException:
                logging.warning("Could not read history in channel/thread %d", channel.id)
            except Exception:
                logging.exception("History import failed in channel/thread %d", channel.id)
        logging.info("History import pass finished for guild %d", self.guild_id)

    async def _backfill_channel(
        self,
        channel: discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.Thread,
    ) -> None:
        last_id = await asyncio.to_thread(
            self.store.get_last_backfilled_message_id, self.guild_id, channel.id
        )
        after = discord.Object(id=last_id) if last_id else None
        count = 0
        async for message in channel.history(limit=None, after=after, oldest_first=True):
            await asyncio.to_thread(
                self.store.save_historical_message,
                message.id,
                self.guild_id,
                channel.id,
                message.author.id,
                message.content,
                message.created_at.isoformat(),
                message.edited_at.isoformat() if message.edited_at else None,
            )
            count += 1
            if count % 500 == 0:
                logging.info("Imported %d historical event(s) from channel/thread %d so far", count, channel.id)
        logging.info("Imported %d historical event(s) from channel/thread %d", count, channel.id)

    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.guild.id != self.guild_id or not message.content:
            return
        await asyncio.to_thread(
            self.store.save_message,
            message.id,
            message.guild.id,
            message.channel.id,
            message.author.id,
            message.content,
            message.created_at.isoformat(),
        )

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.guild_id != self.guild_id:
            return
        content = payload.data.get("content")
        if not isinstance(content, str):
            return  # Other edits, such as embed updates, contain no new text.
        edited_at = payload.data.get("edited_timestamp") or datetime.now(timezone.utc).isoformat()
        updated = await asyncio.to_thread(
            self.store.update_message, payload.message_id, self.guild_id, content, edited_at
        )
        if not updated and (content or payload.data.get("edited_timestamp")):
            try:
                message = payload.message
                if message is None:
                    channel = self.get_channel(payload.channel_id)
                    if channel is None:
                        channel = await self.fetch_channel(payload.channel_id)
                    message = await channel.fetch_message(payload.message_id)
                if message.guild is None or message.guild.id != self.guild_id:
                    return
                await asyncio.to_thread(
                    self.store.save_message,
                    payload.message_id,
                    self.guild_id,
                    payload.channel_id,
                    message.author.id,
                    content,
                    message.created_at.isoformat(),
                    edited_at=edited_at,
                )
            except discord.HTTPException:
                logging.warning("Could not fetch edited message %d", payload.message_id)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id == self.guild_id:
            await asyncio.to_thread(self.store.delete_message, payload.message_id, self.guild_id)

    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent) -> None:
        if payload.guild_id == self.guild_id:
            await asyncio.to_thread(self.store.delete_messages, payload.message_ids, self.guild_id)

    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if channel.guild.id == self.guild_id:
            await asyncio.to_thread(self.store.delete_channel, self.guild_id, channel.id)

    async def on_raw_thread_delete(self, payload: discord.RawThreadDeleteEvent) -> None:
        if payload.guild_id == self.guild_id:
            await asyncio.to_thread(self.store.delete_channel, self.guild_id, payload.thread_id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        if guild.id == self.guild_id:
            await asyncio.to_thread(self.store.delete_guild, self.guild_id)
            logging.warning("Removed from guild %d; deleted its local message log", self.guild_id)


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", interpolate=False)
    token = os.getenv("TEXT_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing TEXT_BOT_TOKEN. Fill in the project root .env.")

    guild_id_text = os.getenv("DISCORD_GUILD_ID", "").strip()
    if not guild_id_text.isdecimal() or int(guild_id_text) == 0:
        raise SystemExit("DISCORD_GUILD_ID must be a positive server ID in .env.")
    guild_id = int(guild_id_text)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    store = SQLiteStore(resolve_database_path(os.getenv("BOT_DB")))
    client = BotClient(guild_id, store)

    @client.tree.command(name="ping", description="Check whether the bot is online")
    async def ping(interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Pong! 🏓")

    client.run(token)


if __name__ == "__main__":
    main()
