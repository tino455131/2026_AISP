"""Local SQLite storage for voice-channel transcripts (feature F6).

語音逐字稿和 MessageStore 的文字訊息存在同一個資料庫檔（data/messages.sqlite3），
讓 AI 組只需要從一個地方讀資料。每一句都保留語音頻道的 guild_id／channel_id，
所以讀取時可以沿用 ChannelAccess 的權限檢查（見 transcript_reader.py）。

三張表：
- voice_sessions：一場錄音／會議一筆
- voice_lines：一句話一筆（誰說的、何時、文字、信心分數、警告標記）
- voice_session_summaries：整理過的會議摘要（AI 組產生、這裡負責保存與失效）

This module only uses the standard library, so voice_stt (another venv) can
load it to write transcripts.
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


class SessionNotFound(LookupError):
    """No voice session with this id is stored."""


@dataclass(frozen=True)
class VoiceSession:
    session_id: str
    guild_id: int
    channel_id: int  # the voice channel
    started_at: str  # ISO 8601, UTC, same format as messages.created_at
    ended_at: str | None
    started_by: int | None  # Discord user id of whoever started the recording


@dataclass(frozen=True)
class NewLine:
    """One recognized sentence, ready to be saved."""

    speaker_id: int  # Discord user id (names are looked up when reading)
    started_at: str
    ended_at: str
    text: str  # Taiwan Traditional Chinese, after cleanup
    text_raw: str  # recognizer output, for debugging
    confidence: float  # 0-1
    flags: tuple[str, ...] = ()  # e.g. ("low_confidence",)


@dataclass(frozen=True)
class TranscriptLine:
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
    session_id: str
    content: str
    model: str  # which model wrote it
    prompt_version: str  # which prompt wrote it, so old summaries can be redone
    source_line_count: int  # how many lines existed when it was written
    created_at: str


class TranscriptStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            # WAL lets the bot and voice_stt (two processes) write the same file
            # without blocking each other. The setting is stored in the database
            # file, so it also applies to MessageStore's connections.
            connection.execute("PRAGMA journal_mode=WAL")
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

    # ---- writing -----------------------------------------------------------

    def start_session(
        self,
        session_id: str,
        guild_id: int,
        channel_id: int,
        started_at: str,
        started_by: int | None = None,
    ) -> None:
        """Create a session; an existing id is an error, never overwritten."""
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO voice_sessions "
                "(session_id, guild_id, channel_id, started_at, started_by) VALUES (?, ?, ?, ?, ?)",
                (session_id, guild_id, channel_id, started_at, started_by),
            )

    def add_lines(self, session_id: str, lines: Iterable[NewLine]) -> int:
        """Save sentences of one session in one transaction; returns how many."""
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

    def end_session(self, session_id: str, ended_at: str) -> None:
        with self._connection() as connection:
            self._session_row(connection, session_id)
            connection.execute(
                "UPDATE voice_sessions SET ended_at = ? WHERE session_id = ?", (ended_at, session_id)
            )

    def save_summary(
        self, session_id: str, content: str, model: str, prompt_version: str, created_at: str
    ) -> None:
        """Store (or replace) the session's summary, remembering how many lines it saw."""
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

    # ---- deleting (a summary is always dropped with its sources) -----------

    def delete_speaker(self, session_id: str, speaker_id: int) -> None:
        """Remove one person's sentences, e.g. when they withdraw consent.

        The summary is deleted too, because it may repeat what they said.
        """
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM voice_lines WHERE session_id = ? AND speaker_id = ?",
                (session_id, speaker_id),
            )
            connection.execute("DELETE FROM voice_session_summaries WHERE session_id = ?", (session_id,))

    def delete_session(self, session_id: str) -> None:
        with self._connection() as connection:
            self._delete_sessions(connection, "session_id = ?", (session_id,))

    def delete_channel(self, guild_id: int, channel_id: int) -> None:
        with self._connection() as connection:
            self._delete_sessions(connection, "guild_id = ? AND channel_id = ?", (guild_id, channel_id))

    def delete_guild(self, guild_id: int) -> None:
        with self._connection() as connection:
            self._delete_sessions(connection, "guild_id = ?", (guild_id,))

    # ---- reading (callers must check access; AI code uses transcript_reader) -

    def get_session(self, session_id: str) -> VoiceSession:
        with self._connection() as connection:
            return VoiceSession(*self._session_row(connection, session_id))

    def recent_sessions(self, guild_id: int, channel_id: int, limit: int = 20) -> list[VoiceSession]:
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

    def lines(self, session_id: str) -> list[TranscriptLine]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT line_id, session_id, speaker_id, started_at, ended_at, text, confidence, flags "
                "FROM voice_lines WHERE session_id = ? ORDER BY started_at, line_id",
                (session_id,),
            ).fetchall()
        return [
            TranscriptLine(*row[:7], flags=tuple(json.loads(row[7]))) for row in rows
        ]

    def summary(self, session_id: str) -> SessionSummary | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT session_id, content, model, prompt_version, source_line_count, created_at "
                "FROM voice_session_summaries WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return SessionSummary(*row) if row else None

    def line_count(self, session_id: str) -> int:
        with self._connection() as connection:
            return self._line_count(connection, session_id)

    # ---- helpers -----------------------------------------------------------

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
