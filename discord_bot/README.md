# Python Discord Bot

此 bot 提供 `/ping`，並將指定 Discord 伺服器中 bot 有權讀取的文字頻道、語音／舞台頻道文字聊天及討論串訊息保存到本機 SQLite。首次啟動會匯入可讀取的歷史訊息；之後持續記錄新訊息。每筆資料保留伺服器、頻道、訊息與作者 ID，以及文字內容、建立與編輯時間。這是供未來 AI 功能使用的原始資料層，目前沒有 AI 回答或跨頻道檢索功能。

## 設定

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 建立應用程式與 Bot，取得 Bot Token。
2. 在 Developer Portal → Bot → **Privileged Gateway Intents** 啟用 **Message Content Intent** 與 **Server Members Intent**。前者用來取得訊息文字，後者用來列出完整伺服器成員並計算每個頻道的可見名單。將 bot 安裝到目標伺服器，授予它需要記錄的頻道的 **View Channel** 與 **Read Message History** 權限；斜線指令需要 `bot`／`applications.commands` scope。
3. 在 Discord 開啟開發者模式，複製目標伺服器 ID。bot 只會記錄 `.env` 指定的這一個伺服器。
4. 在本資料夾執行：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

5. 編輯 `.env`，填入 `DISCORD_TOKEN` 與 `DISCORD_GUILD_ID`。Token 不要公開或提交到 Git。

## 啟動

```powershell
.\.venv\Scripts\python.exe bot.py
```

資料庫建立在 `data/messages.sqlite3`，已排除在 Git 之外。啟動後會在背景逐一匯入有權讀取的頻道與討論串歷史訊息；中斷後重新啟動會從各頻道上次匯入的訊息繼續，重複訊息依 Discord 訊息 ID 去重。匯入較大的伺服器可能需要較長時間，進度會顯示在終端機。

新的純文字訊息會即時保存；訊息編輯、刪除，以及頻道／討論串刪除會同步到本機資料庫。Bot 被移出指定伺服器時，會清除該伺服器的本機紀錄。沒有文字的附件或嵌入內容不會保存。Bot 離線期間發生的編輯或刪除可能無法自動同步到舊紀錄；後續正式使用 AI 記憶前，應先定義資料保留與重整機制。

此資料庫可能包含 bot 可讀取的私人頻道內容。未來的 AI 查詢必須檢查請求者是否仍有權存取對應頻道，不能直接跨頻道合併。部署前也應讓伺服器成員知悉記錄範圍與用途。依 [Discord Developer Policy](https://support-dev.discord.com/hc/en-us/articles/8563934450327-Discord-Developer-Policy)，不得將透過 API 取得的訊息內容用於訓練 AI 模型，除非取得 Discord 明確許可。

## 頻道可見性與安全讀取

每筆訊息以不會隨頻道改名而改變的 `channel_id` 區分。`ChannelAccess` 在每次查詢時向 Discord 取得目前頻道、成員與權限，不把可見名單保存到 SQLite。`visible_members(channel_id)` 回傳頻道 ID、目前名稱、類型、討論串的父頻道 ID，以及可見的人類成員 ID／顯示名稱。名單代表**現在能看到頻道**的人；讀取已存訊息還需要 `Read Message History` 權限。

例如伺服器有 `#team`（頻道 ID 101，Alice 與 Bob 可見）和 `#leader`（頻道 ID 102，只有 Alice 可見）：兩個頻道的訊息會按 ID 分開保存。Bob 查詢 `#team` 的舊訊息可通過權限檢查，查詢 `#leader` 則會得到 `AccessDenied`。若 Bob 之後失去 `#team` 的權限，下一次查詢也會被拒絕；過去能看到並不保證現在仍能讀取。

內部程式應從 `BotClient.message_reader` 讀取訊息：

```py
visibility = await client.channel_access.visible_members(channel_id)
can_read = await client.channel_access.can_read_history(member_id, channel_id)
messages = await client.message_reader.recent_messages_for(member_id, channel_id)
```

`recent_messages_for` 會先重新核對目前的權限，再讀取單一頻道。沒有 `View Channel`、`Read Message History` 或私人討論串成員資格時會拋出 `AccessDenied`；Discord 無法確認頻道、成員或權限時會拋出 `AccessUnavailable`，不回傳任何訊息或不完整名單。私人討論串需屬於該討論串，或在父頻道具有 `Manage Threads`；公開討論串採用父頻道權限。`MessageStore.recent_messages` 是底層資料庫方法，未來 AI 功能必須使用 `message_reader`，不可直接呼叫它。

目前沒有公開可見名單的斜線指令，也沒有 AI 檢索或回答功能。這些介面供後續功能在完成權限檢查後使用。

## 語音逐字稿（F6）

語音頻道的會議逐字稿由 [`voice_stt/`](../voice_stt/README.md) 產生，存在**同一個** `data/messages.sqlite3`：`voice_sessions`（一場會議）、`voice_lines`（一句話）、`voice_session_summaries`（會議摘要）。資料庫因此改用 WAL 模式，讓 bot 和 `voice_stt` 兩個程式能同時寫入。

讀取一樣要經過權限檢查：AI 功能使用 `BotClient.transcript_reader`（`transcript_reader.py`），以**語音頻道**的 View Channel + Read Message History 判斷。語音頻道被刪除或 bot 被移出伺服器時，逐字稿與摘要會一起刪除。給 AI 組的完整讀取說明見 [docs/ai_memory_api.md](../docs/ai_memory_api.md)。

## 本機檢查

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_channel_access test_message_store test_bot_events test_transcript_store test_transcript_reader
```
