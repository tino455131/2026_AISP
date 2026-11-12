# Decisions Log

## 2026-09-21 — Initial code steward
**What:** [Name] is the initial code steward for the team.
**Why:** [one sentence — e.g. "volunteered," "has the most git experience so far," "assigned by team agreement"]

## 2026-10-28 — Python Discord bot starter

**What:** 新增 `discord_bot/`，以 `discord.py` 建立提供 `/ping` 的斜線指令 bot。
**Why:** 將 bot 起始程式放在既有課程專案內，並以獨立資料夾避免覆蓋專案文件；斜線指令不需要 Message Content Intent。

## 2026-10-28 — 指定伺服器訊息紀錄與歷史匯入

**What:** 依使用者本次要求，bot 記錄指定伺服器中它有權讀取的文字頻道與討論串訊息，首次啟動並匯入可存取的歷史訊息。此決定取代上方起始版本「不需要 Message Content Intent」的設定。
**Why:** 為未來 AI 記憶建立有伺服器與頻道來源的原始資料。以本機 SQLite 保存，查詢介面限定單一頻道；目前不提供 AI 回答或跨頻道讀取。資料保留期限及成員知情方式仍待團隊決定。
