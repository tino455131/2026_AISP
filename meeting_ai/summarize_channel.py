"""Summarize one channel's logged messages after the bot checks Discord access."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from sqlite_api import PROJECT_ROOT, SQLiteStore

from .interface import MeetingSummarizer, get_summarizer
from .summarize_text_meeting import build_text_lines


def summarize_channel(
    store: SQLiteStore, guild_id: int, channel_id: int, summarizer: MeetingSummarizer
) -> dict[str, int | str]:
    """Summarize up to 100 stored messages from one guild and channel."""
    rows = store.get_channel_message_list(guild_id, channel_id, limit=100)
    messages = [
        {
            "message_id": row["message_id"],
            "author_id": row["user_id"],
            "created_at": row["created_at"],
            "text": row["content"],
        }
        for row in rows
        if row["content"].strip()
    ]
    if not messages:
        return {"count": 0, "summary": ""}

    lines, names, _, _ = build_text_lines(messages)
    summary = summarizer.summarize(lines, names)
    return {"count": len(lines), "summary": summary.summary or "（沒有內容）"}


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", interpolate=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guild", type=int, required=True)
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args(argv)

    result = summarize_channel(SQLiteStore(args.db), args.guild, args.channel, get_summarizer())
    print("RESULT " + json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
