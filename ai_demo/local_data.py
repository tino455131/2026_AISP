"""LocalData：唯讀打開本機的 bot 資料庫，把一場會議（語音或文字）整理成 AI 功能要的樣子。

【測試用】這裡不檢查 Discord 權限。spec R15：衍生資料要沿用來源的限制，
正式版給使用者看的內容一律要經過讀取介面（語音：AuthorizedTranscriptReader）。

會議 ID：
- 語音錄音：rec-…（voice_sessions 表）
- 文字會議：mtg-…（text_meetings 表；原文從 messages 表讀，文字記錄沒開的話就只用摘要）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from meeting_ai.summarize_text_meeting import MENTION, build_text_lines
from sqlite_api import DEFAULT_DB, SQLiteStore

REPO_ROOT = Path(__file__).resolve().parents[1]
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

        self.store = SQLiteStore(self.db, read_only=True)

    def meetings(self) -> list[dict]:
        """List both kinds of meeting, most recent first."""
        return self.store.list_meeting_overviews()

    def meeting(self, meeting_id: str, messages: list[dict] | None = None) -> MeetingRecord:
        """Build an AI meeting record from authorized input or locally stored data.

        None allows an offline text lookup. An explicit empty Discord result uses the
        saved meeting summary as context.
        """
        if meeting_id.startswith("mtg-"):
            data = self.store.get_text_meeting_data(meeting_id, include_saved_messages=messages is None)
            if data is not None:
                return self._text(meeting_id, *data, messages)
        voice = self.store.get_voice_meeting_data(meeting_id)
        if voice is not None:
            return self._voice(*voice)
        raise LookupError(meeting_id)

    def _voice(self, session, rows, summary) -> MeetingRecord:
        speakers: dict[str, int] = {}
        lines = []
        for number, row in enumerate(rows, start=1):
            label = next((k for k, v in speakers.items() if v == row.speaker_id), None)
            if label is None:
                label = f"S{len(speakers) + 1}"
                speakers[label] = row.speaker_id
            lines.append(SourceLine(
                number, label, row.speaker_id, row.started_at, row.text,
                uncertain=bool(row.flags) or row.confidence < 0.4,
                source_ref={"kind": "voice_line", "session_id": session.session_id, "line_id": row.line_id},
            ))
        return MeetingRecord(
            session.session_id, "voice", session.guild_id, session.channel_id, session.started_by,
            session.started_at, session.ended_at, tuple(lines),
            json.loads(summary.content) if summary else None,
            self._voice_names(session.session_id, speakers), speakers,
        )

    def _voice_names(self, session_id: str, speakers: dict[str, int]) -> dict[str, str]:
        manifest = self.recordings / session_id / "manifest.json"  # voice_bot keeps display names here
        if not manifest.is_file():
            return {}
        names = json.loads(manifest.read_text(encoding="utf-8")).get("names", {})
        return {label: names[str(uid)] for label, uid in speakers.items() if str(uid) in names}

    def _text(self, meeting_id: str, row: dict, saved_rows, messages: list[dict] | None) -> MeetingRecord:
        speakers = {label: int(uid) for label, uid in row["speakers"].items()}
        summary = row["summary"]
        names: dict[str, str] = {}
        lines = []
        from_table = messages is None
        if from_table:
            people = set(speakers.values())
            messages = [
                {"message_id": m["message_id"], "author_id": m["user_id"], "created_at": m["created_at"],
                 "text": m["content"], "mentions": [{"id": found} for found in MENTION.findall(m["content"])]}
                for m in saved_rows if m["user_id"] in people
            ]
        if messages:  # same labels as the summary, "<@id>" becomes "@名字（S3）"
            built, names, user_of, source = build_text_lines(messages)
            if from_table:
                names = {}  # the messages table keeps no display names, only ids
            speakers = {label: int(uid) for label, uid in user_of.items()}
            lines = [
                SourceLine(line.line_id, line.speaker, speakers[line.speaker], line.started_at, line.text,
                           source_ref={"kind": "message", "channel_id": row["channel_id"], "message_id": source[line.line_id]})
                for line in built
            ]
        if not lines:
            lines = summary_lines(meeting_id, summary, speakers)
        return MeetingRecord(
            meeting_id, "text", row["guild_id"], row["channel_id"], row["started_by"],
            row["started_at"], row["ended_at"], tuple(lines), summary, names, speakers,
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
