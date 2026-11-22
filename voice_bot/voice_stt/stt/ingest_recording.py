"""Transcribe a recording folder made by voice_bot and save it into the bot's database.

voice_bot runs this after /record stop:
    python -m stt.ingest_recording <recordings/rec-...> --db <data/messages.sqlite3>

The folder holds manifest.json and one WAV per thing a consenting person said.
One person's clips that follow each other closely are joined before transcribing:
a 1-2 second clip alone gives the model no context and comes out badly.
On success it prints one line "RESULT {json}" for voice_bot, and deletes the
audio (the transcript is kept in the database; the audio is not needed).
"""

from __future__ import annotations

import argparse
import json
import shutil
import os
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from sqlite_api import PROJECT_ROOT, SQLiteStore, resolve_database_path
from .output import write_markdown
from .postprocess import PostProcessor
from .session import Track, Transcriber, import_session


def load_manifest(session_dir: Path) -> dict:
    return json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))


def tracks_from_manifest(manifest: dict, session_dir: Path) -> list[Track]:
    """One Track per clip, only for people whose consent is still "agreed"."""
    consent = manifest.get("consent", {})
    tracks = []
    for clip in manifest.get("clips", []):
        user_id = str(clip["user_id"])
        if consent.get(user_id, {}).get("status") != "agreed":
            continue  # withdrew or never agreed: never transcribe
        path = session_dir / clip["file"]
        if path.is_file():
            tracks.append(Track(int(user_id), str(path), float(clip["offset"])))
    return tracks


# Join one person's clips when the next starts within this many seconds of the last one
# ending and nobody else talked in between (so lines stay in speaking order), up to a
# piece of this length. Real test: one 48 s piece gave ~9% wrong characters; 1-2 s clips
# came out mostly wrong.
MERGE_GAP_SECONDS = 3.0
MAX_MERGED_SECONDS = 60.0
GLOSSARY = Path(__file__).resolve().parents[1] / "glossary.txt"


def _wav_seconds(path: str) -> tuple[tuple, float] | None:
    """(format, duration) of a WAV file, or None if it can't be read as one."""
    try:
        with wave.open(path, "rb") as w:
            fmt = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            return fmt, w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, OSError):
        return None


def plan_groups(tracks: list[Track], seconds: dict[str, float]) -> list[list[Track]]:
    """Group each person's clips that follow closely, never across someone else's talk."""
    ordered = sorted(tracks, key=lambda t: t.offset)
    end = {t.path: t.offset + seconds[t.path] for t in ordered}
    groups: list[list[Track]] = []
    open_group: dict[int, list[Track]] = {}
    for track in ordered:
        group = open_group.get(track.speaker_id)
        if group:
            last_end = end[group[-1].path]
            others_talked = any(
                o.speaker_id != track.speaker_id and o.offset < track.offset and end[o.path] > last_end
                for o in ordered
            )
            if (
                track.offset - last_end <= MERGE_GAP_SECONDS
                and end[track.path] - group[0].offset <= MAX_MERGED_SECONDS
                and not others_talked
            ):
                group.append(track)
                continue
        group = [track]
        groups.append(group)
        open_group[track.speaker_id] = group
    return groups


def _join_wavs(group: list[Track], out: Path) -> None:
    """Write the clips one after another, with silence for the real gaps between them."""
    with wave.open(group[0].path, "rb") as w:
        params = w.getparams()
    frame_bytes = params.nchannels * params.sampwidth
    with wave.open(str(out), "wb") as joined:
        joined.setparams(params)
        written = 0
        for track in group:
            start = round((track.offset - group[0].offset) * params.framerate)
            if start > written:
                joined.writeframes(b"\0" * ((start - written) * frame_bytes))
                written = start
            with wave.open(track.path, "rb") as w:
                frames = w.readframes(w.getnframes())
            joined.writeframes(frames)
            written += len(frames) // frame_bytes


