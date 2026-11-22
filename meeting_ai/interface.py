"""給 AI 組的介面：把一場會議的逐字稿整理成摘要（meeting summary）。

流程：voice_bot 錄音 → voice_stt 轉成逐字稿存進資料庫 → 這裡的摘要器整理重點 →
voice_bot 把摘要貼回語音頻道的聊天室，並存進 voice_session_summaries。

任何摘要器只要符合 MeetingSummarizer（有 name、prompt_version、summarize()）就能替換。
目前內建三個：
- "simple"：關鍵字規則，不用 API，給測試用（SimpleSummarizer）
- "claude-code"：交給主機上已登入的 Claude Code（ClaudeCodeSummarizer，用該帳號的訂閱額度，測試用）
- "openai"：呼叫 OpenAI API（OpenAISummarizer，需要 OPENAI_API_KEY）
用環境變數 MEETING_SUMMARIZER 選擇，預設 simple。

換成其他來源（別的模型、AI 組自己的做法）不用改這裡：
- 只想換模型：繼承 llm.LLMSummarizer、實作 generate()，提示詞與格式沿用（見 llm.py）
- 整套自己做：任何有 name、prompt_version、summarize() 的類別都可以
然後設定 MEETING_SUMMARIZER=模組路徑:類別名稱。
"""

from __future__ import annotations

import importlib
import json
import os
import re
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
    """By name (simple, claude-code, openai), or "module.path:ClassName" for any other source."""
    raw = (kind or os.environ.get("MEETING_SUMMARIZER") or "simple").strip()
    if ":" in raw:
        return _load_summarizer(raw)
    kind = raw.lower()
    if kind == "simple":
        from .simple import SimpleSummarizer

        return SimpleSummarizer()
    if kind == "claude-code":
        from .claude_code import ClaudeCodeSummarizer

        return ClaudeCodeSummarizer()
    if kind == "openai":
        from .openai import OpenAISummarizer

        return OpenAISummarizer()
    if kind == "claude":
        raise ValueError("MEETING_SUMMARIZER=claude 已移除：請改用 openai 並設定 OPENAI_API_KEY")
    raise ValueError(f"不認得的摘要器 {kind!r}：請用 simple、claude-code、openai，或「模組路徑:類別名稱」")


def _load_summarizer(spec: str) -> MeetingSummarizer:
    """MEETING_SUMMARIZER=my_pkg.my_module:MySummarizer -> MySummarizer(); module paths are
    relative to the repo root (where summarize_session runs). No file in meeting_ai has to change."""
    module_name, _, class_name = spec.partition(":")
    try:
        cls = getattr(importlib.import_module(module_name.strip()), class_name.strip())
    except (ImportError, AttributeError, ValueError) as exc:
        raise ValueError(f"載入不了摘要器 {spec!r}：{exc}") from exc
    summarizer = cls()
    if not callable(getattr(summarizer, "summarize", None)):
        raise ValueError(f"{spec!r} 沒有 summarize()，不是摘要器")
    return summarizer


def render_markdown(summary: MeetingSummary, owner_display: Mapping[str, str]) -> str:
    """Discord-ready text. `owner_display` turns labels into mentions, e.g. "S1" -> "<@123>"."""
    # Every label inside the owner is replaced, so "S1、S2" (two people) shows two names too.
    labels = sorted(owner_display, key=len, reverse=True)
    pattern = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(map(re.escape, labels)) + r")(?![0-9])") if labels else None

    def show(owner: str) -> str:
        if not owner:
            return "（未指定）"
        return pattern.sub(lambda m: owner_display[m[1]], owner) if pattern else owner

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
