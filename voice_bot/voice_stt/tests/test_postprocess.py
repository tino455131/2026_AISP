import pytest

from stt.postprocess import PostProcessor, make_opencc_converter
from stt.schema import Segment


def seg(text, start=0.0, end=1.0, logprob=-0.2, no_speech=0.1, compression=1.2):
    return Segment(start, end, text, logprob, no_speech, compression)


def run(segments, convert=None):
    return PostProcessor(convert).process(
        segments, session_id="s1", speaker="組長", source="a.wav"
    )


def test_keeps_normal_speech():
    utts, report = run([seg("先看這週進度", start=1.234, end=3.0)])
    assert [u.text for u in utts] == ["先看這週進度"]
    u = utts[0]
    assert u.flags == []
    assert u.speaker == "組長" and u.session_id == "s1" and u.source == "a.wav"
    assert u.start == 1.23
    assert 0.8 < u.confidence <= 1.0
    assert report.kept == 1 and report.dropped == []


def test_drops_segment_that_is_only_a_hallucination():
    utts, report = run([seg("謝謝觀看！")])
    assert utts == []
    assert report.dropped == [(0.0, "謝謝觀看！", "hallucination")]


def test_flags_segment_that_contains_a_hallucination():
    utts, _ = run([seg("好今天就到這裡 謝謝觀看")])
    assert len(utts) == 1
    assert "hallucination_suspect" in utts[0].flags


def test_drops_empty_or_punctuation_only():
    utts, report = run([seg("   "), seg("。。")])
    assert utts == []
    assert [r[2] for r in report.dropped] == ["empty", "empty"]


def test_low_confidence_flag_and_value():
    utts, _ = run([seg("那個測試呢", logprob=-1.3)])
    assert "low_confidence" in utts[0].flags
    assert utts[0].confidence == pytest.approx(0.27, abs=0.01)


def test_repetitive_flag_from_compression_ratio():
    utts, _ = run([seg("我們明天再討論", compression=2.6)])
    assert "repetitive" in utts[0].flags


def test_repetitive_flag_from_repeated_characters():
    utts, _ = run([seg("對對對對對對對")])
    assert "repetitive" in utts[0].flags


def test_short_repetition_is_normal_speech():
    utts, _ = run([seg("對對對，我明天補上")])
    assert utts[0].flags == []


def test_no_speech_flag():
    utts, _ = run([seg("嗯", no_speech=0.7)])
    assert "maybe_no_speech" in utts[0].flags


def test_opencc_converts_to_taiwan_traditional():
    pytest.importorskip("opencc")
    convert = make_opencc_converter()
    assert convert("软件") == "軟體"

    utts, report = run([seg("这个软件我明天测试"), seg("谢谢观看")], convert)
    assert utts[0].text_raw == "这个软件我明天测试"  # original kept
    assert utts[0].text == "這個軟體我明天測試"
    # Simplified version of a known hallucination is still dropped.
    assert [r[2] for r in report.dropped] == ["hallucination"]
