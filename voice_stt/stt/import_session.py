"""Command line: transcribe a recorded meeting and save it into the bot's database.

Example (run inside voice_stt; one file per person, e.g. from Craig):
    python -m stt.import_session --guild-id 111 --channel-id 222 \
        --started-at 2026-11-18T14:00:00+08:00 --started-by 333 \
        --track 333=leader.wav --track 444=member.wav
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .botdb import DEFAULT_DB, load_transcript_store
from .engine import DEFAULT_MODEL, Engine, EngineConfig
from .output import fmt_ts, write_markdown
from .postprocess import PostProcessor, make_opencc_converter
from .session import import_session, parse_track


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m stt.import_session",
        description="Transcribe one meeting (one audio file per speaker) into the bot's database.",
    )
    p.add_argument("--guild-id", type=int, required=True, help="Discord server id")
    p.add_argument("--channel-id", type=int, required=True, help="voice channel id")
    p.add_argument("--started-at", required=True, help="meeting start with time zone, e.g. 2026-11-18T14:00:00+08:00")
    p.add_argument(
        "--track",
        action="append",
        required=True,
        help="SPEAKER_ID=FILE or SPEAKER_ID=FILE@OFFSET_SECONDS; repeat once per person",
    )
    p.add_argument("--started-by", type=int, help="Discord user id who started the recording")
    p.add_argument("--session-id", help="default: rec-<channel>-<start time>")
    p.add_argument("--db", default=str(DEFAULT_DB), help="bot database (default: discord_bot/data/messages.sqlite3)")
    p.add_argument("--out-dir", default="transcripts", help="also save a readable Markdown copy here")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--compute-type", default="auto", choices=["auto", "float16", "int8_float16", "int8"])
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    try:
        tracks = [parse_track(t) for t in args.track]
        started_at = datetime.fromisoformat(args.started_at)
    except ValueError as exc:
        print(f"參數錯誤：{exc}", file=sys.stderr)
        return 2
    if started_at.tzinfo is None:
        print("--started-at 要包含時區，例如 2026-11-18T14:00:00+08:00", file=sys.stderr)
        return 2
    missing = [t.path for t in tracks if not Path(t.path).is_file()]
    if missing:
        print(f"找不到音檔：{', '.join(missing)}", file=sys.stderr)
        return 1

    session_id = args.session_id or f"rec-{args.channel_id}-{started_at:%Y%m%d-%H%M%S}"
    module = load_transcript_store()
    store = module.TranscriptStore(Path(args.db))

    print(f"載入模型 {args.model} ...")
    engine = Engine(EngineConfig(model=args.model, device=args.device, compute_type=args.compute_type))
    print(f"模型就緒：{engine.device} / {engine.compute_type}；開始辨識 {len(tracks)} 個音軌")

    result = import_session(
        engine,
        PostProcessor(make_opencc_converter()),
        store,
        module,
        tracks=tracks,
        session_id=session_id,
        guild_id=args.guild_id,
        channel_id=args.channel_id,
        started_at=started_at,
        started_by=args.started_by,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{session_id}.md"
    write_markdown(
        result.utterances,
        md_path,
        title=session_id,
        meta={"語音頻道": str(args.channel_id), "開始": args.started_at, "長度": fmt_ts(result.duration)},
    )

    dropped = sum(len(r.dropped) for r in result.dropped.values())
    print(f"完成：存了 {result.saved_lines} 句到 {args.db}（session_id = {session_id}），丟掉 {dropped} 句")
    print(f"可讀版本：{md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
