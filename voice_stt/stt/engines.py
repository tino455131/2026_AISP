"""選擇語音辨識（STT）引擎。預設是本機的 Breeze-ASR-25（faster-whisper），也可以換成其他來源。

    STT_ENGINE=local（預設）| openai | 模組路徑:類別名稱
    或：python -m stt.ingest_recording <資料夾> --engine openai
    或：voice_bot 啟動時加 --stt openai

每個引擎只要有 transcribe(audio_path, on_segment=None) -> (segments, 音檔秒數)
（見 session.Transcriber，segments 是 schema.Segment），後面的清理、合併、存資料庫都不用改。
自訂引擎的類別要能用 MyEngine(hotwords=...) 建立（hotwords 是詞彙表，可以不理它）。
"""

from __future__ import annotations

import importlib
import os

from .session import Transcriber

BUILT_IN = ("local", "openai")


def engine_name(name: str | None = None) -> str:
    return (name or os.environ.get("STT_ENGINE") or "local").strip()


def make_transcriber(name: str | None = None, hotwords: str | None = None) -> Transcriber:
    """Build the chosen engine. Heavy model code is imported only for the engine actually used."""
    chosen = engine_name(name)
    if ":" in chosen:
        module_name, _, class_name = chosen.partition(":")
        try:
            cls = getattr(importlib.import_module(module_name.strip()), class_name.strip())
        except (ImportError, AttributeError, ValueError) as exc:
            raise ValueError(f"載入不了語音辨識引擎 {chosen!r}：{exc}") from exc
        return cls(hotwords=hotwords)
    kind = chosen.lower()
    if kind == "local":
        from .engine import Engine, EngineConfig

        return Engine(EngineConfig(hotwords=hotwords))
    if kind == "openai":
        from .openai_engine import OpenAITranscriber

        return OpenAITranscriber(hotwords=hotwords)
    raise ValueError(f"不認得的語音辨識引擎 {chosen!r}：請用 local、openai，或「模組路徑:類別名稱」")
