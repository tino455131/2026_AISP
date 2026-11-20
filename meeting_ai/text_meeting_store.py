"""TextMeetingStore：文字會議（/meeting）的紀錄，存在 bot 的同一個資料庫檔案裡。

只存會議的範圍、摘要，和每項摘要依據的訊息 ID；不另外保存會議中的完整訊息
（spec：一般聊天不長期完整保存）。要看原文時，照訊息 ID 回 Discord 讀，權限也照頻道的。
讀取摘要的人必須看得到那個頻道（spec R15：衍生資料沿用來源限制）。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS text_meetings (
    meeting_id TEXT PRIMARY KEY,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    started_by INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    start_message_id INTEGER NOT NULL,
    end_message_id INTEGER NOT NULL,
    message_count INTEGER NOT NULL,
    summary TEXT NOT NULL,
    source_message_ids TEXT NOT NULL,
    speakers TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS text_meetings_by_channel ON text_meetings (guild_id, channel_id, started_at);
"""


class TextMeetingStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, record: dict) -> None:
        """Insert or replace one meeting; `summary` and `source_message_ids` are stored as JSON."""
        row = dict(record)
        row["summary"] = row["summary"] if isinstance(row["summary"], str) else json.dumps(row["summary"], ensure_ascii=False)
        row["source_message_ids"] = json.dumps(row["source_message_ids"])
        row["speakers"] = json.dumps(row.get("speakers", {}))  # label (S1) -> author id
        columns = ", ".join(row)
        marks = ", ".join(f":{key}" for key in row)
        with self._connection() as connection:
            connection.execute(f"INSERT OR REPLACE INTO text_meetings ({columns}) VALUES ({marks})", row)

    def get(self, meeting_id: str) -> dict | None:
        with self._connection() as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute("SELECT * FROM text_meetings WHERE meeting_id = ?", (meeting_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        out["summary"] = json.loads(out["summary"])
        out["source_message_ids"] = {int(k): v for k, v in json.loads(out["source_message_ids"]).items()}
        out["speakers"] = json.loads(out["speakers"])
        return out
