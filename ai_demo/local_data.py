"""LocalData：唯讀打開本機的 bot 資料庫，把一場會議（語音或文字）整理成 AI 功能要的樣子。

【測試用】這裡不檢查 Discord 權限。spec R15：衍生資料要沿用來源的限制，
正式版給使用者看的內容一律要經過讀取介面（語音：AuthorizedTranscriptReader）。

會議 ID：
- 語音錄音：rec-…（voice_sessions 表）
- 文字會議：mtg-…（text_meetings 表；原文從 messages 表讀，文字記錄沒開的話就只用摘要）
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "discord_bot" / "data" / "messages.sqlite3"
DEFAULT_RECORDINGS = REPO_ROOT / "voice_bot" / "recordings"


@dataclass(frozen=True)
class SourceLine:
    """One thing said or written in the meeting, numbered 1, 2, 3… for the model to cite."""

    line_id: int
    speaker_label: str  # S1, S2… (same labels as the summaries)
    author_user_id: int | None  # Discord user id; None for a line taken from the summary
    created_at: str  # UTC RFC 3339
    text: str
    uncertain: bool = False  # speech recognition was not sure
    source_ref: dict = field(default_factory=dict)  # where it came from, kept with every result


@dataclass(frozen=True)
class MeetingRecord:
    meeting_id: str
    kind: str  # "voice" | "text"
    guild_id: int
    channel_id: int
    started_by: int | None
    started_at: str
    ended_at: str | None
    lines: tuple[SourceLine, ...]
    summary: dict | None
    names: dict[str, str]  # label -> display name, when known
    speakers: dict[str, int]  # label -> Discord user id

    def label_of(self, user_id: int | str) -> str | None:
        return next((label for label, uid in self.speakers.items() if str(uid) == str(user_id)), None)


class LocalData:
    def __init__(self, db: Path = DEFAULT_DB, recordings: Path = DEFAULT_RECORDINGS) -> None:
        self.db = Path(db)
        self.recordings = Path(recordings)
        if not self.db.is_file():
            raise FileNotFoundError(f"找不到資料庫 {self.db}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)  # read-only
        connection.row_factory = sqlite3.Row
        return connection

    def _tables(self, connection) -> set[str]:
        return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def meetings(self) -> list[dict]:
        """Every meeting, newest first: id, kind, channel, start time, how many lines, summary or not."""
        out = []
        with self._connect() as connection:
            tables = self._tables(connection)
            if "voice_sessions" in tables:
                for row in connection.execute(
                    """SELECT s.session_id, s.channel_id, s.started_at,
                              (SELECT COUNT(*) FROM voice_lines l WHERE l.session_id = s.session_id) AS lines,
                              EXISTS (SELECT 1 FROM voice_session_summaries m WHERE m.session_id = s.session_id) AS summary
                       FROM voice_sessions s"""
                ):
                    out.append({"meeting_id": row[0], "kind": "voice", "channel_id": row[1], "started_at": row[2],
                                "line_count": row[3], "has_summary": bool(row[4])})
            if "text_meetings" in tables:
                for row in connection.execute("SELECT meeting_id, channel_id, started_at, message_count FROM text_meetings"):
                    out.append({"meeting_id": row[0], "kind": "text", "channel_id": row[1], "started_at": row[2],
                                "line_count": row[3], "has_summary": True})
        return sorted(out, key=lambda m: m["started_at"], reverse=True)

    def meeting(self, meeting_id: str) -> MeetingRecord:
        """Raises LookupError when there is no such meeting (spec: NOT_FOUND)."""
        with self._connect() as connection:
            tables = self._tables(connection)
            if meeting_id.startswith("mtg-") and "text_meetings" in tables:
                return self._text(connection, tables, meeting_id)
            if "voice_sessions" in tables:
                return self._voice(connection, meeting_id)
        raise LookupError(meeting_id)

    def _voice(self, connection, session_id: str) -> MeetingRecord:
        session = connection.execute("SELECT * FROM voice_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if session is None:
            raise LookupError(session_id)
        rows = connection.execute(
            "SELECT * FROM voice_lines WHERE session_id = ? ORDER BY started_at, line_id", (session_id,)
        ).fetchall()
        speakers: dict[str, int] = {}
        lines = []
        for number, row in enumerate(rows, start=1):
            label = next((k for k, v in speakers.items() if v == row["speaker_id"]), None)
            if label is None:
                label = f"S{len(speakers) + 1}"
                speakers[label] = row["speaker_id"]
            lines.append(SourceLine(
                number, label, row["speaker_id"], row["started_at"], row["text"],
                uncertain=bool(json.loads(row["flags"] or "[]")) or row["confidence"] < 0.4,  # same rule as summaries
                source_ref={"kind": "voice_line", "session_id": session_id, "line_id": row["line_id"]},
            ))
        summary_row = connection.execute(
            "SELECT content FROM voice_session_summaries WHERE session_id = ?", (session_id,)
        ).fetchone()
        return MeetingRecord(
            session_id, "voice", session["guild_id"], session["channel_id"], session["started_by"],
            session["started_at"], session["ended_at"], tuple(lines),
            json.loads(summary_row[0]) if summary_row else None,
            self._voice_names(session_id, speakers), speakers,
        )

    def _voice_names(self, session_id: str, speakers: dict[str, int]) -> dict[str, str]:
        manifest = self.recordings / session_id / "manifest.json"  # voice_bot keeps display names here
        if not manifest.is_file():
            return {}
        names = json.loads(manifest.read_text(encoding="utf-8")).get("names", {})
        return {label: names[str(uid)] for label, uid in speakers.items() if str(uid) in names}

    def _text(self, connection, tables: set[str], meeting_id: str) -> MeetingRecord:
        row = connection.execute("SELECT * FROM text_meetings WHERE meeting_id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise LookupError(meeting_id)
        speakers = {label: int(uid) for label, uid in json.loads(row["speakers"]).items()}
        summary = json.loads(row["summary"])
        lines = []
        if "messages" in tables:  # only when the text logger was running during the meeting
            messages = connection.execute(
                """SELECT * FROM messages WHERE guild_id = ? AND channel_id = ?
                   AND message_id > ? AND message_id < ? ORDER BY message_id""",
                (row["guild_id"], row["channel_id"], row["start_message_id"], row["end_message_id"]),
            ).fetchall()
            for number, message in enumerate(messages, start=1):
                label = next((k for k, v in speakers.items() if v == message["author_id"]), None)
                if label is None:  # e.g. a bot message: not part of the meeting
                    continue
                lines.append(SourceLine(
                    len(lines) + 1, label, message["author_id"], message["created_at"], " ".join(message["content"].split()),
                    source_ref={"kind": "message", "channel_id": row["channel_id"], "message_id": message["message_id"]},
                ))
        if not lines:
            lines = summary_lines(meeting_id, summary, speakers)
        return MeetingRecord(
            meeting_id, "text", row["guild_id"], row["channel_id"], row["started_by"],
            row["started_at"], row["ended_at"], tuple(lines), summary, {}, speakers,
        )


def summary_lines(meeting_id: str, summary: dict, speakers: dict[str, int]) -> list[SourceLine]:
    """When the original messages are not stored, the AI works from the summary's own items."""
    texts = [summary.get("summary", "")]
    texts += [f"決定：{d['text']}" for d in summary.get("decisions", [])]
    texts += [
        f"待辦：{a['task']}（負責：{a.get('owner') or '未指定'}{'，期限：' + a['due'] if a.get('due') else ''}）"
        for a in summary.get("action_items", [])
    ]
    return [
        SourceLine(number, "摘要", None, "", text, source_ref={"kind": "summary", "meeting_id": meeting_id})
        for number, text in enumerate((t for t in texts if t), start=1)
    ]
