"""【測試用】用 Demo_Script.md 產生一個假的 bot 資料庫，讓 AI 組在自己電腦上測試。

在 repo 根目錄執行：

    discord_bot/.venv/Scripts/python.exe demo_data/make_demo_db.py

產生的東西都在 demo_data/out/（不會進 git）：

- messages.sqlite3：和真的 bot 資料庫同一套表（建表的就是真的程式）
  - 語音錄音 rec-demo-voice（語音頻道 20）：逐字稿和摘要
  - 文字會議 mtg-30-3000（文字頻道 30）：訊息在 messages 表，會議紀錄在 text_meetings 表
- recordings/rec-demo-voice/manifest.json：語音的顯示名稱（真的 bot 也存在這裡）
- text_meeting_messages.json：文字會議的原文，格式和 bot 當場向 Discord 讀到的一樣

全部是假資料：伺服器、頻道、人的 ID 都是編的，名字是 A～E，A 是組長。
摘要用 simple（不呼叫 AI）。對話最後另外加一句組長的明確指派，用來試「正式任務」。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "discord_bot")]

from message_store import MessageStore  # noqa: E402
from transcript_store import NewLine, TranscriptStore  # noqa: E402

from meeting_ai import get_summarizer  # noqa: E402
from meeting_ai.summarize_session import summarize_session  # noqa: E402
from meeting_ai.summarize_text_meeting import summarize_text_meeting  # noqa: E402
from meeting_ai.text_meeting_store import TextMeetingStore  # noqa: E402

GUILD_ID = 1
VOICE_CHANNEL_ID = 20
TEXT_CHANNEL_ID = 30
LEADER_ONLY_CHANNEL_ID = 40  # 只有組長看得到、裡面沒有資料：用來試「沒有權限」
PEOPLE = {"A": 1001, "B": 1002, "C": 1003, "D": 1004, "E": 1005}
LEADER = "A"
OUTSIDER_ID = 9999  # 不在團隊裡，什麼都看不到

VOICE_SESSION_ID = "rec-demo-voice"
MEETING_START_ID = 3000  # /meeting start 那則訊息；會議是它和結束訊息「之間」的訊息
TEXT_MEETING_ID = f"mtg-{TEXT_CHANNEL_ID}-{MEETING_START_ID}"

# 劇本裡的期限都是「下週五」這種相對說法，照 spec 只會是待確認提案；加一句絕對時間的明確指派。
EXTRA_VOICE = ("A", "C 負責第一次小考出題，2026/11/27 18:00 前完成。")
EXTRA_TEXT = ("A", f"<@{PEOPLE['C']}> 負責第一次小考出題，2026/11/27 18:00 前完成。")

DEFAULT_SCRIPT = REPO_ROOT / "Demo_Script.md"
DEFAULT_OUT = Path(__file__).resolve().parent / "out"


def read_script(path: Path) -> list[tuple[str, str]]:
    """「**A：** 說的話」→ [("A", "說的話"), …]，讀到第一條 --- 為止。"""
    if not path.is_file():
        raise SystemExit(f"找不到 {path}。它在 main 上；也可以用 --script 指定劇本。")
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip() == "---":
            break
        found = re.match(r"^\*\*([A-E])：\*\*\s*(.+)$", raw.strip())
        if found:
            lines.append((found[1], found[2]))
    if not lines:
        raise SystemExit(f"{path} 裡沒有「**A：** …」格式的對話")
    return lines


def build(script: Path = DEFAULT_SCRIPT, out: Path = DEFAULT_OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    db = out / "messages.sqlite3"
    for old in (db, out / "messages.sqlite3-wal", out / "messages.sqlite3-shm"):
        old.unlink(missing_ok=True)
    dialogue = read_script(script)
    simple = get_summarizer("simple")
    names = {str(uid): who for who, uid in PEOPLE.items()}

    # 語音：一句 12 秒
    store = TranscriptStore(db)
    start = datetime(2026, 11, 20, 6, 0, tzinfo=timezone.utc)
    spoken = [*dialogue, EXTRA_VOICE]
    store.start_session(VOICE_SESSION_ID, GUILD_ID, VOICE_CHANNEL_ID, start.isoformat(), PEOPLE[LEADER])
    store.add_lines(VOICE_SESSION_ID, [
        NewLine(PEOPLE[who], (start + timedelta(seconds=12 * n)).isoformat(),
                (start + timedelta(seconds=12 * n + 10)).isoformat(), text, text, 0.9)
        for n, (who, text) in enumerate(spoken)
    ])
    store.end_session(VOICE_SESSION_ID, (start + timedelta(seconds=12 * len(spoken))).isoformat())
    manifest = out / "recordings" / VOICE_SESSION_ID / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"names": names}, ensure_ascii=False, indent=2), encoding="utf-8")
    summarize_session(store, VOICE_SESSION_ID, simple, names)

    # 文字會議：一則 30 秒；文字記錄存進 messages 表，/meeting end 存會議紀錄
    messages_store = MessageStore(db)
    begin = datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc)
    messages = []
    for n, (who, text) in enumerate([*dialogue, EXTRA_TEXT], start=1):
        message_id = MEETING_START_ID + n
        at = (begin + timedelta(seconds=30 * n)).isoformat()
        messages_store.save_message(message_id, GUILD_ID, TEXT_CHANNEL_ID, PEOPLE[who], text, at)
        messages.append({
            "message_id": str(message_id), "author_id": str(PEOPLE[who]), "name": who, "created_at": at, "text": text,
            "mentions": [{"id": str(uid), "name": name} for name, uid in PEOPLE.items() if f"<@{uid}>" in text],
        })
    meeting = {
        "guild_id": GUILD_ID, "channel_id": TEXT_CHANNEL_ID, "started_by": PEOPLE[LEADER],
        "started_at": begin.isoformat(), "ended_at": (begin + timedelta(seconds=30 * (len(messages) + 1))).isoformat(),
        "start_message_id": MEETING_START_ID, "end_message_id": MEETING_START_ID + len(messages) + 1,
        "messages": messages,
    }
    summarize_text_meeting(TextMeetingStore(db), meeting, simple)
    (out / "text_meeting_messages.json").write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {"db": db, "recordings": out / "recordings", "voice_lines": len(spoken), "text_messages": len(messages)}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="【測試用】產生假的 bot 資料庫")
    p.add_argument("--script", type=Path, default=DEFAULT_SCRIPT, help="劇本（預設 repo 根目錄的 Demo_Script.md）")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="輸出資料夾（預設 demo_data/out）")
    args = p.parse_args(argv)
    made = build(args.script, args.out)
    print(f"假資料庫：{made['db']}")
    print(f"  語音錄音 {VOICE_SESSION_ID}：{made['voice_lines']} 句（語音頻道 {VOICE_CHANNEL_ID}）")
    print(f"  文字會議 {TEXT_MEETING_ID}：{made['text_messages']} 則（文字頻道 {TEXT_CHANNEL_ID}）")
    print(f"  人：{', '.join(f'{k}={v}' for k, v in PEOPLE.items())}；組長 {LEADER}；團隊外的人 {OUTSIDER_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
