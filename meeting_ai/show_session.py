"""Show one recording's summary or transcript to one person (voice_bot's "查看" buttons).

    python -m meeting_ai.show_session <session_id> --member <Discord user ID> --guild-id <ID> [--what summary|transcript]

Run from the repo root with text_bot's virtual environment (it needs discord.py).

This is also a working example, for the AI team, of reading through the interface in
docs/ai_memory_api.md: everything comes from AuthorizedTranscriptReader, which asks
Discord right now whether this person can read the voice channel's history. Whoever can
(even someone who missed the meeting) gets the text; anyone else gets nothing.

The permission check needs a live Discord connection, so this logs in as the recording
bot (VOICE_BOT_TOKEN in the project root .env) for a few seconds. Prints one line "RESULT {json}":
{"ok": true, "what": ..., "text": ...} or {"ok": false, "reason": ...}.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import discord
from dotenv import load_dotenv
from typing import Awaitable, Callable

from .discord_session import DiscordNotReady, ready_discord_client
from .interface import MeetingSummary, render_markdown
from sqlite_api import PROJECT_ROOT, SessionNotFound, SQLiteStore, TranscriptLine, resolve_database_path

from .summarize_session import build_lines

sys.path.insert(0, str(PROJECT_ROOT / "text_bot"))
from channel_access import AccessDenied, AccessUnavailable, ChannelAccess  # noqa: E402
from transcript_reader import AuthorizedTranscriptReader, SummaryView  # noqa: E402

NamesOf = Callable[[list[int]], Awaitable[dict[int, str]]]


def _unsure(line: TranscriptLine) -> bool:
    return bool(line.flags) or line.confidence < 0.4  # same rule as the summarizer's `uncertain`


def render_summary(view: SummaryView, lines: list[TranscriptLine], names: dict[int, str]) -> str:
    summary = MeetingSummary.from_dict(json.loads(view.summary.content))
    _, speaker_of_label = build_lines(lines)  # the same S1, S2 labels the summarizer saw
    owners = {label: names.get(sid, str(sid)) for label, sid in speaker_of_label.items()}
    text = render_markdown(summary, owners)
    if view.is_stale:
        text += "\n-# 摘要寫好之後逐字稿有變動，內容可能過時。"
    return f"{text}\n-# 摘要器：{view.summary.model}"


def render_transcript(lines: list[TranscriptLine], names: dict[int, str]) -> str:
    if not lines:
        return "（這場錄音沒有任何句子）"
    out = ["**🗒 逐字稿**"]
    for line in lines:
        at = datetime.fromisoformat(line.started_at).astimezone().strftime("%H:%M:%S")
        mark = " ⚠️" if _unsure(line) else ""
        out.append(f"`{at}` **{names.get(line.speaker_id, line.speaker_id)}**：{line.text}{mark}")
    if any(_unsure(line) for line in lines):
        out.append("-# ⚠️ = 可能聽錯")
    return "\n".join(out)


# spec.md: programs decide by ErrorCode, people read the message. When we cannot tell why,
# we only say the permission could not be confirmed.
REFUSED = {
    "ACCESS_DENIED_USER": "你沒有權限取得所要求的資訊。",
    "PERMISSION_UNVERIFIED": "暫時無法確認你的權限，請稍後再試。",
    "NOT_FOUND": "沒有找到符合條件的資料（這場錄音可能已經被刪除）。",
}
NO_SUMMARY = "這場錄音沒有摘要，可以改看逐字稿。"


def refused(error_code: str, message: str | None = None) -> dict:
    return {"ok": False, "error_code": error_code, "message": message or REFUSED[error_code]}


async def read_for_member(reader, member_id: int, session_id: str, what: str, names_of: NamesOf) -> dict:
    """Read through the reader only; `names_of` is asked for display names after access is granted."""
    try:
        lines = await reader.transcript_for(member_id, session_id)
        view = await reader.summary_for(member_id, session_id) if what == "summary" else None
    except AccessDenied:
        return refused("ACCESS_DENIED_USER")
    except AccessUnavailable:
        return refused("PERMISSION_UNVERIFIED")
    except SessionNotFound:
        return refused("NOT_FOUND")
    if what == "summary" and view is None:
        return refused("NOT_FOUND", NO_SUMMARY)  # the recording exists, its summary does not

    names = await names_of(sorted({line.speaker_id for line in lines}))
    text = render_summary(view, lines, names) if what == "summary" else render_transcript(lines, names)
    return {"ok": True, "what": what, "text": text}


def _token() -> str:
    """The recording bot's token, never printed."""
    token = os.environ.get("VOICE_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("找不到 VOICE_BOT_TOKEN（請填寫專案根目錄 .env）")
    return token


async def run(session_id: str, member_id: int, guild_id: int, what: str, db: Path) -> dict:
    try:
        async with ready_discord_client(_token()) as client:

            async def names_of(ids: list[int]) -> dict[int, str]:
                guild = client.get_guild(guild_id)
                names = {}
                for speaker_id in ids:
                    try:
                        names[speaker_id] = (await guild.fetch_member(speaker_id)).display_name
                    except discord.HTTPException:
                        names[speaker_id] = str(speaker_id)  # left the server, or Discord hiccup
                return names

            reader = AuthorizedTranscriptReader(ChannelAccess(client, guild_id), SQLiteStore(db))
            return await read_for_member(reader, member_id, session_id, what, names_of)
    except DiscordNotReady:
        return refused("PERMISSION_UNVERIFIED")


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", interpolate=False)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="python -m meeting_ai.show_session", description=__doc__.splitlines()[0])
    p.add_argument("session_id")
    p.add_argument("--member", type=int, required=True, help="who is asking (Discord user ID)")
    p.add_argument("--guild-id", type=int, default=os.getenv("DISCORD_GUILD_ID", "").strip() or None)
    p.add_argument("--what", choices=["summary", "transcript"], default="summary")
    p.add_argument("--db", type=Path, default=resolve_database_path(os.getenv("BOT_DB")))
    args = p.parse_args(argv)
    if args.guild_id is None or args.guild_id <= 0:
        p.error("請在根目錄 .env 設定 DISCORD_GUILD_ID，或傳入有效的 --guild-id")

    result = asyncio.run(run(args.session_id, args.member, args.guild_id, args.what, args.db))
    print("RESULT " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
