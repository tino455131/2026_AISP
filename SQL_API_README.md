# SQLite API 使用指南

`sqlite_api.py` 提供文字訊息、語音逐字稿、兩種會議與 AI 測試追蹤共用的 `SQLiteStore`。預設資料庫位於根目錄的 `data/messages.sqlite3`。本機開發可以使用暫存資料庫測試，避免改到既有紀錄。

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
    rows = store.get_channel_message_list(guild_id=20, channel_id=30, limit=20)
    assert rows[0]["content"] == "週五下午交第一版報告"
```

| 欄位 | 型別與用途 |
|---|---|
| `message_id` | `int`，Discord 訊息 ID。 |
| `guild_id`、`channel_id` | `int`，伺服器及頻道或討論串 ID。 |
| `author_id` | `int`，Discord 作者 ID。可透過 Discord 查顯示名稱。 |
| `content` | `str`，目前保存的文字。 |
| `created_at`、`edited_at` | ISO 8601 UTC 字串。未編輯時 `edited_at` 為 `None`。 |

`get_channel_message_list` 回傳 `list[sqlite3.Row]`，可用欄位名稱索引。結果限定一個伺服器及頻道，排除空文字，先選出最新的指定筆數，再依建立時間與訊息 ID 由舊到新排序。預設 100 筆，允許 1 至 1000，超出會拋出 `ValueError`。沒有符合資料時回傳空清單。

寫入相同訊息可安全重試，重複資料保留第一次儲存的文字。修改請使用 `update_message`，找不到對應訊息時回傳 `False`。較舊的編輯不會覆蓋較新的版本。要匯入歷史訊息時，使用 `save_historical_message` 同步紀錄匯入進度。經 `delete_message` 或 `delete_messages` 刪除的訊息會留刪除標記，避免再次匯入。資料庫開啟、鎖定或讀寫失敗時，應處理 `sqlite3.Error`，勿將失敗當成沒有資料。語音方法遇到不存在的 session 時，依 docstring 回傳空結果或拋出 `SessionNotFound`。

## Discord 使用者的讀取權限

`SQLiteStore` 供可信任的後端流程保存或整理資料。使用者發起的 AI 查詢請走 `client.message_reader.recent_messages_for(member_id, channel_id)`。語音資料請使用 `client.transcript_reader`。兩者都查詢 Discord 當下的權限。AI 工具請從可信任的 Discord 請求取得 `member_id`，並在跨來源輸出前依聽眾再驗權。[AI 讀取說明](docs/ai_memory_api.md)

## 方法

以下整理 [`sqlite_api.py`](sqlite_api.py) 的公開介面。表中方法皆由 `store = SQLiteStore(path)` 建立的實例呼叫，路徑工具與建構方式見第一表。

`guild_id`、`channel_id`、`message_id`、`author_id`、`speaker_id` 與 `started_by` 都使用 Discord 整數 ID。`channel_id` 也可傳討論串 ID。`session_id` 是語音錄音的字串 ID，`meeting_id` 是文字會議的字串 ID。時間欄位皆為 ISO 8601 UTC 字串，例如 `2026-11-22T03:00:00+00:00`。標示 `=` 的參數可省略，用方法簽名的預設值。

### 路徑與初始化

| 介面 | 參數 | 回傳與行為 |
|---|---|---|
| `DEFAULT_DB` | — | `Path`，指向根目錄下的 `data/messages.sqlite3`。 |
| `resolve_database_path` | `configured_path: str \| None = None`，可傳 `BOT_DB` 的值 | `Path`。空白或 `None` 使用 `DEFAULT_DB`，相對路徑以專案根目錄為基準。 |
| `SQLiteStore` | `path: str \| Path`，資料庫檔案路徑。選填關鍵字參數 `read_only: bool = False` | `SQLiteStore` 實例。預設建立必要目錄和資料表。唯讀模式開啟既有資料庫，檔案缺少時拋出 `FileNotFoundError`。 |

### 文字訊息

| 方法 | 參數 | 回傳與行為 |
|---|---|---|
| `save_message` | `message_id: int`、`guild_id: int`、`channel_id: int`、`author_id: int`、`content: str`、`created_at: str`，選填關鍵字參數 `edited_at: str \| None = None` | `None`。新增即時訊息。重複送入且省略 `edited_at` 時保留既有版本。帶入 `edited_at` 時，可套用時間相同或更新的編輯。 |
| `save_historical_message` | `message_id: int`、`guild_id: int`、`channel_id: int`、`author_id: int`、`content: str`、`created_at: str`、`edited_at: str \| None`（必填，未編輯傳 `None`） | `None`。在同一交易匯入文字並更新補匯進度。重複訊息保留既有資料，空文字只推進進度。 |
| `update_message` | `message_id: int`、`guild_id: int`、`content: str`、`edited_at: str` | `bool`。找到指定訊息即回傳 `True`，包括收到較舊編輯而保留原版本的情況。找不到時回傳 `False`。 |
| `get_channel_message_list` | `guild_id: int`、`channel_id: int`、`limit: int = 100`（1–1000） | `list[sqlite3.Row]`。取指定頻道最新的非空文字，依建立時間和訊息 ID 由舊到新排序。欄位見[文字讀寫範例](#文字讀寫範例)。無資料時回傳 `[]`。 |
| `get_last_backfilled_message_id` | `guild_id: int`、`channel_id: int` | `int \| None`。取得該頻道補匯已處理的最大訊息 ID。首次補匯前回傳 `None`。 |
| `delete_message` | `message_id: int`、`guild_id: int` | `None`。刪除訊息並寫入刪除標記，避免即時事件或補匯重新寫入。 |
| `delete_messages` | `message_ids: set[int]`、`guild_id: int` | `None`。在同一交易批次刪除並寫入標記。空集合直接結束。 |

### 語音場次與逐字稿

| 方法 | 參數 | 回傳與行為 |
|---|---|---|
| `create_voice_session` | `session_id: str`、`guild_id: int`、`channel_id: int`、`started_at: str`、`started_by: int \| None = None` | `None`。建立錄音場次。重複的 `session_id` 會拋出 `sqlite3.IntegrityError`。 |
| `end_voice_session` | `session_id: str`、`ended_at: str` | `None`。設定場次結束時間。場次不存在時拋出 `SessionNotFound`。 |
| `get_voice_session` | `session_id: str` | `VoiceSession`，包含來源頻道與起訖時間等欄位。場次不存在時拋出 `SessionNotFound`。 |
| `list_recent_voice_sessions` | `guild_id: int`、`channel_id: int`、`limit: int = 20`（1–200） | `list[VoiceSession]`。取指定頻道場次，依開始時間由新到舊排序。無資料時回傳 `[]`。 |
| `add_transcript_lines` | `session_id: str`、`lines: Iterable[NewLine]` | `int`，實際新增的行數。批次附加逐字稿，重複送入會再次新增。場次不存在時拋出 `SessionNotFound`。 |
| `list_transcript_lines` | `session_id: str` | `list[TranscriptLine]`。按開始時間及行 ID 由小到大排序。沒有逐字稿或找不到場次時回傳 `[]`。 |
| `count_transcript_lines` | `session_id: str` | `int`，逐字稿行數。沒有逐字稿或找不到場次時回傳 `0`。 |
| `delete_speaker_transcript` | `session_id: str`、`speaker_id: int` | `None`。移除指定成員在該場次的逐字稿，並清除該場次的既有摘要。 |
| `delete_voice_session` | `session_id: str` | `None`。刪除該場次、全部逐字稿與摘要。 |

### 語音摘要與文字會議

| 方法 | 參數 | 回傳與行為 |
|---|---|---|
| `save_session_summary` | `session_id: str`、`content: str`（純文字或 JSON 字串）、`model: str`、`prompt_version: str`、`created_at: str` | `None`。新增或取代語音摘要，並記下儲存當下的逐字稿行數。場次不存在時拋出 `SessionNotFound`。 |
| `get_session_summary` | `session_id: str` | `SessionSummary \| None`。回傳語音摘要及產生資訊，`content` 保留為字串。沒有已存摘要時回傳 `None`。 |
| `save_text_meeting` | `record: Mapping[str, Any]`，需提供下表列出的全部欄位 | `None`。以 `meeting_id` 新增或取代文字會議紀錄。缺少必填欄位會拋出 `KeyError`。 |
| `get_text_meeting` | `meeting_id: str` | `dict \| None`。回傳完整紀錄，並解碼 `summary`、`source_message_ids`、`speakers`。`source_message_ids` 的鍵會轉回整數。查無紀錄時回傳 `None`。 |

`save_text_meeting` 的 `record` 必填欄位如下。文字會議以摘要、時間範圍與引用保留整理結果。

| 欄位 | 型別與用途 |
|---|---|
| `meeting_id` | `str`，例如 `mtg-30-101`（格式為 `mtg-<channel_id>-<start_message_id>`）。 |
| `guild_id`、`channel_id`、`started_by` | `int`，來源伺服器、頻道與開始會議的 Discord 使用者 ID。 |
| `started_at`、`ended_at`、`created_at` | `str`，會議起訖與紀錄建立時間。 |
| `start_message_id`、`end_message_id` | `int`，界定會議範圍的 Discord 訊息 ID。 |
| `message_count` | `int`，納入摘要的訊息筆數。 |
| `summary` | `dict` 或合法 JSON 字串，存放摘要、決定及候選待辦。 |
| `source_message_ids` | `dict[int, int]`，摘要引用行號對應到 Discord 訊息 ID。 |
| `speakers` | `dict[str, int]`，發言者代號（例如 `S1`）對應到 Discord 使用者 ID。 |
| `model`、`prompt_version` | `str`，模型或摘要器名稱及提示詞版本。 |

### 跨資料刪除

| 方法 | 參數 | 回傳與行為 |
|---|---|---|
| `delete_channel` | `guild_id: int`、`channel_id: int` | `None`。在同一交易清除該頻道的文字訊息、歷史匯入進度、語音場次及其逐字稿與摘要、文字會議。伺服器級訊息刪除標記會保留。 |
| `delete_guild` | `guild_id: int` | `None`。在同一交易清除整個伺服器的上述資料及訊息刪除標記。 |

### AI demo 的會議查詢與進度追蹤

| 方法 | 參數 | 回傳與行為 |
|---|---|---|
| `list_meeting_overviews` | — | `list[dict]`。兩種會議的基本資料、句數與摘要狀態，依開始時間由新到舊排序。 |
| `get_voice_meeting_data` | `session_id: str` | 同一讀取交易中的 `(VoiceSession, list[TranscriptLine], SessionSummary 或 None)`。找不到場次時回傳 `None`。 |
| `get_text_meeting_data` | `meeting_id: str`、`include_saved_messages: bool = False` | `(dict, list[sqlite3.Row])` 或 `None`。選用保存原文時只取同一伺服器、頻道及會議起訖 ID 之間的訊息。 |
| `create_demo_tasks` | `confirmation: dict` | `list[dict]`。確認資料包含 `confirmation_id`、`meeting_id`、`guild_id`、`channel_id`、`created_by` 與 `tasks`。任務包含 `title`、`owner_user_id`、`due_at`，可帶 `description`、`collaborators`、`source_refs`、`activation_state`。相同確認重送會取回既有任務。 |
| `record_demo_inquiry` | `task_id: str`、`owner_id: int`、`delivery_state: str`、`message_id: str` 或 `None` | `int`，新增的詢問 ID。已送達的詢問會等待回覆，其他送達結果直接結案。 |
| `record_demo_progress` | `task_id: str`、`user_id: int`、`status: str` | `dict`，更新後的任務。只接受負責人回報，並在同一交易記錄進度及結束最近的待回覆詢問。無權或狀態無效時拋出 `TrackingError`。 |
| `list_demo_tasks` | `guild_id: int` | `list[dict]`，該伺服器的任務，依建立時間由新到舊排列。 |
| `list_demo_inquiries` | `task_id: str` | `list[dict]`，該任務的詢問、送達和回覆資料，依詢問 ID 排序。 |

測試追蹤維持既有 `demo_*` 資料表和狀態。應用程式可用 `TrackingError.error_code` 判別找不到任務、角色限制或無效狀態。

### 語音資料型別

| 型別 | 欄位 |
|---|---|
| `VoiceSession` | `session_id: str`、`guild_id: int`、`channel_id: int`、`started_at: str`、`ended_at: str \| None`（尚未結束時為 `None`）、`started_by: int \| None`。 |
| `NewLine` | `speaker_id: int`、`started_at: str`、`ended_at: str`、`text: str`（整理後文字）、`text_raw: str`（辨識原始結果）、`confidence: float`（0–1）、`flags: tuple[str, ...] = ()`（辨識警示）。 |
| `TranscriptLine` | `line_id: int`（SQLite 產生的行 ID）、`session_id: str`、`speaker_id: int`、`started_at: str`、`ended_at: str`、`text: str`、`confidence: float`、`flags: tuple[str, ...]`。 |
| `SessionSummary` | `session_id: str`、`content: str`、`model: str`、`prompt_version: str`、`source_line_count: int`（儲存摘要時的行數）、`created_at: str`。 |

查詢筆數超出表列範圍時捕捉 `ValueError`，場次查找失敗可依各方法處理 `SessionNotFound`。開啟、鎖定或讀寫資料庫失敗時捕捉 `sqlite3.Error`。Discord 使用者能讀哪些資料，由[授權讀取介面](#discord-使用者的讀取權限)判斷。
