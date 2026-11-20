"""Summarize one text meeting and save it (voice_bot runs this after /meeting end).

    python -m meeting_ai.summarize_text_meeting [--db PATH] [--summarizer NAME] < meeting.json

Run from the repo root. stdin is one JSON object:
    {"guild_id", "channel_id", "started_by", "started_at", "ended_at",
     "start_message_id", "end_message_id",
     "messages": [{"message_id", "author_id", "name", "created_at", "text"}, ...]}
Prints one line "RESULT {json}" with Discord-ready markdown (owners as <@id> mentions).

Same summarizer as voice meetings (MEETING_SUMMARIZER), so text and voice records look alike.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .interface import MeetingLine, MeetingSummarizer, get_summarizer, render_markdown
from .text_meeting_store import TextMeetingStore

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "discord_bot" / "data" / "messages.sqlite3"


def build_text_lines(messages: list[dict]):
    """Messages -> (lines, label->name, label->author id, line id->message id).

    Lines are numbered 1, 2, 3… (short numbers for the model); the map keeps the real message ids.
    Authors get labels S1, S2… in order of first message, like voice speakers.
    """
    label_of: dict[str, str] = {}
    names: dict[str, str] = {}
    lines, source = [], {}
    for number, message in enumerate(messages, start=1):
        author = str(message["author_id"])
        label = label_of.setdefault(author, f"S{len(label_of) + 1}")
        names.setdefault(label, str(message.get("name") or author))
        text = " ".join(str(message["text"]).split())  # one line per message, as the prompt expects
        lines.append(MeetingLine(number, label, message["created_at"], text))
        source[number] = str(message["message_id"])
    return lines, names, {label: author for author, label in label_of.items()}, source


def summarize_text_meeting(store: TextMeetingStore, meeting: dict, summarizer: MeetingSummarizer) -> dict:
    lines, names, author_of, source = build_text_lines(meeting["messages"])
    summary = summarizer.summarize(lines, names)
    meeting_id = f"mtg-{meeting['channel_id']}-{meeting['start_message_id']}"
    store.save(
        {
            "meeting_id": meeting_id,
            "guild_id": int(meeting["guild_id"]),
            "channel_id": int(meeting["channel_id"]),
            "started_by": int(meeting["started_by"]),
            "started_at": meeting["started_at"],
            "ended_at": meeting["ended_at"],
            "start_message_id": int(meeting["start_message_id"]),
            "end_message_id": int(meeting["end_message_id"]),
            "message_count": len(lines),
            "summary": summary.to_json(),
            "source_message_ids": source,
            "speakers": author_of,
            "model": summarizer.name,
            "prompt_version": summarizer.prompt_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    mentions = {label: f"<@{author}>" for label, author in author_of.items()}
    return {
        "meeting_id": meeting_id,
        "summarizer": summarizer.name,
        "markdown": render_markdown(summary, mentions),
        "decisions": len(summary.decisions),
        "action_items": len(summary.action_items),
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="python -m meeting_ai.summarize_text_meeting")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--summarizer", help="simple, claude, claude-code or module:Class (default: $MEETING_SUMMARIZER)")
    args = p.parse_args(argv)

    meeting = json.loads(sys.stdin.read())
    result = summarize_text_meeting(TextMeetingStore(Path(args.db)), meeting, get_summarizer(args.summarizer))
    print(result["markdown"])
    print("RESULT " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
