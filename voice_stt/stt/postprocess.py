"""Turn raw recognizer segments into clean utterances.

For every segment we:
1. convert the text to Taiwan Traditional Chinese (OpenCC "s2twp"),
2. drop it if it is only a known hallucination or is empty,
3. compute a 0-1 confidence and attach warning flags for humans to check.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .schema import Segment, Utterance

# Whisper-family models sometimes "hear" these phrases in silence or noise,
# because they appeared a lot in the subtitle data the model learned from.
# A segment that is ONLY one of these is dropped; one that merely CONTAINS one
# is kept but flagged.
HALLUCINATION_PHRASES = (
    "謝謝觀看",
    "感謝觀看",
    "謝謝收看",
    "感謝收看",
    "謝謝大家觀看",
    "請不吝點贊訂閱轉發打賞支持明鏡與點點欄目",
    "請訂閱我的頻道",
    "歡迎訂閱",
    "點贊訂閱",
    "字幕由Amara.org社群提供",
    "字幕由Amara.org社區提供",
    "中文字幕志願者",
    "優優獨播劇場",
)

# Same thresholds OpenAI Whisper uses internally to decide a result is unreliable.
LOW_LOGPROB = -1.0
HIGH_COMPRESSION = 2.4
NO_SPEECH = 0.6

# The same 1-4 characters repeated 5+ times in a row, e.g. "對對對對對對".
# (Three or four "對" is normal speech, so we only flag longer runs.)
_REPEAT_RE = re.compile(r"(.{1,4})\1{4,}")
# Anything that is not a letter/digit/CJK character (punctuation, spaces).
_NON_WORD_RE = re.compile(r"[\W_]+")


def _normalize(text: str) -> str:
    """Remove punctuation/spaces and lowercase, for loose comparisons."""
    return _NON_WORD_RE.sub("", text).lower()


def make_opencc_converter(config: str = "s2twp") -> Callable[[str], str]:
    """Return a function that converts text to Taiwan Traditional Chinese.

    "s2twp" = Simplified -> Traditional (Taiwan standard) + Taiwan phrases,
    e.g. 软件 -> 軟體. Text that is already Traditional stays mostly unchanged.
    """
    import opencc

    try:
        converter = opencc.OpenCC(config)
    except Exception:  # some OpenCC builds want the ".json" suffix
        converter = opencc.OpenCC(f"{config}.json")
    return converter.convert


@dataclass
class CleanupReport:
    """What the post-processor removed, so a human can double-check."""

    kept: int = 0
    dropped: list[tuple[float, str, str]] = field(default_factory=list)
    # each dropped item = (start seconds, original text, reason)


class PostProcessor:
    def __init__(self, convert: Callable[[str], str] | None = None):
        # `convert` is the OpenCC function; None means "keep text as is".
        self.convert = convert or (lambda text: text)
        # Run the blacklist through the same converter so Simplified and
        # Traditional variants of a phrase both match.
        self._blacklist = {_normalize(self.convert(p)) for p in HALLUCINATION_PHRASES}

    def process(
        self,
        segments: Iterable[Segment],
        *,
        session_id: str,
        speaker: str,
        source: str = "",
    ) -> tuple[list[Utterance], CleanupReport]:
        utterances: list[Utterance] = []
        report = CleanupReport()

        for seg in segments:
            text_raw = seg.text.strip()
            text = self.convert(text_raw).strip()
            key = _normalize(text)

            if not key:
                report.dropped.append((seg.start, text_raw, "empty"))
                continue
            if key in self._blacklist:
                report.dropped.append((seg.start, text_raw, "hallucination"))
                continue

            utterances.append(
                Utterance(
                    session_id=session_id,
                    speaker=speaker,
                    start=round(seg.start, 2),
                    end=round(seg.end, 2),
                    text_raw=text_raw,
                    text=text,
                    confidence=_confidence(seg.avg_logprob),
                    flags=self._flags(seg, key),
                    source=source,
                )
            )

        report.kept = len(utterances)
        return utterances, report

    def _flags(self, seg: Segment, key: str) -> list[str]:
        flags = []
        if seg.avg_logprob < LOW_LOGPROB:
            flags.append("low_confidence")
        if seg.compression_ratio > HIGH_COMPRESSION or _REPEAT_RE.search(key):
            flags.append("repetitive")
        if seg.no_speech_prob > NO_SPEECH:
            flags.append("maybe_no_speech")
        if any(phrase in key for phrase in self._blacklist):
            flags.append("hallucination_suspect")
        return flags


def _confidence(avg_logprob: float) -> float:
    """exp(average log-probability) = the model's average per-token certainty."""
    return round(min(1.0, max(0.0, math.exp(avg_logprob))), 2)