def merge_tracks(tracks: list[Track], work_dir: Path) -> list[Track]:
    """Join close clips into longer pieces in `work_dir`. Unreadable WAVs: no joining."""
    info = {t.path: _wav_seconds(t.path) for t in tracks}
    if not tracks or any(v is None for v in info.values()):
        return tracks
    groups = plan_groups(tracks, {path: v[1] for path, v in info.items()})
    work_dir.mkdir(exist_ok=True)
    merged = []
    for group in groups:
        if len(group) == 1 or len({info[t.path][0] for t in group}) > 1:
            merged.extend(group)  # alone, or clips in different formats
            continue
        out = work_dir / f"{group[0].speaker_id}-{round(group[0].offset * 1000)}.wav"
        _join_wavs(group, out)
        merged.append(Track(group[0].speaker_id, str(out), group[0].offset))
    return merged


def _parse_time(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def ingest(
    session_dir: Path,
    engine: Transcriber,
    post: PostProcessor,
    store,
    *,
    keep_audio: bool = False,
) -> dict:
    manifest = load_manifest(session_dir)
    tracks = tracks_from_manifest(manifest, session_dir)
    session_id = manifest["session_id"]
    started_at = _parse_time(manifest["started_at"])

    work_dir = session_dir / "_merged"
    try:
        pieces = merge_tracks(tracks, work_dir)
        result = import_session(
            engine,
            post,
            store,
            tracks=pieces,
            session_id=session_id,
            guild_id=int(manifest["guild_id"]),
            channel_id=int(manifest["channel_id"]),
            started_at=started_at,
            started_by=int(manifest["started_by"]) if manifest.get("started_by") else None,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    if manifest.get("ended_at"):
        ended = _parse_time(manifest["ended_at"]).astimezone(timezone.utc).isoformat()
        store.end_voice_session(session_id, ended)

    write_markdown(
        result.utterances,
        session_dir / "transcript.md",
        title=session_id,
        meta={"語音頻道": str(manifest["channel_id"]), "開始": manifest["started_at"], "片段數": str(len(tracks))},
        names=manifest.get("names", {}),
    )
    # Audio of people who did not (or no longer) agree is always removed;
    # transcribed audio too, unless asked to keep it.
    consent = manifest.get("consent", {})
    for clip in manifest.get("clips", []):
        agreed = consent.get(str(clip["user_id"]), {}).get("status") == "agreed"
        if not agreed or not keep_audio:
            (session_dir / clip["file"]).unlink(missing_ok=True)

    return {
        "session_id": session_id,
        "saved_lines": result.saved_lines,
        "clips": len(tracks),
        "pieces": len(pieces),
        "dropped": sum(len(r.dropped) for r in result.dropped.values()),
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", interpolate=False)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="python -m stt.ingest_recording", description=__doc__.splitlines()[0])
    p.add_argument("session_dir", help="a folder voice_bot wrote (with manifest.json)")
    p.add_argument("--db", type=Path, default=resolve_database_path(os.getenv("BOT_DB")))
    p.add_argument("--keep-audio", action="store_true", help="keep the WAV clips after transcribing")
    p.add_argument(
        "--glossary",
        default=str(GLOSSARY) if GLOSSARY.is_file() else None,
        help="word list that helps the model (default: voice_bot/voice_stt/glossary.txt)",
    )
    p.add_argument("--engine", help="local (default), openai, or module:Class; default: $STT_ENGINE")
    args = p.parse_args(argv)

    session_dir = Path(args.session_dir)
    if not (session_dir / "manifest.json").is_file():
        print(f"找不到 {session_dir / 'manifest.json'}", file=sys.stderr)
        return 1

    # Import the heavy model code only when actually transcribing.
    from .cli import load_glossary
    from .engines import make_transcriber
    from .postprocess import make_opencc_converter

    summary = ingest(
        session_dir,
        make_transcriber(args.engine, hotwords=load_glossary(args.glossary)),
        PostProcessor(make_opencc_converter()),
        SQLiteStore(args.db),
        keep_audio=args.keep_audio,
    )
    print(
        f"完成：{summary['clips']} 段（合併成 {summary['pieces']} 段辨識）→ "
        f"存了 {summary['saved_lines']} 句，丟掉 {summary['dropped']} 句"
    )
    print("RESULT " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
