from datetime import datetime

import pytest

from sqlite_api import SQLiteStore
from stt.postprocess import PostProcessor
from stt.schema import Segment
from stt.session import Track, import_session, parse_track, to_iso


def seg(start, text, logprob=-0.2):
    return Segment(start, start + 2.0, text, logprob, 0.1, 1.2)


class FakeEngine:
    """Returns fixed segments per file instead of running the real model."""

    def __init__(self, by_path):
        self.by_path = by_path

    def transcribe(self, audio_path, on_segment=None):
        segments, duration = self.by_path[audio_path]
        return segments, duration


def test_parse_track():
    assert parse_track("123=leader.wav") == Track(123, "leader.wav", 0.0)
    assert parse_track("456=C:/rec/member.flac@2.5") == Track(456, "C:/rec/member.flac", 2.5)
    with pytest.raises(ValueError):
        parse_track("leader.wav")
    with pytest.raises(ValueError):
        parse_track("abc=leader.wav")


def test_to_iso_converts_to_utc_like_discord_timestamps():
    start = datetime.fromisoformat("2026-11-18T14:00:00+08:00")
    assert to_iso(start, 1.5) == "2026-11-18T06:00:01.500000+00:00"


def test_import_session_merges_tracks_by_time_into_the_bot_database(tmp_path):
    store = SQLiteStore(tmp_path / "messages.sqlite3")
    engine = FakeEngine(
        {
            "leader.wav": ([seg(1.0, "先看這週進度"), seg(16.0, "那測試呢？", logprob=-1.4)], 30.0),
            # member's file started 2 s late, so 6.0 in the file = 8.0 in the meeting
            "member.wav": ([seg(6.0, "API 我做完了"), seg(20.0, "謝謝觀看")], 25.0),
        }
    )

    result = import_session(
        engine,
        PostProcessor(),
        store,
        tracks=[Track(111, "leader.wav"), Track(222, "member.wav", offset=2.0)],
        session_id="rec-1",
        guild_id=10,
        channel_id=301,
        started_at=datetime.fromisoformat("2026-11-18T14:00:00+08:00"),
        started_by=111,
    )

    assert result.saved_lines == 3  # "謝謝觀看" is a known hallucination and is dropped
    assert result.dropped[222].dropped[0][2] == "hallucination"
    assert result.duration == 30.0

    lines = store.list_transcript_lines("rec-1")
    assert [(line.speaker_id, line.text) for line in lines] == [
        (111, "先看這週進度"),
        (222, "API 我做完了"),
        (111, "那測試呢？"),
    ]
    assert lines[1].started_at == "2026-11-18T06:00:08+00:00"
    assert lines[2].flags == ("low_confidence",)

    session = store.get_voice_session("rec-1")
    assert (session.guild_id, session.channel_id, session.started_by) == (10, 301, 111)
    assert session.ended_at == "2026-11-18T06:00:30+00:00"


def test_import_session_needs_a_time_zone(tmp_path):
    store = SQLiteStore(tmp_path / "messages.sqlite3")
    with pytest.raises(ValueError):
        import_session(
            FakeEngine({}),
            PostProcessor(),
            store,
            tracks=[],
            session_id="x",
            guild_id=10,
            channel_id=301,
            started_at=datetime(2026, 11, 18, 14, 0),
        )
