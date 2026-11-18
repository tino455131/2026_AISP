"""Save utterances as JSONL (for programs) and Markdown (for people)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .schema import Utterance


def fmt_ts(seconds: float) -> str:
    """75.4 -> "01:15", 3725 -> "1:02:05"."""
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def write_jsonl(utterances: Iterable[Utterance], path: Path) -> None:
    """One JSON object per line; Chinese is written as-is, not escaped."""
    with open(path, "w", encoding="utf-8") as f:
        for u in utterances:
            f.write(json.dumps(u.to_dict(), ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[Utterance]:
    with open(path, encoding="utf-8") as f:
        return [Utterance(**json.loads(line)) for line in f if line.strip()]


def render_markdown(
    utterances: Iterable[Utterance],
    *,
    title: str,
    meta: dict[str, str],
    names: dict[str, str] | None = None,
) -> str:
    """`names` maps a speaker id to a display name; unknown speakers keep their id."""
    names = names or {}
    lines = [f"# 逐字稿：{title}", ""]
    lines += [f"- {key}：{value}" for key, value in meta.items()]
    lines += ["- ⚠️ = 系統沒把握，請人工確認", ""]
    for u in utterances:
        warn = f" ⚠️({', '.join(u.flags)})" if u.flags else ""
        who = names.get(str(u.speaker), u.speaker)
        lines.append(f"[{fmt_ts(u.start)}] **{who}**：{u.text}{warn}  ")
    return "\n".join(lines) + "\n"


def write_markdown(
    utterances: Iterable[Utterance],
    path: Path,
    *,
    title: str,
    meta: dict[str, str],
    names: dict[str, str] | None = None,
) -> None:
    text = render_markdown(utterances, title=title, meta=meta, names=names)
    path.write_text(text, encoding="utf-8")
