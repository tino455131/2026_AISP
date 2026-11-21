import json

from sqlite_api import SQLiteStore
from stt.ingest_recording import ingest, tracks_from_manifest
from stt.postprocess import PostProcessor
from stt.schema import Segment

LEADER = "123456789012345678"  # Discord ids are strings in voice_bot's JSON
MEMBER = "223456789012345678"
REFUSED = "323456789012345678"


class FakeEngine:
    def transcribe(self, audio_path, on_segment=None):
        text = {"0": "先看進度", "4500": "我做完了", "9000": "這句不該出現"}[audio_path.split("\\")[-1].split("/")[-1][:-4]]
        return [Segment(0.1, 1.5, text, -0.2, 0.1, 1.2)], 1.6


def make_session(tmp_path, *, member_status="agreed"):
    session_dir = tmp_path / "rec-301-20261118-140000"
    clips = [(LEADER, 0), (MEMBER, 4500), (REFUSED, 9000)]
    for user, ms in clips:
        (session_dir / user).mkdir(parents=True, exist_ok=True)
        (session_dir / user / f"{ms}.wav").write_bytes(b"RIFF fake")
    manifest = {
        "session_id": "rec-301-20261118-140000",
        "guild_id": "10",
        "channel_id": "301",
        "started_by": LEADER,
        "started_at": "2026-11-18T06:00:00.000Z",
        "ended_at": "2026-11-18T06:10:00.000Z",
        "consent": {
            LEADER: {"status": "agreed", "at": "2026-11-18T06:00:01.000Z"},
            MEMBER: {"status": member_status, "at": "2026-11-18T06:00:02.000Z"},
            REFUSED: {"status": "withdrawn", "at": "2026-11-18T06:05:00.000Z"},
        },
        "clips": [{"user_id": u, "file": f"{u}/{ms}.wav", "offset": ms / 1000, "duration": 1.6} for u, ms in clips],
    }
    (session_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return session_dir


def test_only_people_who_still_agree_are_transcribed(tmp_path):
    session_dir = make_session(tmp_path, member_status="withdrawn")
    tracks = tracks_from_manifest(json.loads((session_dir / "manifest.json").read_text()), session_dir)
    assert [t.speaker_id for t in tracks] == [int(LEADER)]


def test_ingest_saves_lines_writes_markdown_and_deletes_audio(tmp_path):
    session_dir = make_session(tmp_path)
    store = SQLiteStore(tmp_path / "messages.sqlite3")

    result = ingest(session_dir, FakeEngine(), PostProcessor(), store)

    assert result == {"session_id": "rec-301-20261118-140000", "saved_lines": 2, "clips": 2, "pieces": 2, "dropped": 0}
    lines = store.list_transcript_lines("rec-301-20261118-140000")
    assert [(l.speaker_id, l.text, l.started_at) for l in lines] == [
        (int(LEADER), "先看進度", "2026-11-18T06:00:00.100000+00:00"),
        (int(MEMBER), "我做完了", "2026-11-18T06:00:04.600000+00:00"),
    ]
    assert store.get_voice_session("rec-301-20261118-140000").ended_at == "2026-11-18T06:10:00+00:00"
    assert (session_dir / "transcript.md").is_file()
    assert not (session_dir / LEADER / "0.wav").exists()  # transcribed audio deleted
    assert not (session_dir / REFUSED / "9000.wav").exists()  # never transcribed, still deleted
