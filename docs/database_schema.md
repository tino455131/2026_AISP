# Bot 資料庫架構

全部存在同一個 SQLite 檔：`discord_bot/data/messages.sqlite3`。這個檔案在 `.gitignore` 裡，不會上傳。

- 時間一律是 UTC 的 RFC 3339 字串。
- Discord ID 存成 INTEGER。傳給 JavaScript 時要轉成字串，因為 JavaScript 的數字裝不下這麼長的 ID。
- 誰可以讀，照「來源頻道」的權限決定（spec R15）。正式讀取一律走讀取介面，例如 `AuthorizedTranscriptReader`。

## 有哪些表

| 群組 | 表 | 誰寫入 | 什麼時候建立 |
|---|---|---|---|
| 語音 | `voice_sessions`、`voice_lines`、`voice_session_summaries` | voice_stt（逐字稿）、meeting_ai（摘要） | 第一次錄完音 |
| 文字訊息 | `messages`、`backfill_state`、`deleted_messages` | 文字記錄（`discord_bot/bot.py` 或 `team_bot/text_logger.py`） | 文字記錄第一次啟動 |
| 文字會議 | `text_meetings` | `/meeting end`（meeting_ai） | 第一次結束文字會議 |
| 追蹤進度（測試） | `demo_tasks`、`demo_inquiries`、`demo_progress_updates` | `/ai tasks` 的「追蹤」按鈕（ai_demo） | 第一次確認追蹤 |

表都是程式第一次用到時才建立的。2026-11-21 時，資料庫裡只有語音的三張表：6 場錄音、115 句、6 份摘要。

## 關係圖

```mermaid
erDiagram
  voice_sessions ||--o{ voice_lines : "一場有很多句"
  voice_sessions ||--o| voice_session_summaries : "一場一份摘要"
  text_meetings }o..o{ messages : "開始到結束之間的訊息（用 ID 範圍，不是外鍵）"
  demo_tasks }o..|| voice_sessions : "meeting_id = session_id"
  demo_tasks }o..|| text_meetings : "meeting_id"
  demo_tasks ||--o{ demo_inquiries : "每次詢問"
  demo_tasks ||--o{ demo_progress_updates : "每次回報"
  demo_inquiries |o--o| demo_progress_updates : "回覆哪一次詢問"

  voice_sessions {
    TEXT session_id PK "rec-頻道-時間"
    INTEGER guild_id
    INTEGER channel_id "語音頻道"
    TEXT started_at
    TEXT ended_at
    INTEGER started_by "自動錄音時是空的"
  }
  voice_lines {
    INTEGER line_id PK
    TEXT session_id FK
    INTEGER guild_id
    INTEGER channel_id
    INTEGER speaker_id "說話的人"
    TEXT started_at
    TEXT ended_at
    TEXT text "整理後的繁體中文"
    TEXT text_raw "辨識原文"
    REAL confidence "0-1"
    TEXT flags "JSON，例如可能聽錯"
  }
  voice_session_summaries {
    TEXT session_id PK
    TEXT content "JSON：summary、decisions、action_items"
    TEXT model "例如 claude-code"
    TEXT prompt_version
    INTEGER source_line_count "句數變了就代表摘要過期"
    TEXT created_at
  }
  messages {
    INTEGER message_id PK
    INTEGER guild_id
    INTEGER channel_id
    INTEGER author_id
    TEXT content
    TEXT created_at
    TEXT edited_at
  }
  backfill_state {
    INTEGER guild_id PK
    INTEGER channel_id PK
    INTEGER last_message_id "歷史訊息匯入到哪"
  }
  deleted_messages {
    INTEGER guild_id PK
    INTEGER message_id PK
  }
  text_meetings {
    TEXT meeting_id PK "mtg-頻道-開始訊息"
    INTEGER guild_id
    INTEGER channel_id
    INTEGER started_by "組長"
    TEXT started_at
    TEXT ended_at
    INTEGER start_message_id
    INTEGER end_message_id
    INTEGER message_count
    TEXT summary "JSON"
    TEXT source_message_ids "JSON：行號對應訊息 ID"
    TEXT speakers "JSON：S1 對應誰"
    TEXT model
    TEXT prompt_version
    TEXT created_at
  }
  demo_tasks {
    TEXT task_id PK
    TEXT confirmation_id "同一次確認不重複建立"
    TEXT meeting_id
    INTEGER guild_id
    INTEGER channel_id "來源頻道"
    TEXT title
    TEXT description
    INTEGER owner_user_id "負責人"
    TEXT collaborators "JSON"
    TEXT due_at
    TEXT status "not_started 等五種"
    TEXT activation_state "active 或 awaiting_leader_decision"
    TEXT source_refs "JSON：依據"
    INTEGER created_by "確認的組長"
    TEXT created_at
    INTEGER version
  }
  demo_inquiries {
    INTEGER inquiry_id PK
    TEXT task_id FK
    INTEGER owner_id
    TEXT delivery_state "sent、delivery_failed、delivery_unknown"
    TEXT provider_message_id "私訊的訊息 ID"
    TEXT sent_at
    TEXT reply_received_at
    TEXT state "awaiting_reply、reply_received、closed"
  }
  demo_progress_updates {
    INTEGER update_id PK
    TEXT task_id FK
    INTEGER owner_id
    TEXT status
    TEXT confirmed_at
    INTEGER inquiry_id FK
  }
```

## 每個功能讀哪些表

| 功能 | 讀 | 寫 |
|---|---|---|
| 錄音結束 → 逐字稿 | — | `voice_sessions`、`voice_lines` |
| 錄音結束 → 摘要 | `voice_lines` | `voice_session_summaries` |
| 「查看摘要／逐字稿」按鈕 | 先讀 `voice_sessions` 找到語音頻道，確認權限後讀 `voice_lines`、`voice_session_summaries` | — |
| `/meeting end` | 直接向 Discord 讀這段訊息 | `text_meetings` |
| `/ai` 選會議（打字搜尋） | `voice_sessions`（含句數、有沒有摘要）、`text_meetings`；bot 再過濾掉你看不到的頻道 | — |
| `/ai tasks`、`/ai ask`（語音） | `voice_sessions`、`voice_lines`（照時間排序，重新編號成第 1、2、3… 句）、`voice_session_summaries`；名字從錄音資料夾的 `manifest.json` 讀 | — |
| `/ai tasks`、`/ai ask`（文字會議） | `text_meetings` 拿範圍；原文由 bot 當場向 Discord 讀，不存進資料庫 | — |
| 「追蹤」按鈕、負責人回報 | `demo_tasks` | `demo_tasks`、`demo_inquiries`、`demo_progress_updates` |
| 文字記錄 | — | `messages`、`backfill_state`、`deleted_messages` |
