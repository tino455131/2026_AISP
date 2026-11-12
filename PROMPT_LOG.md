# AI Prompt Log

## 2026-10-28 — Discord bot starter

- **Prompt 1:** 「以python在專案資料夾內初始化一個discord bot的內容」
- **Prompt 2 (path correction):** 「不對，應該要在這 D:\HaoYuan\course\AISP\2026_AISP」
- **Model/tool:** Codex (GPT-6 family), with local Python checks.
- **Produced:** `discord_bot/bot.py`, dependency list, environment template, ignore rules, and setup README. Added a link in the project README and a decision entry.
- **Changes and why:** The first draft was placed in the chat workspace. It was moved into this repository after the user specified the intended path. The bot files live in a subfolder because the repository already had its own README.
## 2026-10-28 — Discord message logging

- **Prompt:** 「我想讓bot有能log伺服器每個頻道內文字的能力，作為未來AI的記憶」
- **Clarification:** 使用者選擇「也要匯入歷史訊息」。
- **Model/tool:** Codex (GPT-6 family), official Discord and discord.py documentation, local Python checks.
- **Produced:** 新增訊息儲存、歷史匯入與續傳、即時新增／編輯／刪除事件處理，以及本機測試。更新設定與使用說明。
- **Changes and why:** 記錄範圍限於設定的單一伺服器和 bot 有權讀取的頻道；SQLite 保留頻道 ID，供未來查詢時執行權限隔離。Discord 訊息內容不能用於訓練模型，這次沒有加入 AI 查詢功能。
- **Checks:** 5 個本機測試通過；未提供 Bot Token 或伺服器 ID，因此未實際連線匯入。
