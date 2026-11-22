# 文字 Bot

文字 Bot 記錄指定伺服器裡可讀的文字頻道、語音／舞台頻道的文字聊天，以及討論串。Team Bot 使用同一套文字記錄程式。需要獨立執行文字 Bot 時，使用它自己的 Discord 帳號。

## 設定

依[根目錄 README](../README.md#從專案根目錄設定與啟動)安裝 `text_bot/.venv`。在文字 Bot 的 Discord 應用程式套用 [Gateway Intents 和頻道權限](../team_bot/README.md#discord-權限)，然後在根目錄 `.env` 填入 `TEXT_BOT_TOKEN` 和 `DISCORD_GUILD_ID`。

在專案根目錄啟動。

```powershell
.\text_bot\.venv\Scripts\python.exe text_bot/bot.py
```

```sh
./text_bot/.venv/bin/python text_bot/bot.py
```

獨立文字 Bot 暫停註冊斜線指令。可從 Terminal 的登入訊息確認已上線。部署時在 Team Bot 的文字記錄和此入口之間選一個，避免兩個程序重複接收同一批事件。

## 記錄與同步

- 啟動時會背景匯入歷史。各頻道按保存的進度接續，訊息 ID 用於去重，匯入筆數在 Terminal 顯示。
- 即時文字訊息寫入後，Terminal 會顯示頻道 ID、使用者 ID 與內容。程式也監聽編輯和刪除。部署時請告知成員記錄範圍，並只讓有權限的管理者存取 Terminal 與資料庫。
- 即時訊息、歷史匯入和編輯會略過 Bot 帳號與 Webhook 傳送的內容。歷史進度仍會接續，舊的資料庫紀錄會保留。
- 離線期間的編輯或刪除可能未同步。資料表及查詢方式見[資料庫結構](../docs/database_schema.md)和 [SQLite API](../SQL_API_README.md)。

## 使用者名稱

Bot 登入時會同步指定伺服器的成員 username。成員加入或 Bot 偵測到 username 變更時，會更新 `users` 表。以 `SQLiteStore.get_user_name(user_id)` 取得最近一次保存的名稱，查無資料時回傳空字串。

## 頻道可見性與安全讀取

`channel_access.py` 依 Discord 當下權限計算可見成員，`transcript_reader.py` 使用同一套權限規則授權查看語音逐字稿。開發者可直接看 [AI 讀取介面](../docs/ai_memory_api.md)的範例與錯誤處理。

## 本機檢查

在專案根目錄執行。

```powershell
.\text_bot\.venv\Scripts\python.exe -m unittest discover -s text_bot/test -t text_bot
```

```sh
./text_bot/.venv/bin/python -m unittest discover -s text_bot/test -t text_bot
```
