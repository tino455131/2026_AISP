"""Choosing the speech-to-text engine. The OpenAI engine is tested with a fake client: nothing is sent."""

from types import SimpleNamespace

import pytest

from stt.engines import engine_name, make_transcriber
from stt.openai_engine import OpenAITranscriber
from stt.schema import Segment


class FakeEngine:
    def __init__(self, hotwords=None):
        self.hotwords = hotwords

    def transcribe(self, audio_path, on_segment=None):
        return [], 0.0


class FakeOpenAI:
    def __init__(self):
        self.calls = []
        self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({k: v for k, v in kwargs.items() if k != "file"})
        segment = SimpleNamespace(start=0.0, end=1.5, text="大家好", avg_logprob=-0.2, no_speech_prob=0.01, compression_ratio=1.1)
        return SimpleNamespace(segments=[segment], duration=1.5)


def test_engine_comes_from_argument_then_env_then_default(monkeypatch):
    monkeypatch.delenv("STT_ENGINE", raising=False)
    assert engine_name() == "local"
    monkeypatch.setenv("STT_ENGINE", "openai")
    assert engine_name() == "openai"
    assert engine_name("tests.test_engines:FakeEngine") == "tests.test_engines:FakeEngine"


def test_any_engine_can_be_plugged_in_by_module_path():
    engine = make_transcriber("tests.test_engines:FakeEngine", hotwords="皓元")
    # pytest loads this file under another module name, so compare by class name
    assert type(engine).__name__ == "FakeEngine" and engine.hotwords == "皓元"
    with pytest.raises(ValueError, match="不認得"):
        make_transcriber("whatever")


def test_openai_engine_returns_segments_like_the_local_one(tmp_path):
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF" + bytes(100))
    fake = FakeOpenAI()
    seen = []
    segments, duration = OpenAITranscriber(hotwords="Breeze 皓元", client=fake).transcribe(str(audio), seen.append)

    assert segments == [Segment(0.0, 1.5, "大家好", -0.2, 0.01, 1.1)] and seen == segments
    assert duration == 1.5
    call = fake.calls[0]
    assert call["response_format"] == "verbose_json" and call["language"] == "zh"
    assert call["prompt"] == "Breeze 皓元"  # glossary words help the model spell names


def test_openai_engine_refuses_files_over_the_limit(tmp_path, monkeypatch):
    import stt.openai_engine as module

    monkeypatch.setattr(module, "MAX_BYTES", 10)
    audio = tmp_path / "big.wav"
    audio.write_bytes(bytes(11))
    with pytest.raises(RuntimeError, match="25 MB"):
        OpenAITranscriber(client=FakeOpenAI()).transcribe(str(audio))


def test_openai_engine_is_picked_by_name_without_loading_anything():
    assert isinstance(make_transcriber("openai"), OpenAITranscriber)
