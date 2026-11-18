"""Load the speech recognizer (Breeze-ASR-25 via faster-whisper) and run it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .cuda_dlls import add_nvidia_dll_dirs
from .schema import Segment

# Breeze-ASR-25 (MediaTek Research, Apache-2.0): Whisper-large-v2 fine-tuned
# for Taiwanese Mandarin and Mandarin-English code-switching.
# This repo is a community conversion to the CTranslate2 format that
# faster-whisper needs (fp16 weights, about 3.1 GB, downloaded once).
DEFAULT_MODEL = "SoybeanMilk/faster-whisper-Breeze-ASR-25"


@dataclass
class EngineConfig:
    model: str = DEFAULT_MODEL  # Hugging Face repo id or local folder
    device: str = "auto"  # "auto" | "cuda" | "cpu"
    compute_type: str = "auto"  # "auto" | "float16" | "int8_float16" | "int8"
    language: str = "zh"
    beam_size: int = 5
    hotwords: str | None = None  # glossary words that should be recognized


class Engine:
    def __init__(self, cfg: EngineConfig):
        add_nvidia_dll_dirs()
        from faster_whisper import WhisperModel  # import after the DLL setup

        self.cfg = cfg
        self.device, self.compute_type = _pick_device(cfg.device, cfg.compute_type)
        self.model = WhisperModel(
            cfg.model, device=self.device, compute_type=self.compute_type
        )

    def transcribe(
        self,
        audio_path: str,
        on_segment: Callable[[Segment], None] | None = None,
    ) -> tuple[list[Segment], float]:
        """Return (segments, audio duration in seconds).

        `on_segment` is called as each segment finishes, e.g. to show progress.
        """
        raw_segments, info = self.model.transcribe(
            audio_path,
            language=self.cfg.language,
            task="transcribe",
            beam_size=self.cfg.beam_size,
            # Skip silence with the built-in Silero VAD (voice activity detection).
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            # Not feeding previous text back in stops one mistake from snowballing
            # into a loop of repeated / invented sentences.
            condition_on_previous_text=False,
            hotwords=self.cfg.hotwords,
        )

        segments: list[Segment] = []
        for s in raw_segments:  # the model actually runs while we iterate
            seg = Segment(
                start=s.start,
                end=s.end,
                text=s.text,
                avg_logprob=s.avg_logprob,
                no_speech_prob=s.no_speech_prob,
                compression_ratio=s.compression_ratio,
            )
            segments.append(seg)
            if on_segment:
                on_segment(seg)
        return segments, info.duration


def _pick_device(device: str, compute_type: str) -> tuple[str, str]:
    if device == "auto":
        import ctranslate2

        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    if compute_type == "auto":
        # GPU: full fp16 for best accuracy (~4.5 GB VRAM); use int8_float16 to
        # save memory. CPU: int8 is the only practical speed.
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type
