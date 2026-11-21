# SQLite API 使用指南

`sqlite_api.py` 提供文字訊息、語音逐字稿與會議摘要共用的 `SQLiteStore`。預設資料庫位於根目錄的 `data/messages.sqlite3`。本機開發可以使用暫存資料庫測試，避免改到既有紀錄。

## 安裝與路徑

在專案根目錄，用要執行程式的 Python 3.11 以上環境安裝。

```sh
python -m pip install -e .
```

Bot 與 CLI 會載入根目錄的 `.env`。選填的 `BOT_DB` 支援絕對路徑與相對專案根目錄的路徑。CLI 的 `--db` 優先，若傳入相對路徑，則以執行命令時的位置為準。獨立 Python 工具可明確傳入 `SQLiteStore(path)`，或使用 `DEFAULT_DB` 與 `resolve_database_path`。這個儲存模組不會自行讀取 `.env`。

## 文字讀寫範例

以下範例使用假資料，資料庫會在範例執行完後移除。Discord IDs 使用整數，時間使用 ISO 8601 UTC。

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlite_api import SQLiteStore

with TemporaryDirectory() as directory:
    store = SQLiteStore(Path(directory) / "example.sqlite3")
    store.save_message(
        message_id=101,
        guild_id=20,
        channel_id=30,
        author_id=40,
        content="週五交第一版報告",
        created_at="2026-11-22T03:00:00+00:00",
    )
    store.update_message(
        message_id=101,
        guild_id=20,
        content="週五下午交第一版報告",
        edited_at="2026-11-22T03:05:00+00:00",
    )
    rows = store.list_recent_messages(guild_id=20, channel_id=30, limit=20)
    assert rows[0]["content"] == "週五下午交第一版報告"
```

| 欄位 | 型別與用途 |
|---|---|
| `message_id` | `int`，Discord 訊息 ID。 |
| `guild_id`、`channel_id` | `int`，伺服器及頻道或討論串 ID。 |
| `author_id` | `int`，Discord 作者 ID。可透過 Discord 查顯示名稱。 |
| `content` | `str`，目前保存的文字。 |
| `created_at`、`edited_at` | ISO 8601 UTC 字串。未編輯時 `edited_at` 為 `None`。 |

`list_recent_messages` 回傳 `list[sqlite3.Row]`，可用欄位名稱索引。結果限定一個伺服器及頻道，排除空文字，依建立時間與訊息 ID 由新到舊排序。預設 100 筆，允許 1 至 1000，超出會拋出 `ValueError`。沒有符合資料時回傳空清單。

寫入相同訊息可安全重試，重複資料保留第一次儲存的文字。修改請使用 `update_message`，找不到對應訊息時回傳 `False`。較舊的編輯不會覆蓋較新的版本。要匯入歷史訊息時，使用 `save_historical_message` 同步紀錄匯入進度。經 `delete_message` 或 `delete_messages` 刪除的訊息會留刪除標記，避免再次匯入。資料庫開啟、鎖定或讀寫失敗時，應處理 `sqlite3.Error`，勿將失敗當成沒有資料。語音方法遇到不存在的 session 時，依 docstring 回傳空結果或拋出 `SessionNotFound`。

## Discord 使用者的讀取權限

`SQLiteStore` 供可信任的後端流程保存或整理資料。使用者發起的 AI 查詢請走 `client.message_reader.recent_messages_for(member_id, channel_id)`。語音資料請使用 `client.transcript_reader`。兩者都查詢 Discord 當下的權限。AI 工具請從可信任的 Discord 請求取得 `member_id`，並在跨來源輸出前依聽眾再驗權。[AI 讀取說明](docs/ai_memory_api.md)

## 方法名稱對照

舊程式呼叫者請更新為右欄。方法參數與回傳格式沿用原有行為。

| 舊名 | 新名 |
|---|---|
| `save_history_message` | `save_historical_message` |
| `last_backfilled_message_id` | `get_last_backfilled_message_id` |
| `recent_messages` | `list_recent_messages` |
| `start_session` | `create_voice_session` |
| `end_session` | `end_voice_session` |
| `get_session` | `get_voice_session` |
| `recent_sessions` | `list_recent_voice_sessions` |
| `add_lines` | `add_transcript_lines` |
| `lines` | `list_transcript_lines` |
| `line_count` | `count_transcript_lines` |
| `save_summary` | `save_session_summary` |
| `summary` | `get_session_summary` |
| `delete_speaker` | `delete_speaker_transcript` |
| `delete_session` | `delete_voice_session` |

`save_message`、`update_message`、`delete_message`、`delete_messages`、`delete_channel`、`delete_guild` 可照原名使用。完整型別與操作行為見 [sqlite_api.py](sqlite_api.py)。

## 搬移既有資料庫

1. 先停止所有使用 SQLite 的 Bot、轉寫和摘要程式。從根目錄確認舊版文字 Bot 路徑 `discord_bot/data/messages.sqlite3` 存在，而且目的地 `data/` 尚未建立。若兩處已有資料，先保留兩份並確認要用的版本。
2. 透過 SQLite 工具對舊檔執行 `PRAGMA wal_checkpoint(TRUNCATE);` 和 `PRAGMA quick_check;`。確認 checkpoint 的第一欄為 `0` 且 quick check 顯示 `ok`，記下各資料表筆數後關閉工具。
3. 從根目錄搬移整個資料夾。PowerShell 使用 `Move-Item -LiteralPath ./discord_bot/data -Destination ./data`，macOS 使用 `mv ./discord_bot/data ./data`。確認根目錄 .env 的 `BOT_DB` 已留空，或已指向要使用的資料庫。
4. 對新位置再做一次 `PRAGMA quick_check;`，確認各表筆數和搬移前相同，再啟動服務。
