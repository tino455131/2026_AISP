# Team Bot 使用說明

Team Bot 使用一個 Discord 帳號。Node.js 負責指令和錄音，Python 負責把文字存進共用資料庫。完整資料流見[系統流程圖](../docs/SystemWorkflow.html)。

## Discord 權限

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 選擇使用 `VOICE_BOT_TOKEN` 的應用程式。
2. 在 **Bot → Privileged Gateway Intents** 啟用 **Message Content Intent** 和 **Server Members Intent** 並儲存。
3. 邀請 Bot 時使用 `bot` 和 `applications.commands` scope。依要用的功能，在來源頻道授予 **View Channel**、**Read Message History**、**Send Messages** 和語音頻道的 **Connect**。邀請連結可用[語音 Bot 的設定檢查](../voice_bot/README.md#一次性設定)產生。

## 啟動

從[根目錄 README](../README.md#從專案根目錄設定與啟動)完成安裝與啟動。Terminal 的 `[語音]` 和 `[文字]` 前綴可分辨兩個程序。按 Ctrl+C 會一起停止，正在錄音時會先收尾。啟動旗標可用 `node team_bot/start.mjs --help` 查詢。

## 指令

目前只啟用 `/help` 和 `/ask`。`/help` 一律只顯示給執行者。`/ask` 預設在原頻道公開回覆，需要私人回覆時可將 `private` 設為 `true`。

| 指令 | 範例 | 作用 |
|---|---|---|
| `/help` | `/help` | 私下查看目前可用指令。 |
| `/ask` | `/ask question:我們剛才決定了什麼？` | 在同一則互動回覆中顯示提問者、完整問題與答案。 |

`/ask question:這個頻道最近決定了什麼？ private:true` 會將整則結果只顯示給提問者。即使使用公開模式，含歷史的答案也只有在所有可見成員都有權讀取來源時才會公開。聽眾權限不足時，頻道只顯示通用提示。

`/ask` 使用根目錄 `.env` 的 `OPENAI_API_KEY` 和 `MEETING_SUMMARY_MODEL`。模型會用提問者的 Discord ID 對照近期訊息的作者。開發教學見 [AI 團隊接手指南](../docs/ai_team_guide.md)。

其餘斜線指令暫停註冊。錄音、文字記錄與既有按鈕仍依啟動設定運作。

## 已知限制

- **直接錄音模式。** 目前預設模式將成員標成 `included`，轉寫只接受 `agreed`，因此錄音可能被略過並刪除，即使開啟 `KEEP_AUDIO`。這個模式在錄音通知發送失敗時仍可能開始錄音。可從根目錄執行 `node team_bot/start.mjs --consent ask --auto-record off`，暫停自動錄音。 [錄音開始](../voice_bot/src/commands.js) · [轉寫匯入](../voice_bot/voice_stt/stt/ingest_recording.py)
- **文字會議整理失敗。** `/meeting end` 先清除進行中的會議，再讀 Discord 和呼叫摘要器。後續步驟失敗時，同一場會議無法用原指令重試。 [文字會議](../voice_bot/src/meetings.js)
- **聊天保存與同步。** 文字記錄程序會保存可讀頻道的一般聊天；保留期限仍需由部署設定。Bot 離線期間發生的編輯和刪除可能留在本地舊紀錄。 [文字記錄](../text_bot/README.md)
