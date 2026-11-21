"""【測試用】追蹤任務進度：組長確認要追蹤 → 私訊負責人詢問 → 負責人回報 → 通知組長。

照 spec 的名稱和規則（「任務狀態、進度與異動」「提醒、追問與 TeamLeader 彙報」）：
- Task：status 只有 not_started、in_progress、blocked、completed、cancelled；
  activation_state 是 active 或 awaiting_leader_decision（負責人看不到來源頻道時，R18）
- Inquiry：送給負責人的一次詢問；state 是 awaiting_reply、reply_received、closed。
  按鈕回報本身就是確認過、要分享的版本，所以回報後直接 closed（不經過「待釐清」的 reply_received）
- Delivery：sent、delivery_failed、delivery_unknown（私訊失敗不改貼公開頻道，也不算對方沒回，R10；
  結果不明時記 delivery_unknown，不當成送達）
- ProgressUpdate：只有負責人本人的回報能改狀態（Collaborator、組長都不能代替）；
  回報「完成」後就不能再改，重新開啟是組長的事
- 同一次確認重送不會重複建立任務（AC03：用確認的 ID 當 idempotency key）

這是測試版：沒有排程（只在確認時問一次），也不能取消或改期限。
資料表都用 demo_ 開頭，和 AI 組之後的正式資料表分開。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_tasks (
    task_id TEXT PRIMARY KEY,
    confirmation_id TEXT NOT NULL,
    meeting_id TEXT NOT NULL,
    guild_id INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    owner_user_id INTEGER NOT NULL,
    collaborators TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL,
    activation_state TEXT NOT NULL,
    source_refs TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_inquiries (
    inquiry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    delivery_state TEXT NOT NULL,
    provider_message_id TEXT,
    sent_at TEXT NOT NULL,
    reply_received_at TEXT,
    state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_progress_updates (
    update_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    owner_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    inquiry_id INTEGER
);
"""

OWNER_STATUSES = {"not_started", "in_progress", "blocked", "completed"}  # cancelled is the leader's


class TrackingError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TrackingStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        with self._connection() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_tasks(self, confirmation: dict) -> list[dict]:
        """The leader confirmed exactly these tasks. Running it again returns the same tasks."""
        created = _now()
        with self._connection() as connection:
            for number, task in enumerate(confirmation["tasks"], start=1):
                connection.execute(
                    """INSERT OR IGNORE INTO demo_tasks VALUES
                       (:task_id, :confirmation_id, :meeting_id, :guild_id, :channel_id, :title, :description,
                        :owner_user_id, :collaborators, :due_at, 'not_started', :activation_state, :source_refs,
                        :created_by, :created_at, 1)""",
                    {
                        "task_id": f"task-{confirmation['confirmation_id']}-{number}",
                        "confirmation_id": confirmation["confirmation_id"],
                        "meeting_id": confirmation["meeting_id"],
                        "guild_id": int(confirmation["guild_id"]),
                        "channel_id": int(confirmation["channel_id"]),
                        "title": task["title"],
                        "description": task.get("description", ""),
                        "owner_user_id": int(task["owner_user_id"]),
                        "collaborators": json.dumps([str(c) for c in task.get("collaborators", [])]),
                        "due_at": task["due_at"],
                        "activation_state": task.get("activation_state", "active"),
                        "source_refs": json.dumps(task.get("source_refs", []), ensure_ascii=False),
                        "created_by": int(confirmation["created_by"]),
                        "created_at": created,
                    },
                )
            rows = connection.execute(
                "SELECT * FROM demo_tasks WHERE confirmation_id = ? ORDER BY task_id", (confirmation["confirmation_id"],)
            ).fetchall()
        return [self._task(row) for row in rows]

    def record_inquiry(self, task_id: str, owner_id: int, delivery_state: str, message_id: str | None) -> int:
        state = "awaiting_reply" if delivery_state == "sent" else "closed"  # never sent: not "no reply"
        with self._connection() as connection:
            cursor = connection.execute(
                """INSERT INTO demo_inquiries (task_id, owner_id, delivery_state, provider_message_id, sent_at, state)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (task_id, int(owner_id), delivery_state, message_id, _now(), state),
            )
            return cursor.lastrowid

    def record_progress(self, task_id: str, user_id: int, status: str) -> dict:
        """Only the task's owner can report, and not after completing it; ends any open inquiry for it."""
        if status not in OWNER_STATUSES:
            raise TrackingError("INVALID_ARGUMENT", f"負責人不能把狀態改成 {status}")
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM demo_tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None:
                raise TrackingError("NOT_FOUND", "沒有找到符合條件的資料。")
            if row["owner_user_id"] != int(user_id):
                raise TrackingError("ROLE_REQUIRED", "只有這項任務的負責人可以回報進度。")
            if row["status"] == "cancelled":
                raise TrackingError("INVALID_ARGUMENT", "這項任務已經取消了。")
            if row["status"] == "completed":  # terminal: only the leader may reopen it (spec)
                raise TrackingError("INVALID_ARGUMENT", "這項任務已經回報完成；要重新開啟請找組長。")
            inquiry = connection.execute(
                "SELECT inquiry_id FROM demo_inquiries WHERE task_id = ? AND state = 'awaiting_reply' ORDER BY inquiry_id DESC",
                (task_id,),
            ).fetchone()
            now = _now()
            if inquiry:  # a button press is already the confirmed, shared report: the inquiry is done
                connection.execute(
                    "UPDATE demo_inquiries SET state = 'closed', reply_received_at = ? WHERE inquiry_id = ?",
                    (now, inquiry[0]),
                )
            connection.execute(
                "INSERT INTO demo_progress_updates (task_id, owner_id, status, confirmed_at, inquiry_id) VALUES (?, ?, ?, ?, ?)",
                (task_id, int(user_id), status, now, inquiry[0] if inquiry else None),
            )
            connection.execute(
                "UPDATE demo_tasks SET status = ?, version = version + 1 WHERE task_id = ?", (status, task_id)
            )
            row = connection.execute("SELECT * FROM demo_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._task(row)

    def tasks(self, guild_id: int) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM demo_tasks WHERE guild_id = ? ORDER BY created_at DESC, task_id", (int(guild_id),)
            ).fetchall()
        return [self._task(row) for row in rows]

    @staticmethod
    def _task(row: sqlite3.Row) -> dict:
        task = dict(row)
        task["collaborators"] = json.loads(task["collaborators"])
        task["source_refs"] = json.loads(task["source_refs"])
        return task
