"""給 AI 組的介面：把一場會議的逐字稿整理成摘要（meeting summary）。

流程：voice_bot 錄音 → voice_stt 轉成逐字稿存進資料庫 → 這裡的摘要器整理重點 →
voice_bot 把摘要貼回語音頻道的聊天室，並存進 voice_session_summaries。

任何摘要器只要符合 MeetingSummarizer（有 name、prompt_version、summarize()）就能替換。
目前內建兩個：
- "simple"：關鍵字規則，不用 API，給測試用（SimpleSummarizer）
- "claude"：呼叫 Claude API（ClaudeSummarizer，需要 ANTHROPIC_API_KEY）
用環境變數 MEETING_SUMMARIZER 選擇，預設 simple。AI 組（Alex、claire）之後可以寫自己的版本換掉。
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Mapping, Protocol, Sequence


@dataclass(frozen=True)
class MeetingLine:
    """One sentence of the transcript, as a summarizer sees it."""

    line_id: int  # voice_lines.line_id: cite this as the source
    speaker: str  # short label such as "S1"; names are in the `speakers` mapping
    started_at: str  # ISO 8601, UTC
    text: str
    uncertain: bool = False  # flagged or low confidence: may be misheard


@dataclass(frozen=True)
class Decision:
    text: str
    source_line_ids: tuple[int, ...]


@dataclass(frozen=True)
class ActionItem:
    task: str
    owner: str  # a speaker label ("S1"), a name said in the meeting, or "" if unclear
    due: str  # as said ("週五前"), or "" if none was said
    source_line_ids: tuple[int, ...]


@dataclass(frozen=True)
class MeetingSummary:
    summary: str
    decisions: tuple[Decision, ...] = ()
    action_items: tuple[ActionItem, ...] = ()

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict, valid_ids: set[int] | None = None) -> "MeetingSummary":
        """Build from plain JSON; source ids not in `valid_ids` are dropped (no invented sources)."""

        def ids(values) -> tuple[int, ...]:
            out = tuple(int(v) for v in values or [])
            return tuple(v for v in out if valid_ids is None or v in valid_ids)

        return cls(
            summary=str(data.get("summary", "")).strip(),
            decisions=tuple(
                Decision(str(d.get("text", "")).strip(), ids(d.get("source_line_ids")))
                for d in data.get("decisions", [])
                if str(d.get("text", "")).strip()
            ),
            action_items=tuple(
                ActionItem(
                    str(a.get("task", "")).strip(),
                    str(a.get("owner", "")).strip(),
                    str(a.get("due", "")).strip(),
                    ids(a.get("source_line_ids")),
                )
                for a in data.get("action_items", [])
                if str(a.get("task", "")).strip()
            ),
        )


class MeetingSummarizer(Protocol):
    name: str  # stored as `model` with the summary
    prompt_version: str  # bump when the prompt/rules change, so old summaries can be redone

    def summarize(self, lines: Sequence[MeetingLine], speakers: Mapping[str, str]) -> MeetingSummary:
        """`speakers` maps a label ("S1") to a display name ("組長"), when known."""
        ...


class SummaryError(RuntimeError):
    """The summarizer could not produce a summary (e.g. the model refused)."""


def get_summarizer(kind: str | None = None) -> MeetingSummarizer:
    kind = (kind or os.environ.get("MEETING_SUMMARIZER") or "simple").strip().lower()
    if kind == "simple":
        from .simple import SimpleSummarizer

        return SimpleSummarizer()
    if kind == "claude":
        from .claude import ClaudeSummarizer

        return ClaudeSummarizer()
    raise ValueError(f"不認得的摘要器 {kind!r}：請用 simple 或 claude")


def render_markdown(summary: MeetingSummary, owner_display: Mapping[str, str]) -> str:
    """Discord-ready text. `owner_display` turns labels into mentions, e.g. "S1" -> "<@123>"."""
    show = lambda owner: owner_display.get(owner, owner) if owner else "（未指定）"  # noqa: E731
    parts = ["**📝 會議摘要**", summary.summary or "（沒有內容）"]
    if summary.decisions:
        parts.append("**決定**")
        parts += [f"- {d.text}" for d in summary.decisions]
    if summary.action_items:
        parts.append("**待辦**")
        parts += [
            f"- {show(a.owner)}：{a.task}" + (f"（{a.due}）" if a.due else "") for a in summary.action_items
        ]
    return "\n".join(parts)
