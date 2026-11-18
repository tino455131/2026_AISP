"""Turn one recorded meeting (one audio track per person) into database rows.

Discord gives the bot every speaker's audio separately, and recorders such as
Craig save one file per person. So "who said it" never has to be guessed:
each track is transcribed on its own, then all sentences are merged by time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .postprocess import CleanupReport, PostProcessor
from .schema import Segment, Utterance


@dataclass(frozen=True)
class Track:
    speaker_id: int  # Discord user id of the person in this audio file
    path: str
    offset: float = 0.0  # seconds this file starts after the meeting start


class Transcriber(Protocol):
    def transcribe(self, audio_path: str, on_segment=None) -> tuple[list[Segment], float]: ...


@dataclass
class ImportResult:
    session_id: str
    saved_lines: int
    duration: float  # seconds, the longest track
    utterances: list[Utterance] = field(default_factory=list)  # merged, for a readable copy
    dropped: dict[int, CleanupReport] = field(default_factory=dict)  # per speaker


def parse_track(text: str) -> Track:
    """"123=leader.wav" or "123=leader.wav@2.5" (start 2.5 s late) -> Track."""
    speaker, sep, rest = text.partition("=")
    if not sep or not speaker.strip().isdecimal() or not rest:
        raise ValueError(f"track must look like SPEAKER_ID=FILE[@OFFSET], got {text!r}")
    path, at, offset = rest.rpartition("@") if "@" in rest else (rest, "", "0")
    return Track(int(speaker), path, float(offset))


def to_iso(start: datetime, seconds: float) -> str:
    """Meeting start + seconds -> UTC ISO text, the format messages.created_at uses."""
    return (start + timedelta(seconds=seconds)).astimezone(timezone.utc).isoformat()


def transcribe_tracks(
    engine: Transcriber,
    post: PostProcessor,
    tracks: list[Track],
    session_id: str,
) -> tuple[list[tuple[Track, Utterance]], float, dict[int, CleanupReport]]:
    """Transcribe each track; return sentences merged by time (offsets applied)."""
    merged: list[tuple[Track, Utterance]] = []
    reports: dict[int, CleanupReport] = {}
    duration = 0.0
    for track in tracks:
        segments, track_duration = engine.transcribe(track.path)
        duration = max(duration, track.offset + track_duration)
        utterances, reports[track.speaker_id] = post.process(
            segments, session_id=session_id, speaker=str(track.speaker_id), source=track.path
        )
        for u in utterances:
            u.start = round(u.start + track.offset, 2)
            u.end = round(u.end + track.offset, 2)
            merged.append((track, u))
    merged.sort(key=lambda item: (item[1].start, item[0].speaker_id))
    return merged, duration, reports


def import_session(
    engine: Transcriber,
    post: PostProcessor,
    store,  # discord_bot TranscriptStore
    store_module,  # the loaded transcript_store module (for NewLine)
    *,
    tracks: list[Track],
    session_id: str,
    guild_id: int,
    channel_id: int,
    started_at: datetime,
    started_by: int | None = None,
) -> ImportResult:
    if started_at.tzinfo is None:
        raise ValueError("started_at needs a time zone, e.g. 2026-11-18T14:00:00+08:00")

    merged, duration, reports = transcribe_tracks(engine, post, tracks, session_id)

    store.start_session(session_id, guild_id, channel_id, to_iso(started_at, 0), started_by)
    saved = store.add_lines(
        session_id,
        [
            store_module.NewLine(
                speaker_id=track.speaker_id,
                started_at=to_iso(started_at, u.start),
                ended_at=to_iso(started_at, u.end),
                text=u.text,
                text_raw=u.text_raw,
                confidence=u.confidence,
                flags=tuple(u.flags),
            )
            for track, u in merged
        ],
    )
    store.end_session(session_id, to_iso(started_at, duration))
    return ImportResult(session_id, saved, duration, [u for _, u in merged], reports)
