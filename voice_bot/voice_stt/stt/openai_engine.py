"""OpenAITranscriber：把錄音交給 OpenAI 的語音轉文字 API。預設沒有開啟。

開啟方式（換到別台電腦、沒有 GPU 時）：
1. 安裝套件：voice_stt/.venv/Scripts/pip install openai
2. 在 voice_bot/.env 填 OPENAI_API_KEY=...（這是密碼，只能放 .env）
3. 改成 STT_ENGINE=openai，或 voice_bot 啟動時加 --stt openai

注意：
- 錄音檔會傳到 OpenAI。voice_bot 會依 STT_ENGINE 自動在錄音通知裡寫出來。
- 模型用 STT_OPENAI_MODEL 換（預設 whisper-1）。whisper-1 會回傳每一段的時間和信心分數，
  後面「可能聽錯」的判斷和清理規則用得到；只回純文字的模型就用不了這些規則。
- 一個檔案最多 25 MB（48 kHz 單聲道約 4 分半），超過會直接報錯。
"""

from __future__ import annotations

import os
from pathlib import Path

from .schema import Segment

MODEL = os.environ.get("STT_OPENAI_MODEL", "whisper-1")
MAX_BYTES = 25 * 1024 * 1024


class OpenAITranscriber:
    def __init__(self, hotwords: str | None = None, client=None, language: str = "zh") -> None:
        self.hotwords = hotwords  # sent as the prompt: names and terms the model should spell right
        self.language = language
        self._client = client  # tests pass a fake; otherwise created on first use
        self.device, self.compute_type = "openai", MODEL  # shown in logs like the local engine

    def _get_client(self):
        if self._client is None:
            try:
                import openai
            except ImportError as exc:
                raise RuntimeError("沒有安裝 openai 套件：在 voice_stt/.venv 執行 pip install openai") from exc
            if not os.environ.get("OPENAI_API_KEY", "").strip():
                raise RuntimeError("沒有 OPENAI_API_KEY：請填在 voice_bot/.env")
            self._client = openai.OpenAI()
        return self._client

    def transcribe(self, audio_path: str, on_segment=None) -> tuple[list[Segment], float]:
        size = Path(audio_path).stat().st_size
        if size > MAX_BYTES:
            raise RuntimeError(f"{Path(audio_path).name} 有 {size / 1024 / 1024:.0f} MB，超過 OpenAI 的 25 MB 上限")
        options = {"prompt": self.hotwords} if self.hotwords else {}
        with open(audio_path, "rb") as audio:
            result = self._get_client().audio.transcriptions.create(
                model=MODEL,
                file=audio,
                language=self.language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                **options,
            )
        segments = [
            Segment(
                start=float(s.start),
                end=float(s.end),
                text=s.text,
                avg_logprob=float(s.avg_logprob),
                no_speech_prob=float(s.no_speech_prob),
                compression_ratio=float(s.compression_ratio),
            )
            for s in (result.segments or [])
        ]
        for segment in segments:
            if on_segment:
                on_segment(segment)
        duration = float(getattr(result, "duration", 0) or (segments[-1].end if segments else 0))
        return segments, duration
