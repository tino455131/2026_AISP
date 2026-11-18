from stt.output import fmt_ts, read_jsonl, render_markdown, write_jsonl
from stt.schema import Utterance


def utt(text, start, flags=None):
    return Utterance(
        session_id="s1",
        speaker="組長",
        start=start,
        end=start + 2,
        text_raw=text,
        text=text,
        confidence=0.9,
        flags=flags or [],
        source="a.wav",
    )


def test_fmt_ts():
    assert fmt_ts(0) == "00:00"
    assert fmt_ts(75.4) == "01:15"
    assert fmt_ts(3725) == "1:02:05"


def test_jsonl_roundtrip_keeps_chinese_readable(tmp_path):
    path = tmp_path / "out.jsonl"
    original = [utt("先看這週進度", 1.0), utt("那測試呢", 16.5, ["low_confidence"])]
    write_jsonl(original, path)

    assert "先看這週進度" in path.read_text(encoding="utf-8")  # not \u escaped
    assert read_jsonl(path) == original


def test_markdown_marks_flagged_lines():
    md = render_markdown(
        [utt("先看這週進度", 1.0), utt("那測試呢", 75.0, ["low_confidence"])],
        title="a.wav",
        meta={"模型": "test"},
    )
    assert "# 逐字稿：a.wav" in md
    assert "[00:01] **組長**：先看這週進度  " in md
    assert "[01:15] **組長**：那測試呢 ⚠️(low_confidence)" in md
