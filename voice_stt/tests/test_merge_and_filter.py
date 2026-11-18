import wave

from stt.cli import load_glossary
from stt.ingest_recording import GLOSSARY, merge_tracks, plan_groups
from stt.postprocess import PostProcessor
from stt.schema import Segment
from stt.session import Track

A, B = 111, 222


def seg(start, end, text, logprob):
    return Segment(start, end, text, logprob, 0.1, 1.2)


def test_short_unsure_english_is_dropped_but_real_lines_stay():
    segments = [
        seg(0.0, 0.8, "Yeah.", -0.8),  # confidence 0.45: a cough or "嗯" guessed as English
        seg(1.0, 3.0, "It comes forward.", -1.0),
        seg(3.0, 4.0, "好", -0.9),  # unsure but Chinese: kept (flagged elsewhere if needed)
        seg(4.0, 6.0, "OK, let's merge it.", -0.2),  # confident English: kept
        seg(6.0, 11.0, "We should ship the bot this week and test it again.", -0.8),  # long: kept
    ]
    kept, report = PostProcessor().process(segments, session_id="s", speaker="1")
    assert [u.text for u in kept] == [
        "好",
        "OK, let's merge it.",
        "We should ship the bot this week and test it again.",
    ]
    assert [reason for _, _, reason in report.dropped] == ["stray_non_chinese", "stray_non_chinese"]


def test_close_clips_of_one_person_are_grouped_but_not_across_someone_else():
    tracks = [
        Track(A, "a1", 0.0),
        Track(A, "a2", 2.0),  # 1 s after a1 ends: same group
        Track(B, "b1", 4.0),  # B talks between a2 and a3
        Track(A, "a3", 5.0),  # would be close, but B spoke in between: new group
        Track(A, "a4", 20.0),  # long pause: new group
    ]
    seconds = {"a1": 1.0, "a2": 1.5, "b1": 2.0, "a3": 1.0, "a4": 1.0}
    groups = plan_groups(tracks, seconds)
    assert [[t.path for t in g] for g in groups] == [["a1", "a2"], ["b1"], ["a3"], ["a4"]]


def write_wav(path, seconds, rate=16000, value=1000):
    frames = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(value.to_bytes(2, "little", signed=True) * frames)


def test_joined_audio_keeps_real_time(tmp_path):
    write_wav(tmp_path / "a1.wav", 0.5)
    write_wav(tmp_path / "a2.wav", 0.5)
    tracks = [Track(A, str(tmp_path / "a1.wav"), 10.0), Track(A, str(tmp_path / "a2.wav"), 11.0)]
    merged = merge_tracks(tracks, tmp_path / "_merged")
    assert len(merged) == 1 and merged[0].offset == 10.0
    with wave.open(merged[0].path, "rb") as w:
        assert w.getnframes() == 16000 * 1.5  # 0.5 s + 0.5 s of silence + 0.5 s
        frames = w.readframes(w.getnframes())
    middle = frames[2 * 8000 : 2 * 16000]
    assert middle == b"\0" * len(middle)  # the gap really is silent


def test_unreadable_audio_is_left_alone(tmp_path):
    (tmp_path / "x.wav").write_bytes(b"RIFF fake")
    tracks = [Track(A, str(tmp_path / "x.wav"), 0.0)]
    assert merge_tracks(tracks, tmp_path / "_merged") == tracks


def test_team_glossary_holds_the_member_names():
    assert load_glossary(str(GLOSSARY)).split() == ["皓元", "Alex", "claire"]
