# Team Bot 使用說明

Team Bot 使用一個 Discord 帳號。Node.js 負責指令和錄音，Python 負責把文字存進共用資料庫。完整資料流見[系統流程圖](../docs/SystemWorkflow.html)。

## Discord 權限

1. 在 [Discord Developer Portal](https://discord.com/developers/applications) 選擇使用 `VOICE_BOT_TOKEN` 的應用程式。
2. 在 **Bot → Privileged Gateway Intents** 啟用 **Message Content Intent** 和 **Server Members Intent** 並儲存。
3. 邀請 Bot 時使用 `bot` 和 `applications.commands` scope。依要用的功能，在來源頻道授予 **View Channel**、**Read Message History**、**Send Messages** 和語音頻道的 **Connect**。邀請連結可用[語音 Bot 的設定檢查](../voice_bot/README.md#一次性設定)產生。

## 啟動

從[根目錄 README](../README.md#從專案根目錄設定與啟動)完成安裝與啟動。Terminal 的 `[語音]` 和 `[文字]` 前綴可分辨兩個程序。按 Ctrl+C 會一起停止，正在錄音時會先收尾。啟動旗標可用 `node team_bot/start.mjs --help` 查詢。

## 指令

在 Discord 執行 `/help` 可查看目前註冊的所有指令與子指令。

| 想做什麼 | 範例 | 權限與結果 |
|---|---|---|
| 錄音與轉寫 | `/record start` → `/record stop` | 組長開始與停止。摘要與逐字稿透過授權查看按鈕取得。詳見[語音操作](../voice_bot/README.md#使用)。 |
| 整理一段文字會議 | `/meeting start` → `/meeting end` | 組長標記會議起訖。Bot 從 Discord 讀取期間的發言，將紀錄存入 `text_meetings` 並貼回原頻道。 |
| 摘要目前頻道 | `/summary_this_channel` | 使用 `MEETING_SUMMARIZER` 整理目前頻道最近最多 100 則已存文字。來源權限通過後，結果私下顯示。 |
| 私人 OpenAI 問答 | `/ask question:解釋 Python 的 async`、`/ask question:我們剛才決定了什麼？` | 一般問題直接回答。需要目前頻道歷史時，驗權後讀取 SQLite，答案只顯示給提問者。 |
| 問指定會議或追蹤任務 | `/ai ask`、`/ai tasks`、`/ai tracked` | 測試用功能。請先閱讀下方的追蹤限制。流程見 [AI demo](../ai_demo/README.md)。 |

組長由 `LEADER_ROLE_ID` 指定。留空時，具有 **Manage Server** 權限的人可使用組長操作。語音與文字會議使用同一個 `MEETING_SUMMARIZER`。會議進行中的起點保存在錄音目錄的 `active-meetings.json`。

`/ask` 使用根目錄 `.env` 的 `OPENAI_API_KEY` 和 `MEETING_SUMMARY_MODEL`。歷史工具最多取 100 則已存文字，交給模型的文字上限為 12,000 字元。開發教學見 [AI 團隊接手指南](../docs/ai_team_guide.md)。

## 已知限制

- **直接錄音模式。** 目前預設模式將成員標成 `included`，轉寫只接受 `agreed`，因此錄音可能被略過並刪除，即使開啟 `KEEP_AUDIO`。這個模式在錄音通知發送失敗時仍可能開始錄音。測試時可從根目錄執行 `node team_bot/start.mjs --consent ask --auto-record off`，再由組長開始錄音及成員按同意。 [錄音開始](../voice_bot/src/commands.js) · [轉寫匯入](../voice_bot/voice_stt/stt/ingest_recording.py)
- **追蹤狀態的可見範圍。** `/ai tracked` 會向能讀來源頻道的成員顯示負責人回報的狀態。組長失去來源權限後，仍可能用先前的確認按鈕建立追蹤。 [AI 追蹤](../voice_bot/src/ai.js)
- **文字會議整理失敗。** `/meeting end` 先清除進行中的會議，再讀 Discord 和呼叫摘要器。後續步驟失敗時，同一場會議無法用原指令重試。 [文字會議](../voice_bot/src/meetings.js)
- **聊天保存與同步。** 文字記錄程序會保存可讀頻道的一般聊天；保留期限仍需由部署設定。Bot 離線期間發生的編輯和刪除可能留在本地舊紀錄。 [文字記錄](../text_bot/README.md)
