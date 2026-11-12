# Python Discord Bot

此 bot 提供 `/ping`，並將指定 Discord 伺服器中 bot 有權讀取的文字頻道、語音／舞台頻道文字聊天及討論串訊息保存到本機 SQLite。首次啟動會匯入可讀取的歷史訊息；之後持續記錄新訊息。每筆資料保留伺服器、頻道、訊息與作者 ID，以及文字內容、建立與編輯時間。這是供未來 AI 功能使用的原始資料層，目前沒有 AI 回答或跨頻道檢索功能。

## 設定

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 建立應用程式與 Bot，取得 Bot Token。
2. 在 Developer Portal → Bot → **Privileged Gateway Intents** 啟用 **Message Content Intent**。將 bot 安裝到目標伺服器，授予它需要記錄的頻道的 **View Channel** 與 **Read Message History** 權限；斜線指令需要 `bot`／`applications.commands` scope。
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

## 本機檢查

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_message_store
```
