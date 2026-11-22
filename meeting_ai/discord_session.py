"""Short-lived Discord client for authorized reads from Python workers."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import discord


class DiscordNotReady(RuntimeError):
    """Discord did not provide current guild state in time."""


@asynccontextmanager
async def ready_discord_client(token: str) -> AsyncIterator[discord.Client]:
    """Sign in, wait for guild state, and close the client on every exit."""
    intents = discord.Intents.none()
    intents.guilds = True
    async with discord.Client(intents=intents) as client:
        await client.login(token)
        connection = asyncio.create_task(client.connect(reconnect=False))
        ready = asyncio.create_task(client.wait_until_ready())
        try:
            await asyncio.wait({connection, ready}, timeout=30, return_when=asyncio.FIRST_COMPLETED)
            if connection.done():
                connection.result()
                raise DiscordNotReady("Discord closed before the worker could read current permissions")
            if not ready.done():
                raise DiscordNotReady("Discord did not become ready")
            ready.result()
            yield client
        finally:
            ready.cancel()
            await client.close()
            await asyncio.gather(ready, connection, return_exceptions=True)
