"""Data shapes used by the speech-to-text (STT) pipeline.

DRAFT: the `Utterance` fields still need to be agreed with 皓元 (database)
and MT-Alex / claire (AI side) before transcripts are written to the DB.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Segment:
    """One piece of speech exactly as the recognizer returned it."""

    start: float  # seconds from the beginning of the audio file
    end: float
    text: str
    avg_logprob: float  # how sure the model was; closer to 0 = more sure
    no_speech_prob: float  # model's guess that this part is not speech at all
    compression_ratio: float  # high value = text repeats itself a lot


@dataclass
class Utterance:
    """One cleaned-up sentence, ready to be saved or shown to people."""

    session_id: str  # which recording / meeting this belongs to
    speaker: str  # who said it (one audio track = one speaker)
    start: float  # seconds from the beginning of the recording
    end: float
    text_raw: str  # recognizer output, untouched (kept for debugging)
    text: str  # cleaned text in Taiwan Traditional Chinese
    confidence: float  # 0-1, derived from avg_logprob
    flags: list[str] = field(default_factory=list)  # warnings for humans
    source: str = ""  # audio file name

    def to_dict(self) -> dict:
        return asdict(self)
