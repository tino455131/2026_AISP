"""Shared SQLite API for Discord text messages, voice transcripts, and summaries.

All SQL reads and writes live here. User-facing reads must go through the
Discord permission readers in channel_access.py or transcript_reader.py.
This module uses only Python's standard library so both virtual environments
can import it through the editable project installation.

Example:
    from sqlite_api import DEFAULT_DB, SQLiteStore

    store = SQLiteStore(DEFAULT_DB)
    store.save_message(message_id, guild_id, channel_id, author_id, text, created_at)

The storage methods do not check a Discord member's permissions. For a
user-facing read, use AuthorizedMessageReader or AuthorizedTranscriptReader.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DB = PROJECT_ROOT / "data" / "messages.sqlite3"


def resolve_database_path(configured_path: str | None = None) -> Path:
    """Resolve the shared database path from the optional BOT_DB setting.

    Args:
        configured_path: BOT_DB value. Relative paths start at the project
            root. An empty or omitted value selects DEFAULT_DB.

    Returns:
        The absolute path to the SQLite database.
    """
    value = (configured_path or "").strip()
    return PROJECT_ROOT / value if value else DEFAULT_DB


class SessionNotFound(LookupError):
    """Report a missing voice session.
    """


@dataclass(frozen=True)
class VoiceSession:
    """Metadata for one voice recording.

    Attributes:
        session_id: Stable recording ID.
        guild_id: Discord server ID.
        channel_id: Discord channel or thread ID.
        started_at: Start time in ISO 8601 UTC.
        ended_at: End time in ISO 8601 UTC, or None while open.
        started_by: Discord ID of the recording initiator, if known.
    """
    session_id: str
    guild_id: int
    channel_id: int  # the voice channel
    started_at: str  # ISO 8601, UTC, same format as messages.created_at
    ended_at: str | None
    started_by: int | None  # Discord user id of whoever started the recording


@dataclass(frozen=True)
class NewLine:
    """One recognized sentence ready to store.

    Attributes:
        speaker_id: Discord user ID of the speaker.
        started_at: Start time in ISO 8601 UTC.
        ended_at: End time in ISO 8601 UTC.
        text: Cleaned transcript text.
        text_raw: Original transcription output.
        confidence: Recognition confidence between 0 and 1.
        flags: Optional recognition warnings.
    """

    speaker_id: int  # Discord user id (names are looked up when reading)
    started_at: str
    ended_at: str
    text: str  # Taiwan Traditional Chinese, after cleanup
    text_raw: str  # recognizer output, for debugging
    confidence: float  # 0-1
    flags: tuple[str, ...] = ()  # e.g. ("low_confidence",)


@dataclass(frozen=True)
class TranscriptLine:
    """One stored transcript sentence.

    Attributes:
        line_id: SQLite-generated identifier for this sentence.
        session_id: Stable recording ID.
        speaker_id: Discord user ID of the speaker.
        started_at: Start time in ISO 8601 UTC.
        ended_at: End time in ISO 8601 UTC.
        text: Cleaned transcript text.
        confidence: Recognition confidence between 0 and 1.
        flags: Recognition warnings as a tuple.
    """
    line_id: int
    session_id: str
    speaker_id: int
    started_at: str
    ended_at: str
    text: str
    confidence: float
    flags: tuple[str, ...]


@dataclass(frozen=True)
class SessionSummary:
    """The saved summary and its generation metadata.

    Attributes:
        session_id: Stable recording ID.
        content: The stored summary text or serialized JSON.
        model: Name of the summarizer or model.
        prompt_version: Version of the prompt or rules.
        source_line_count: Number of lines at the time of saving.
        created_at: Creation time as an ISO 8601 string in UTC.
    """
    session_id: str
    content: str
    model: str  # which model wrote it
    prompt_version: str  # which prompt wrote it, so old summaries can be redone
    source_line_count: int  # how many lines existed when it was written
    created_at: str


class SQLiteStore:
    """Provide one storage interface for text, transcripts, and summaries.

    Args:
        path: Location of the existing or new SQLite database file.

    Note:
        The caller must check Discord permissions before returning stored
        content to a user. This class only manages persistence.
    """

    def __init__(self, path: str | Path) -> None:
        """Open or initialize the shared database without changing existing rows.

        Args:
            path: SQLite file path shared by the text bot and voice pipeline.

        Raises:
            OSError: The parent directory could not be created.
            sqlite3.Error: SQLite could not open or initialize the database.
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
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
            connection.execute(
                """CREATE TABLE IF NOT EXISTS voice_sessions (
                    session_id TEXT PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    started_by INTEGER
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS voice_sessions_by_channel "
                "ON voice_sessions (guild_id, channel_id, started_at)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS voice_lines (
                    line_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    speaker_id INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    text TEXT NOT NULL,
                    text_raw TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    flags TEXT NOT NULL DEFAULT '[]'
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS voice_lines_by_session "
                "ON voice_lines (session_id, started_at)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS voice_session_summaries (
                    session_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    source_line_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
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

    # Text message operations.

    def save_message(
        self,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        content: str,
        created_at: str,
        *,
        edited_at: str | None = None,
    ) -> None:
        """Insert live text, or apply a newer edit to an existing message.

        Args:
            message_id: Discord message ID.
            guild_id: Discord server ID.
            channel_id: Discord channel or thread ID.
            author_id: Discord user ID of the author.
            content: Text from the Discord message.
            created_at: Creation time as an ISO 8601 string in UTC.
            edited_at: Edit time in ISO 8601 UTC, when saving a text edit.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        if not content and edited_at is None:
            return
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO messages "
                "(message_id, guild_id, channel_id, author_id, content, created_at, edited_at) "
                "SELECT ?, ?, ?, ?, ?, ?, ? WHERE NOT EXISTS "
                "(SELECT 1 FROM deleted_messages WHERE message_id = ? AND guild_id = ?) "
                "ON CONFLICT(message_id) DO UPDATE SET "
                "content = excluded.content, edited_at = excluded.edited_at "
                "WHERE messages.guild_id = excluded.guild_id AND excluded.edited_at IS NOT NULL "
                "AND (messages.edited_at IS NULL "
                "OR julianday(excluded.edited_at) >= julianday(messages.edited_at))",
                (message_id, guild_id, channel_id, author_id, content, created_at, edited_at, message_id, guild_id),
            )

    def update_message(self, message_id: int, guild_id: int, content: str, edited_at: str) -> bool:
        """Apply an edit to a stored message unless a newer edit is already saved.

        Args:
            message_id: Discord message ID.
            guild_id: Discord server ID.
            content: Updated text. Blank text is hidden from recent queries.
            edited_at: Edit time as an ISO 8601 string in UTC.

        Returns:
            True if a stored message matched the server and ID.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            result = connection.execute(
                "UPDATE messages SET content = ?, edited_at = ? "
                "WHERE message_id = ? AND guild_id = ? "
                "AND (messages.edited_at IS NULL OR julianday(?) >= julianday(messages.edited_at))",
                (content, edited_at, message_id, guild_id, edited_at),
            )
            if result.rowcount:
                return True
            return connection.execute(
                "SELECT 1 FROM messages WHERE message_id = ? AND guild_id = ?",
                (message_id, guild_id),
            ).fetchone() is not None

    def save_historical_message(
        self,
        message_id: int,
        guild_id: int,
        channel_id: int,
        author_id: int,
        content: str,
        created_at: str,
        edited_at: str | None,
    ) -> None:
        """Store a historical message and advance the resume point atomically.

        Args:
            message_id: Discord message ID.
            guild_id: Discord server ID.
            channel_id: Discord channel or thread ID.
            author_id: Discord user ID of the author.
            content: Message text. Empty text only advances the resume point.
            created_at: Creation time as an ISO 8601 string in UTC.
            edited_at: Edit time as an ISO 8601 string in UTC. Use None for an unedited message.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
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

    def get_last_backfilled_message_id(self, guild_id: int, channel_id: int) -> int | None:
        """Read the highest Discord message ID processed during backfill.

        Args:
            guild_id: Discord server ID.
            channel_id: Discord channel or thread ID.

        Returns:
            The stored resume ID, or None before the first import.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT last_message_id FROM backfill_state WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            ).fetchone()
            return row[0] if row else None

    def delete_message(self, message_id: int, guild_id: int) -> None:
        """Remove a message and prevent a later backfill from restoring it.

        Args:
            message_id: Discord message ID.
            guild_id: Discord server ID.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
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
        """Remove multiple messages and record their deletion atomically.

        Args:
            message_ids: Discord message IDs to delete.
            guild_id: Discord server ID.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
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

    def list_recent_messages(self, guild_id: int, channel_id: int, limit: int = 100) -> list[sqlite3.Row]:
        """Read saved nonempty messages from one server and channel.

        Args:
            guild_id: Discord server ID.
            channel_id: Discord channel or thread ID.
            limit: Maximum number of rows, from 1 to 1000.

        Returns:
            SQLite rows, newest first by creation time then message ID.

        Raises:
            ValueError: limit is outside the allowed range.
            sqlite3.Error: SQLite could not complete the operation.
        """
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

    # Voice transcript and summary operations.

    def create_voice_session(
        self,
        session_id: str,
        guild_id: int,
        channel_id: int,
        started_at: str,
        started_by: int | None = None,
    ) -> None:
        """Create a voice session with an optional initiator.

        Args:
            session_id: Stable recording ID.
            guild_id: Discord server ID.
            channel_id: Discord channel or thread ID.
            started_at: Start time in ISO 8601 UTC.
            started_by: Discord user ID of the initiator, if known.

        Raises:
            sqlite3.IntegrityError: The session ID already exists.
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO voice_sessions "
                "(session_id, guild_id, channel_id, started_at, started_by) VALUES (?, ?, ?, ?, ?)",
                (session_id, guild_id, channel_id, started_at, started_by),
            )

    def add_transcript_lines(self, session_id: str, lines: Iterable[NewLine]) -> int:
        """Append a batch of transcript lines to one voice session.

        Args:
            session_id: Stable recording ID.
            lines: Sentences to add.

        Returns:
            The number of sentences inserted.

        Raises:
            SessionNotFound: No session has the provided ID.
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            session = self._session_row(connection, session_id)
            rows = [
                (
                    session_id, session[1], session[2], line.speaker_id, line.started_at,
                    line.ended_at, line.text, line.text_raw, line.confidence,
                    json.dumps(list(line.flags)),
                )
                for line in lines
            ]
            connection.executemany(
                "INSERT INTO voice_lines (session_id, guild_id, channel_id, speaker_id, started_at, "
                "ended_at, text, text_raw, confidence, flags) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            return len(rows)

    def end_voice_session(self, session_id: str, ended_at: str) -> None:
        """Set the end timestamp for an existing voice session.

        Args:
            session_id: Stable recording ID.
            ended_at: End time in ISO 8601 UTC.

        Raises:
            SessionNotFound: No session has the provided ID.
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            self._session_row(connection, session_id)
            connection.execute(
                "UPDATE voice_sessions SET ended_at = ? WHERE session_id = ?", (ended_at, session_id)
            )

    def save_session_summary(
        self, session_id: str, content: str, model: str, prompt_version: str, created_at: str
    ) -> None:
        """Save or replace a summary and record its current source line count.

        Args:
            session_id: Stable recording ID.
            content: Summary text or serialized JSON.
            model: Name of the summarizer or model.
            prompt_version: Version of the prompt or rules.
            created_at: Creation time as an ISO 8601 string in UTC.

        Raises:
            SessionNotFound: No session has the provided ID.
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            self._session_row(connection, session_id)
            count = self._line_count(connection, session_id)
            connection.execute(
                "INSERT INTO voice_session_summaries "
                "(session_id, content, model, prompt_version, source_line_count, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (session_id) DO UPDATE SET "
                "content = excluded.content, model = excluded.model, "
                "prompt_version = excluded.prompt_version, "
                "source_line_count = excluded.source_line_count, created_at = excluded.created_at",
                (session_id, content, model, prompt_version, count, created_at),
            )

    def delete_speaker_transcript(self, session_id: str, speaker_id: int) -> None:
        """Remove a speaker's lines and invalidate the saved summary.

        Args:
            session_id: Stable recording ID.
            speaker_id: Discord user ID of the speaker.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM voice_lines WHERE session_id = ? AND speaker_id = ?",
                (session_id, speaker_id),
            )
            connection.execute("DELETE FROM voice_session_summaries WHERE session_id = ?", (session_id,))

    def delete_voice_session(self, session_id: str) -> None:
        """Remove a voice session, all of its lines, and its summary.

        Args:
            session_id: Stable recording ID.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            self._delete_sessions(connection, "session_id = ?", (session_id,))

    def delete_channel(self, guild_id: int, channel_id: int) -> None:
        """Remove saved messages, the resume point, and voice data for one channel.

        Args:
            guild_id: Discord server ID.
            channel_id: Discord channel or thread ID.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM messages WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
            connection.execute(
                "DELETE FROM backfill_state WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )
            self._delete_sessions(connection, "guild_id = ? AND channel_id = ?", (guild_id, channel_id))

    def delete_guild(self, guild_id: int) -> None:
        """Remove saved text, voice data, and import and deletion markers for a server.

        Args:
            guild_id: Discord server ID.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            connection.execute("DELETE FROM messages WHERE guild_id = ?", (guild_id,))
            connection.execute("DELETE FROM backfill_state WHERE guild_id = ?", (guild_id,))
            connection.execute("DELETE FROM deleted_messages WHERE guild_id = ?", (guild_id,))
            self._delete_sessions(connection, "guild_id = ?", (guild_id,))

    # Voice transcript and summary reads and helpers.

    def get_voice_session(self, session_id: str) -> VoiceSession:
        """Read metadata for one voice session.

        Args:
            session_id: Stable recording ID.

        Returns:
            Metadata for the requested recording.

        Raises:
            SessionNotFound: No session has the provided ID.
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            return VoiceSession(*self._session_row(connection, session_id))

    def list_recent_voice_sessions(self, guild_id: int, channel_id: int, limit: int = 20) -> list[VoiceSession]:
        """List voice sessions from one server and channel.

        Args:
            guild_id: Discord server ID.
            channel_id: Discord channel or thread ID.
            limit: Maximum number of sessions, from 1 to 200.

        Returns:
            Sessions ordered by start time, newest first.

        Raises:
            ValueError: limit is outside the allowed range.
            sqlite3.Error: SQLite could not complete the operation.
        """
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT session_id, guild_id, channel_id, started_at, ended_at, started_by "
                "FROM voice_sessions WHERE guild_id = ? AND channel_id = ? "
                "ORDER BY started_at DESC LIMIT ?",
                (guild_id, channel_id, limit),
            ).fetchall()
        return [VoiceSession(*row) for row in rows]

    def list_transcript_lines(self, session_id: str) -> list[TranscriptLine]:
        """Read the saved sentences for one voice session.

        Args:
            session_id: Stable recording ID.

        Returns:
            Lines ordered by start time and line ID. Empty if no lines exist.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT line_id, session_id, speaker_id, started_at, ended_at, text, confidence, flags "
                "FROM voice_lines WHERE session_id = ? ORDER BY started_at, line_id",
                (session_id,),
            ).fetchall()
        return [
            TranscriptLine(*row[:7], flags=tuple(json.loads(row[7]))) for row in rows
        ]

    def get_session_summary(self, session_id: str) -> SessionSummary | None:
        """Read the saved summary for a voice session.

        Args:
            session_id: Stable recording ID.

        Returns:
            The summary and its metadata, or None if unavailable.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            row = connection.execute(
                "SELECT session_id, content, model, prompt_version, source_line_count, created_at "
                "FROM voice_session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return SessionSummary(*row) if row else None

    def count_transcript_lines(self, session_id: str) -> int:
        """Count saved sentences for one voice session.

        Args:
            session_id: Stable recording ID.

        Returns:
            The number of lines, or zero if no lines exist.

        Raises:
            sqlite3.Error: SQLite could not complete the operation.
        """
        with self._connection() as connection:
            return self._line_count(connection, session_id)

    @staticmethod
    def _session_row(connection: sqlite3.Connection, session_id: str) -> tuple:
        row = connection.execute(
            "SELECT session_id, guild_id, channel_id, started_at, ended_at, started_by "
            "FROM voice_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        return row

    @staticmethod
    def _line_count(connection: sqlite3.Connection, session_id: str) -> int:
        return connection.execute(
            "SELECT COUNT(*) FROM voice_lines WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

    @staticmethod
    def _delete_sessions(connection: sqlite3.Connection, where: str, params: tuple) -> None:
        ids = [row[0] for row in connection.execute(f"SELECT session_id FROM voice_sessions WHERE {where}", params)]
        for table in ("voice_lines", "voice_session_summaries", "voice_sessions"):
            connection.executemany(f"DELETE FROM {table} WHERE session_id = ?", ((i,) for i in ids))

__all__ = [
    "PROJECT_ROOT", "DEFAULT_DB", "resolve_database_path", "SQLiteStore", "SessionNotFound", "VoiceSession",
    "NewLine", "TranscriptLine", "SessionSummary",
]
