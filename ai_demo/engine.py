"""選 AI 來源：和摘要器同一套（meeting_ai），預設用這台電腦的 Claude Code。

    --ai claude-code（預設）| openai | 模組路徑:類別名稱
    或環境變數 AI_DEMO_ENGINE

只要有 generate(system_prompt, user_text, schema)（例如 meeting_ai.llm.LLMSummarizer 的子類別）就能用；
simple 只會找關鍵字，不能用在這裡。
"""

from __future__ import annotations

import os

from meeting_ai import get_summarizer


def get_engine(name: str | None = None):
    """--ai, then AI_DEMO_ENGINE, then the summarizer in use (unless it is simple), then claude-code."""
    summarizer = os.environ.get("MEETING_SUMMARIZER", "").strip()
    follow = summarizer if summarizer.lower() not in ("", "simple") else ""
    chosen = name or os.environ.get("AI_DEMO_ENGINE") or follow or "claude-code"
    engine = get_summarizer(chosen)
    if not callable(getattr(engine, "generate", None)):
        raise ValueError(f"{chosen} 不是語言模型，不能用在 AI 功能（請用 claude-code 或 openai）")
    return engine


def as_user_text(lines, names: dict[str, str]) -> str:
    """The meeting the way the summary prompt shows it: "[行號] 代號（名字）：內容"."""
    rows = []
    for line in lines:
        who = f"{line.speaker_label}（{names[line.speaker_label]}）" if line.speaker_label in names else line.speaker_label
        rows.append(f"[{line.line_id}] {who}：{line.text}{'（可能聽錯）' if line.uncertain else ''}")
    return "<meeting>\n" + "\n".join(rows) + "\n</meeting>"
