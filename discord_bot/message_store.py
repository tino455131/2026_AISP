"""Local SQLite storage for current Discord message text."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class MessageStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS messages (
                    message_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    edited_at TEXT
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS messages_by_channel "
                "ON messages (guild_id, channel_id, created_at)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS backfill_state (
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    last_message_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, channel_id)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS deleted_messages (
                    message_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, message_id)
                )"""
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save_message(
        self,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        content: str,
        created_at: str,
    ) -> None:
        if not content:
            return
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO messages "
                "(message_id, guild_id, channel_id, author_id, content, created_at) "
                "SELECT ?, ?, ?, ?, ?, ? WHERE NOT EXISTS "
                "(SELECT 1 FROM deleted_messages WHERE message_id = ? AND guild_id = ?)",
                (message_id, guild_id, channel_id, author_id, content, created_at, message_id, guild_id),
            )

    def update_message(self, message_id: int, guild_id: int, content: str, edited_at: str) -> bool:
        with self._connection() as connection:
            result = connection.execute(
                "UPDATE messages SET content = ?, edited_at = ? "
                "WHERE message_id = ? AND guild_id = ?",
                (content, edited_at, message_id, guild_id),
            )
            return result.rowcount > 0

    def save_history_message(
        self,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        content: str,
        created_at: str,
        edited_at: str | None,
    ) -> None:
        """Store a historical message and its resume point in one transaction."""
        with self._connection() as connection:
            if content:
                connection.execute(
                    "INSERT OR IGNORE INTO messages "
                    "(message_id, guild_id, channel_id, author_id, content, created_at, edited_at) "
                    "SELECT ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS "
                    "(SELECT 1 FROM deleted_messages WHERE message_id = ? AND guild_id = ?)",
                    (
                        message_id, guild_id, channel_id, author_id, content, created_at, edited_at,
                        message_id, guild_id,
                    ),
                )
            connection.execute(
                "INSERT INTO backfill_state (guild_id, channel_id, last_message_id) VALUES (?, ?, ?) "
                "ON CONFLICT (guild_id, channel_id) DO UPDATE SET "
                "last_message_id = MAX(last_message_id, excluded.last_message_id)",
                (guild_id, channel_id, message_id),
            )

    def last_backfilled_message_id(self, guild_id: int, channel_id: int) -> int | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT last_message_id FROM backfill_state WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            ).fetchone()
            return row[0] if row else None

    def delete_message(self, message_id: int, guild_id: int) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO deleted_messages (message_id, guild_id) VALUES (?, ?)",
                (message_id, guild_id),
            )
            connection.execute(
                "DELETE FROM messages WHERE message_id = ? AND guild_id = ?",
                (message_id, guild_id),
            )

    def delete_messages(self, message_ids: set[int], guild_id: int) -> None:
        if not message_ids:
            return
        with self._connection() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO deleted_messages (message_id, guild_id) VALUES (?, ?)",
                ((message_id, guild_id) for message_id in message_ids),
            )
            connection.executemany(
                "DELETE FROM messages WHERE message_id = ? AND guild_id = ?",
                ((message_id, guild_id) for message_id in message_ids),
            )

    def delete_channel(self, guild_id: int, channel_id: int) -> None:
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM messages WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
            connection.execute(
                "DELETE FROM backfill_state WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )

    def delete_guild(self, guild_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM messages WHERE guild_id = ?", (guild_id,))
            connection.execute("DELETE FROM backfill_state WHERE guild_id = ?", (guild_id,))
            connection.execute("DELETE FROM deleted_messages WHERE guild_id = ?", (guild_id,))

    def recent_messages(self, guild_id: int, channel_id: int, limit: int = 100) -> list[sqlite3.Row]:
        """Read recent messages from one channel; callers must enforce viewer access."""
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                "SELECT message_id, guild_id, channel_id, author_id, content, created_at, edited_at "
                "FROM messages WHERE guild_id = ? AND channel_id = ? AND content <> '' "
                "ORDER BY created_at DESC, message_id DESC LIMIT ?",
                (guild_id, channel_id, limit),
            ).fetchall()
