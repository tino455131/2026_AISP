# 給 AI 組的讀取介面（v0.1）

> 這份說明「AI 功能要怎麼拿到 Discord 的文字與語音資料」，以及「整理過的資料（例如會議摘要）存在哪、誰負責」。
> 文字部分是皓元已完成的程式；語音部分由 Ping3227 實作（`text_bot/transcript_*.py`）。

## 1. 三條規則

1. **面向使用者時只能透過 reader 讀資料**，不要直接查 SQLite 或呼叫根目錄 `sqlite_api.SQLiteStore` 的底層讀取方法。系統內部轉寫與摘要處理可用 `SQLiteStore` 寫入及整理資料。
   reader 每次都會當下問 Discord「這個人現在看得到這個頻道嗎」，這是私人頻道不外洩的唯一保證。
2. **每次讀取都要帶「替誰讀」的 `member_id`**（通常是下指令或私訊 bot 的人）。
3. **輸出前再檢查一次聽眾**：答案會貼到哪裡、誰會看到，就只能用「那些人全部都有權看」的資料（見第 5 節）。

讀不到時的兩種例外：

| 例外 | 意思 | AI 該怎麼做 |
|---|---|---|
| `AccessDenied` | 這個人沒有權限 | 不使用這個頻道的資料；必要時告訴使用者「你沒有權限看那個頻道」 |
| `AccessUnavailable` | Discord 暫時無法確認 | 不要猜，也不要用快取；請使用者稍後再試 |

底層儲存方法及欄位說明見 [SQL_API_README.md](../SQL_API_README.md)。

## 2. 文字訊息（皓元，已完成）

```py
messages = await client.message_reader.recent_messages_for(member_id, channel_id, limit=100)
```

回傳 `sqlite3.Row` 清單（新到舊）：

| 欄位 | 說明 |
|---|---|
| `message_id` | Discord 訊息 ID |
| `guild_id`／`channel_id` | 伺服器／頻道 ID |
| `author_id` | 發言者 Discord ID（名字請用 `channel_access.visible_members()` 或 Discord 查） |
| `content` | 文字內容 |
| `created_at`／`edited_at` | ISO 8601，UTC |

## 3. 語音逐字稿（新增）

一場錄音 = 一個 session，綁定一個語音頻道。權限規則和文字一樣，看的是**語音頻道**的 View Channel + Read Message History。

```py
reader = client.transcript_reader

sessions = await reader.recent_sessions_for(member_id, voice_channel_id, limit=20)  # 新到舊
lines = await reader.transcript_for(member_id, session_id)                          # 依時間排序
view = await reader.summary_for(member_id, session_id)                              # 沒有摘要時是 None
```

`VoiceSession`：`session_id`、`guild_id`、`channel_id`（語音頻道）、`started_at`、`ended_at`、`started_by`

`TranscriptLine`：

| 欄位 | 說明 |
|---|---|
| `line_id` | 這一句的編號（引用來源時用） |
| `speaker_id` | 說話者 Discord ID（每人一軌錄音，一定準確） |
| `started_at`／`ended_at` | ISO 8601，UTC，和文字訊息同格式，可以混在一起排序 |
| `text` | 台灣繁體中文 |
| `confidence` | 0–1，越低越可能聽錯 |
| `flags` | 警告：`low_confidence`、`repetitive`、`maybe_no_speech`、`hallucination_suspect` |

**給 prompt 設計的建議**：有 `flags` 或 `confidence` 低的句子，請在 prompt 裡標註「可能聽錯」，不要讓 AI 把它當成確定的事實（例如期限、負責人）。

## 4. 整理過的資料：存在哪、誰負責？

**結論：存放與保護在資料層（我們），內容在 AI 組。**

| 工作 | 誰 | 原因 |
|---|---|---|
| 要整理什麼、prompt 怎麼寫、什麼時候產生 | AI 組 | 這是「AI 行為設計」本身 |
| 存在哪、誰能讀、原始資料刪掉時一起刪 | 資料層（語音：Ping3227；文字：皓元） | 摘要裡有原始內容，必須遵守**同一套**權限與刪除規則，否則摘要會變成繞過權限的後門 |

目前只先做**會議摘要**，因為會議逐字稿很長（30 分鐘約 1 萬 token），而且「回顧上次會議」會被反覆問。
文字聊天在我們的規模（4 人）直接讀原始訊息就夠，等真的變慢或太貴再加「每日頻道摘要」，做法同下。

會議摘要的介面：

```py
# AI 組產生摘要後存起來（先用 reader 讀過逐字稿，確認有權限）
client.store.save_session_summary(session_id, content, model="...", prompt_version="v1", created_at=now_iso)

# 之後讀
view = await client.transcript_reader.summary_for(member_id, session_id)
if view is None or view.is_stale:
    ...  # 重新產生
else:
    view.summary.content
```

**產生摘要的介面**：見 [meeting_ai/README.md](../meeting_ai/README.md)。`MeetingSummarizer` 只要實作 `summarize()` 就能替換。目前內建 `simple`（關鍵字，測試用）和 `openai` 兩個版本；錄音結束後由 voice_bot 自動呼叫並存進資料庫，**不主動貼出來**；語音頻道裡只留一則靜音訊息和「查看摘要」「查看逐字稿」按鈕，按的人透過 reader 讀、只有自己看得到。實際用 reader 讀的範例見 `meeting_ai/show_session.py`。

保存與失效規則（已實作）：

- **一份摘要只對應一場會議**（一個語音頻道），不跨頻道混合，權限才能直接沿用那個頻道。
- 記下 `model`、`prompt_version`：改 prompt 後可以只重做舊版本的摘要。
- 記下產生時有幾句（`source_line_count`）：之後句子有增減，`is_stale` 會變成 `True`。
- **有人撤回同意**（`delete_speaker`）、**整場刪除**、**語音頻道被刪**、**bot 被移出伺服器**時，摘要會和逐字稿一起刪掉。

## 5. 輸出前的聽眾檢查（規則，AI 組實作）

reader 只檢查「**誰在問**」。答案會貼在哪裡，要由產生答案的程式再檢查一次：

- **私訊回答**：聽眾只有提問者 → 用提問者讀得到的資料即可。
- **在頻道裡回答**：聽眾是「現在看得到這個頻道的所有人」（`channel_access.visible_members(channel_id)`）→ 只能用**這些人全部都讀得到**的來源。

例子：組長在四人共用的 `#team` 問「大家進度如何」，就不能把「組長＋小明」私人頻道的內容寫進回答。

## 6. 還沒有、待討論

- 依**時間範圍**讀取（例如「上次會議之後的訊息」）、一次讀**多個頻道**。AI 組需要時提出，由資料層加。
- bot 自己發的訊息目前也會被存，AI 讀的時候要過濾，或請皓元在儲存時就排除。
- 能看到語音頻道、但**沒參加那場會議**的人，能不能讀逐字稿？目前規則是「可以」（2026-11-19 Ping3227 決定測試期間先維持），待團隊決定。
- 錄音的知情同意流程（`/record`、同意按鈕）會在 Discord 即時錄音那一版加上。
