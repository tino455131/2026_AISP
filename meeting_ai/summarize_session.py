"""Summarize one stored recording and save the summary (voice_bot runs this after transcribing).

    python -m meeting_ai.summarize_session <session_id> [--db PATH] [--names manifest.json] [--summarizer simple|openai]

Run from the repo root. Prints one line "RESULT {json}" with Discord-ready markdown.

This is the system summarizing a session for storage: the summary lives with
its session and is read through AuthorizedTranscriptReader, so it gets the same
voice-channel permission check as the transcript itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from sqlite_api import PROJECT_ROOT, SQLiteStore, resolve_database_path

from .interface import MeetingLine, MeetingSummarizer, get_summarizer, render_markdown


def build_lines(stored_lines) -> tuple[list[MeetingLine], dict[str, int]]:
    """Give speakers short labels (S1, S2, ... in order of first speaking)."""
    label_of: dict[int, str] = {}
    lines = []
    for row in stored_lines:
        label = label_of.setdefault(row.speaker_id, f"S{len(label_of) + 1}")
        uncertain = bool(row.flags) or row.confidence < 0.4
        lines.append(MeetingLine(row.line_id, label, row.started_at, row.text, uncertain))
    return lines, {label: speaker_id for speaker_id, label in label_of.items()}


def summarize_session(
    store, session_id: str, summarizer: MeetingSummarizer, names: dict[str, str] | None = None
) -> dict:
    lines, speaker_of_label = build_lines(store.list_transcript_lines(session_id))
    names = names or {}
    speakers = {label: names[str(sid)] for label, sid in speaker_of_label.items() if str(sid) in names}

    summary = summarizer.summarize(lines, speakers)
    store.save_session_summary(
        session_id,
        summary.to_json(),
        model=summarizer.name,
        prompt_version=summarizer.prompt_version,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    mentions = {label: f"<@{sid}>" for label, sid in speaker_of_label.items()}
    return {
        "session_id": session_id,
        "summarizer": summarizer.name,
        "markdown": render_markdown(summary, mentions),
        "decisions": len(summary.decisions),
        "action_items": len(summary.action_items),
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", interpolate=False)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="python -m meeting_ai.summarize_session")
    p.add_argument("session_id")
    p.add_argument("--db", type=Path, default=resolve_database_path(os.getenv("BOT_DB")))
    p.add_argument("--names", help="voice_bot's manifest.json (its 'names' maps Discord id -> display name)")
    p.add_argument("--summarizer", help="simple or openai (default: $MEETING_SUMMARIZER or simple)")
    args = p.parse_args(argv)

    names = {}
    if args.names and Path(args.names).is_file():
        names = json.loads(Path(args.names).read_text(encoding="utf-8")).get("names", {})

    result = summarize_session(SQLiteStore(args.db), args.session_id, get_summarizer(args.summarizer), names)
    print(result["markdown"])
    print("RESULT " + json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
