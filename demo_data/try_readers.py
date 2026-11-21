"""【測試用】示範 AI 組的 tool 怎麼透過讀取介面拿資料。先跑 make_demo_db.py。

在 repo 根目錄執行：

    discord_bot/.venv/Scripts/python.exe demo_data/try_readers.py

讀取介面每次讀之前都會先確認「這個人現在看不看得到來源頻道」（spec R15）。
例外對應到 spec 的 ErrorCode：
    AccessDenied      → ACCESS_DENIED_USER（你沒有權限取得所要求的資訊）
    AccessUnavailable → PERMISSION_UNVERIFIED（暫時無法確認權限）
    SessionNotFound   → NOT_FOUND（沒有找到符合條件的資料）
正式上線時把 FakeAccess 換成 ChannelAccess(client, guild_id)，其他程式不用改。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "discord_bot")]

from channel_access import AccessDenied, AccessUnavailable, AuthorizedMessageReader  # noqa: E402
from fake_access import FakeAccess  # noqa: E402
from make_demo_db import DEFAULT_OUT, OUTSIDER_ID, PEOPLE, TEXT_CHANNEL_ID, VOICE_CHANNEL_ID, VOICE_SESSION_ID  # noqa: E402
from message_store import MessageStore  # noqa: E402
from transcript_reader import AuthorizedTranscriptReader  # noqa: E402
from transcript_store import SessionNotFound, TranscriptStore  # noqa: E402


async def main(db: Path) -> None:
    access = FakeAccess()
    voice = AuthorizedTranscriptReader(access, TranscriptStore(db))
    text = AuthorizedMessageReader(access, MessageStore(db))
    a = PEOPLE["A"]

    sessions = await voice.recent_sessions_for(a, VOICE_CHANNEL_ID)
    print("1. A 看語音頻道的錄音：", [s.session_id for s in sessions])

    lines = await voice.transcript_for(a, VOICE_SESSION_ID)
    print(f"2. 逐字稿 {len(lines)} 句，第一句：說話的人 {lines[0].speaker_id}「{lines[0].text[:20]}…」")

    view = await voice.summary_for(a, VOICE_SESSION_ID)
    summary = json.loads(view.summary.content)
    print(f"3. 摘要（{view.summary.model}，{'過期了' if view.is_stale else '是最新的'}）："
          f"{len(summary['decisions'])} 項決議、{len(summary['action_items'])} 項待辦")

    recent = await text.recent_messages_for(a, TEXT_CHANNEL_ID, limit=2)
    print("4. 文字頻道最新 2 則：", [row["content"][:20] for row in recent])

    try:
        await voice.transcript_for(OUTSIDER_ID, VOICE_SESSION_ID)
    except AccessDenied:
        print("5. 團隊外的人讀逐字稿 → AccessDenied（ACCESS_DENIED_USER）")

    try:
        await voice.transcript_for(a, "rec-not-here")
    except SessionNotFound:
        print("6. 不存在的錄音 → SessionNotFound（NOT_FOUND）")

    try:
        await AuthorizedTranscriptReader(FakeAccess(unavailable=True), TranscriptStore(db)).transcript_for(a, VOICE_SESSION_ID)
    except AccessUnavailable:
        print("7. Discord 無法確認權限 → AccessUnavailable（PERMISSION_UNVERIFIED）")


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    database = DEFAULT_OUT / "messages.sqlite3"
    if not database.is_file():
        raise SystemExit("先執行 demo_data/make_demo_db.py 產生假資料庫")
    asyncio.run(main(database))
